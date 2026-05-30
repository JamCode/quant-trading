"""US equities EOD spot: East Money full market primary, Sina (akshare) slow fallback."""

from __future__ import annotations

import logging
import math
import time
import traceback
from datetime import date, datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine
from fund_platform.us_stock_basic import (
    em_symbol_to_ticker,
    market_from_em_symbol,
    normalize_us_ticker,
    upsert_us_stock_basic,
    us_basic_row_from_spot,
)

logger = logging.getLogger(__name__)

_MIN_ROWS_OK = 2500
_US_TZ = ZoneInfo("America/New_York")

# NYSE / NASDAQ / AMEX — fetch separately (smaller pages, more reliable on ECS).
_EM_US_SEGMENTS = ("m:105", "m:106", "m:107")
_EM_URLS = (
    "https://33.push2.eastmoney.com/api/qt/clist/get",
    "https://48.push2.eastmoney.com/api/qt/clist/get",
    "https://63.push2.eastmoney.com/api/qt/clist/get",
    "https://72.push2.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
)
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/center/gridlist.html",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def trade_date_us_eod() -> date:
    """US session calendar date in America/New_York at sync time."""
    return datetime.now(_US_TZ).date()


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in ("-", "--", "nan", "NaN", "—"):
        return None
    try:
        v = float(s)
        if v != v:
            return None
        return v
    except ValueError:
        return None


def _amount_to_yi_usd(value: Any) -> Optional[float]:
    """成交额 / 总市值 → 亿美元。"""
    v = _opt_float(value)
    if v is None or v <= 0:
        return None
    if v >= 1e6:
        return round(v / 1e8, 2)
    return round(v, 2)


def _int_or_none(value: Any) -> Optional[int]:
    f = _opt_float(value)
    if f is None:
        return None
    return int(f)


def _row_from_em_record(rec: dict[str, Any]) -> Optional[dict[str, Any]]:
    em_code = str(rec.get("代码", "")).strip().upper()
    if not em_code:
        em_code = ""
        enc = str(rec.get("编码", "")).strip()
        abbr = str(rec.get("简称", "")).strip().upper()
        if enc and abbr:
            em_code = f"{enc}.{abbr}"
    ticker = em_symbol_to_ticker(em_code) if em_code else None
    if not ticker:
        ticker = normalize_us_ticker(str(rec.get("简称", "")))
    if not ticker:
        return None
    name = str(rec.get("名称", "")).strip()
    if not name:
        name = ticker
    return {
        "code": ticker,
        "name": name,
        "name_en": None,
        "em_symbol": em_code or None,
        "market": market_from_em_symbol(em_code),
        "price": _opt_float(rec.get("最新价")),
        "change_pct": _opt_float(rec.get("涨跌幅")),
        "change_amt": _opt_float(rec.get("涨跌额")),
        "open_px": _opt_float(rec.get("开盘价", rec.get("今开"))),
        "high_px": _opt_float(rec.get("最高价", rec.get("最高"))),
        "low_px": _opt_float(rec.get("最低价", rec.get("最低"))),
        "prev_close": _opt_float(rec.get("昨收价", rec.get("昨收"))),
        "volume": _int_or_none(rec.get("成交量")),
        "amount": _amount_to_yi_usd(rec.get("成交额")),
        "total_market_cap": _amount_to_yi_usd(rec.get("总市值")),
        "turnover_pct": _opt_float(rec.get("换手率")),
        "pe_dynamic": _opt_float(rec.get("市盈率", rec.get("市盈率-动态"))),
        "amplitude_pct": _opt_float(rec.get("振幅")),
    }


def _fetch_us_spot_em_dataframe_for_fs(fs: str):
    import pandas as pd

    params = {
        "pn": "1",
        "pz": "100",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f12",
        "fs": fs,
        "dect": "1",
        "wbp2u": "|0|0|0|web",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,"
        "f21,f23,f24,f25,f26,f22,f33,f11,f62,f128,f136,f115,f152",
    }

    def _page_json(pn: int) -> dict:
        p = {**params, "pn": str(pn)}
        last: Optional[Exception] = None
        for attempt in range(4):
            for url in _EM_URLS:
                try:
                    r = requests.get(url, params=p, headers=_HEADERS, timeout=45)
                    r.raise_for_status()
                    return r.json()
                except Exception as exc:  # noqa: BLE001
                    last = exc
            time.sleep(fp_settings.us_stock_daily_retry_sleep_sec() * (attempt + 1))
        if last:
            raise last
        return {}

    page_delay = fp_settings.us_stock_daily_page_delay_sec()
    data1 = _page_json(1)
    first = pd.DataFrame(data1.get("data", {}).get("diff") or [])
    if first.empty:
        return first
    per_page = max(1, len(first))
    total_n = int(data1.get("data", {}).get("total") or 0)
    total_pages = max(1, math.ceil(total_n / per_page))
    frames = [first]
    try:
        for pn in range(2, total_pages + 1):
            if page_delay > 0:
                time.sleep(page_delay)
            frames.append(pd.DataFrame(_page_json(pn).get("data", {}).get("diff") or []))
    except Exception as exc:  # noqa: BLE001
        partial = sum(len(f) for f in frames)
        if partial < 500:
            raise exc
        logger.warning("em us spot partial fs=%s rows=%s: %s", fs, partial, exc)
    df = pd.concat(frames, ignore_index=True)
    names = [
        "index",
        "_",
        "最新价",
        "涨跌幅",
        "涨跌额",
        "成交量",
        "成交额",
        "振幅",
        "换手率",
        "_",
        "_",
        "_",
        "简称",
        "编码",
        "名称",
        "最高价",
        "最低价",
        "开盘价",
        "昨收价",
        "总市值",
        "_",
        "_",
        "_",
        "_",
        "_",
        "_",
        "_",
        "_",
        "市盈率",
        "_",
        "_",
        "_",
        "_",
        "_",
    ]
    ncol = len(df.columns)
    if ncol != len(names):
        if ncol > len(names):
            names = names + [f"_x{i}" for i in range(ncol - len(names))]
        else:
            names = names[:ncol]
    df.columns = names
    if "编码" in df.columns and "简称" in df.columns:
        df["代码"] = df["编码"].astype(str) + "." + df["简称"].astype(str)
    return df


def _fetch_us_spot_em_dataframe():
    import pandas as pd

    frames = []
    for fs in _EM_US_SEGMENTS:
        part = _fetch_us_spot_em_dataframe_for_fs(fs)
        if not part.empty:
            frames.append(part)
        seg_delay = fp_settings.us_stock_daily_page_delay_sec()
        if seg_delay > 0:
            time.sleep(seg_delay)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _rows_from_em_df(df) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        row = _row_from_em_record(rec)
        if row:
            rows.append(row)
    return rows


def fetch_us_spot_em(*, max_attempts: int = 2) -> list[dict[str, Any]]:
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, max_attempts)):
        try:
            df = _fetch_us_spot_em_dataframe()
            rows = _rows_from_em_df(df)
            # Deduplicate tickers (segments may overlap).
            by_code: dict[str, dict[str, Any]] = {}
            for row in rows:
                by_code[row["code"]] = row
            rows = list(by_code.values())
            if len(rows) >= _MIN_ROWS_OK:
                return rows
            raise RuntimeError(f"em us spot rows too few: {len(rows)}")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("em us spot attempt %s failed: %s", attempt + 1, exc)
            time.sleep(fp_settings.us_stock_daily_retry_sleep_sec() * (attempt + 1))
    if last_exc:
        raise last_exc
    return []


def _rows_from_sina_df(df) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        ticker = normalize_us_ticker(str(rec.get("symbol", rec.get("code", ""))))
        if not ticker:
            continue
        name = str(rec.get("cname") or rec.get("name") or "").strip() or ticker
        rows.append(
            {
                "code": ticker,
                "name": name,
                "name_en": str(rec.get("name", "")).strip() or None,
                "em_symbol": None,
                "market": None,
                "price": _opt_float(rec.get("price", rec.get("lasttrade"))),
                "change_pct": _opt_float(rec.get("changepercent", rec.get("change_pct"))),
                "change_amt": _opt_float(rec.get("pricechange", rec.get("change"))),
                "open_px": _opt_float(rec.get("open")),
                "high_px": _opt_float(rec.get("high")),
                "low_px": _opt_float(rec.get("low")),
                "prev_close": _opt_float(rec.get("preclose", rec.get("prevclose"))),
                "volume": _int_or_none(rec.get("volume")),
                "amount": _amount_to_yi_usd(rec.get("amount")),
                "total_market_cap": None,
                "turnover_pct": None,
                "pe_dynamic": None,
                "amplitude_pct": None,
            }
        )
    return rows


def fetch_us_spot_sina(*, max_attempts: int = 1) -> list[dict[str, Any]]:
    """Sina via akshare; slow (~15–25 min) — only when EM is down."""
    if not fp_settings.us_stock_sina_fallback_enabled():
        raise RuntimeError("us sina fallback disabled")
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, max_attempts)):
        try:
            import akshare as ak

            logger.warning("us spot sina fallback start (may take 15+ minutes)")
            df = ak.stock_us_spot()
            rows = _rows_from_sina_df(df)
            if len(rows) >= _MIN_ROWS_OK:
                return rows
            raise RuntimeError(f"sina us spot rows too few: {len(rows)}")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("sina us spot attempt %s failed: %s", attempt + 1, exc)
            time.sleep(fp_settings.us_stock_daily_retry_sleep_sec() * (attempt + 1))
    if last_exc:
        raise last_exc
    return []


def fetch_us_spot(*, max_attempts: int = 2) -> tuple[list[dict[str, Any]], str]:
    try:
        return fetch_us_spot_em(max_attempts=1), "eastmoney"
    except Exception as em_exc:  # noqa: BLE001
        logger.warning("em us spot failed: %s", em_exc)
    rows = fetch_us_spot_sina(max_attempts=max_attempts)
    return rows, "sina"


def count_us_stock_daily(conn, trade_date: date) -> int:
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM us_stock_daily WHERE trade_date = %s",
        (trade_date.isoformat(),),
    )
    row = cur.fetchone()
    return int(row[0] if row else 0)


_US_STOCK_DAILY_UPSERT_SQL = """
    INSERT INTO us_stock_daily (
      trade_date, code, name, price, change_pct, change_amt,
      open_px, high_px, low_px, prev_close, volume, amount,
      total_market_cap, turnover_pct, pe_dynamic, amplitude_pct, updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
      name = VALUES(name),
      price = VALUES(price),
      change_pct = VALUES(change_pct),
      change_amt = VALUES(change_amt),
      open_px = VALUES(open_px),
      high_px = VALUES(high_px),
      low_px = VALUES(low_px),
      prev_close = VALUES(prev_close),
      volume = VALUES(volume),
      amount = VALUES(amount),
      total_market_cap = VALUES(total_market_cap),
      turnover_pct = VALUES(turnover_pct),
      pe_dynamic = VALUES(pe_dynamic),
      amplitude_pct = VALUES(amplitude_pct),
      updated_at = VALUES(updated_at)
"""


def us_stock_daily_row_params(
    td_s: str, payload: list[dict[str, Any]], now: str
) -> list[tuple[Any, ...]]:
    return [
        (
            td_s,
            r["code"],
            r["name"],
            r.get("price"),
            r.get("change_pct"),
            r.get("change_amt"),
            r.get("open_px"),
            r.get("high_px"),
            r.get("low_px"),
            r.get("prev_close"),
            r.get("volume"),
            r.get("amount"),
            r.get("total_market_cap"),
            r.get("turnover_pct"),
            r.get("pe_dynamic"),
            r.get("amplitude_pct"),
            now,
        )
        for r in payload
    ]


def _upsert_us_stock_daily(cur, td_s: str, payload: list[dict[str, Any]], *, now: str) -> None:
    chunk = fp_settings.us_stock_daily_db_chunk_size()
    params = us_stock_daily_row_params(td_s, payload, now)
    for i in range(0, len(params), chunk):
        cur.executemany(_US_STOCK_DAILY_UPSERT_SQL, params[i : i + chunk])


def _prune_us_stock_daily_codes(cur, td_s: str, keep_codes: set[str]) -> int:
    cur.execute("SELECT code FROM us_stock_daily WHERE trade_date = %s", (td_s,))
    existing = {normalize_us_ticker(str(row[0])) for row in cur.fetchall()}
    existing = {c for c in existing if c}
    to_remove = sorted(existing - keep_codes)
    if not to_remove:
        return 0
    chunk = fp_settings.us_stock_daily_db_chunk_size()
    removed = 0
    for i in range(0, len(to_remove), chunk):
        part = to_remove[i : i + chunk]
        placeholders = ",".join(["%s"] * len(part))
        cur.execute(
            f"DELETE FROM us_stock_daily WHERE trade_date = %s AND code IN ({placeholders})",
            (td_s, *part),
        )
        removed += len(part)
    return removed


def sync_us_stock_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    td = trade_date or trade_date_us_eod()
    td_s = td.isoformat()
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    job_id = None
    try:
        cur.execute(
            """
            INSERT INTO us_stock_daily_jobs (trade_date, started_at, ok)
            VALUES (%s, %s, 0)
            """,
            (td_s, _utc_now_iso()),
        )
        job_id = cur.lastrowid
        raw.commit()

        logger.info("us_stock_daily fetch start trade_date=%s job_id=%s", td_s, job_id)
        payload, source = fetch_us_spot()
        if len(payload) < _MIN_ROWS_OK:
            raise RuntimeError(f"us spot rows too few: {len(payload)}")

        now = _utc_now_iso()
        keep_codes = {str(r["code"]) for r in payload}
        chunk = fp_settings.us_stock_daily_db_chunk_size()
        _upsert_us_stock_daily(cur, td_s, payload, now=now)
        basic_rows = [us_basic_row_from_spot(r) for r in payload]
        basic_rows = [b for b in basic_rows if b]
        basic_n = upsert_us_stock_basic(cur, basic_rows, now=now, chunk_size=chunk)
        pruned = _prune_us_stock_daily_codes(cur, td_s, keep_codes)
        cur.execute(
            """
            UPDATE us_stock_daily_jobs
            SET finished_at = %s, ok = 1, row_count = %s, error = NULL
            WHERE id = %s
            """,
            (now, len(payload), job_id),
        )
        raw.commit()
        logger.info(
            "us_stock_daily sync OK %s rows=%s basic=%s pruned=%s source=%s",
            td_s,
            len(payload),
            basic_n,
            pruned,
            source,
        )
        return {
            "ok": True,
            "trade_date": td_s,
            "count": len(payload),
            "job_id": job_id,
            "source": source,
            "basic_upserted": basic_n,
            "pruned": pruned,
        }
    except Exception as exc:  # noqa: BLE001
        err = f"{exc}\n{traceback.format_exc()}"
        logger.exception("sync_us_stock_daily failed")
        if job_id is not None:
            try:
                cur.execute(
                    """
                    UPDATE us_stock_daily_jobs
                    SET finished_at = %s, ok = 0, error = %s
                    WHERE id = %s
                    """,
                    (_utc_now_iso(), err[:4000], job_id),
                )
                raw.commit()
            except Exception:
                raw.rollback()
        else:
            try:
                raw.rollback()
            except Exception:
                pass
        return {"ok": False, "trade_date": td_s, "error": str(exc), "job_id": job_id}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()


def ensure_us_stock_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    td = trade_date or trade_date_us_eod()
    engine = get_engine()
    raw = engine.raw_connection()
    try:
        n = count_us_stock_daily(raw, td)
        if n >= _MIN_ROWS_OK:
            return {"ok": True, "trade_date": td.isoformat(), "count": n, "skipped": True}
    finally:
        raw.close()
    return sync_us_stock_daily(td)
