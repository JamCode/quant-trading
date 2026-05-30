"""HK equities EOD spot: East Money primary, Sina fallback."""

from __future__ import annotations

import logging
import math
import time
import traceback
from datetime import date, datetime, timezone
from typing import Any, Optional

import requests

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine
from fund_platform.hk_stock_basic import (
    enrich_hk_stock_basic_em,
    hk_basic_row_from_spot,
    normalize_hk_code,
    upsert_hk_stock_basic,
)

logger = logging.getLogger(__name__)

_MIN_ROWS_OK = 800

_SINA_HK_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/"
    "json_v2.php/Market_Center.getHKStockData"
)
_SINA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://stock.finance.sina.com.cn/hkstock/",
}

_EM_HK_FS = "m:128 t:3,m:128 t:4,m:128 t:1,m:128 t:2"
_EM_URLS = (
    "https://72.push2.eastmoney.com/api/qt/clist/get",
    "https://63.push2.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _trade_date_today() -> date:
    return datetime.now().date()


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


def _amount_to_yi_hkd(value: Any) -> Optional[float]:
    """成交额 → 亿港币（东财/Sina 原值多为元级）。"""
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


def _fetch_hk_spot_sina_pages() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_delay = fp_settings.hk_stock_daily_page_delay_sec()
    for page in range(1, 100):
        if page > 1 and page_delay > 0:
            time.sleep(page_delay)
        params = {
            "page": str(page),
            "num": "80",
            "sort": "symbol",
            "asc": "1",
            "node": "qbgg_hk",
            "_s_r_a": "init",
        }
        last: Optional[Exception] = None
        data: list[dict[str, Any]] = []
        for attempt in range(4):
            try:
                r = requests.get(
                    _SINA_HK_URL, params=params, headers=_SINA_HEADERS, timeout=30
                )
                r.raise_for_status()
                payload = r.json()
                if not payload:
                    data = []
                    break
                if not isinstance(payload, list):
                    raise RuntimeError(f"sina hk spot unexpected page={page}")
                data = payload
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(fp_settings.hk_stock_daily_retry_sleep_sec() * (attempt + 1))
        if not data:
            if last and len(rows) < _MIN_ROWS_OK:
                raise last
            break
        for rec in data:
            sym = normalize_hk_code(str(rec.get("symbol", rec.get("code", ""))))
            if not sym:
                continue
            name = str(rec.get("name", "")).strip()
            if not name:
                continue
            rows.append(
                {
                    "code": sym,
                    "name": name,
                    "name_en": str(rec.get("engname", "")).strip() or None,
                    "security_type": str(rec.get("tradetype", rec.get("type", ""))).strip()
                    or None,
                    "price": _opt_float(rec.get("lasttrade")),
                    "change_pct": _opt_float(rec.get("changepercent")),
                    "change_amt": _opt_float(rec.get("pricechange")),
                    "open_px": _opt_float(rec.get("open")),
                    "high_px": _opt_float(rec.get("high")),
                    "low_px": _opt_float(rec.get("low")),
                    "prev_close": _opt_float(rec.get("prevclose")),
                    "volume": _int_or_none(rec.get("volume")),
                    "amount": _amount_to_yi_hkd(rec.get("amount")),
                    "turnover_pct": None,
                    "pe_dynamic": None,
                    "pb": None,
                    "amplitude_pct": None,
                }
            )
    if len(rows) < _MIN_ROWS_OK:
        raise RuntimeError(f"sina hk spot rows too few: {len(rows)}")
    return rows


def _rows_from_sina_akshare_df(df) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        sym = normalize_hk_code(str(rec.get("代码", "")))
        if not sym:
            continue
        name = str(rec.get("中文名称", "")).strip()
        if not name:
            continue
        rows.append(
            {
                "code": sym,
                "name": name,
                "name_en": str(rec.get("英文名称", "")).strip() or None,
                "security_type": str(rec.get("交易类型", "")).strip() or None,
                "price": _opt_float(rec.get("最新价")),
                "change_pct": _opt_float(rec.get("涨跌幅")),
                "change_amt": _opt_float(rec.get("涨跌额")),
                "open_px": _opt_float(rec.get("今开")),
                "high_px": _opt_float(rec.get("最高")),
                "low_px": _opt_float(rec.get("最低")),
                "prev_close": _opt_float(rec.get("昨收")),
                "volume": _int_or_none(rec.get("成交量")),
                "amount": _amount_to_yi_hkd(rec.get("成交额")),
                "turnover_pct": None,
                "pe_dynamic": None,
                "pb": None,
                "amplitude_pct": None,
            }
        )
    return rows


def fetch_hk_spot_sina(*, max_attempts: int = 3) -> list[dict[str, Any]]:
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, max_attempts)):
        try:
            return _fetch_hk_spot_sina_pages()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("sina hk spot pages attempt %s failed: %s", attempt + 1, exc)
            time.sleep(fp_settings.hk_stock_daily_retry_sleep_sec() * (attempt + 1))
    if last_exc:
        try:
            import akshare as ak

            df = ak.stock_hk_spot()
            rows = _rows_from_sina_akshare_df(df)
            if len(rows) >= _MIN_ROWS_OK:
                return rows
        except Exception as ak_exc:  # noqa: BLE001
            logger.warning("akshare stock_hk_spot fallback failed: %s", ak_exc)
        raise last_exc
    return []


def _fetch_hk_spot_em_dataframe():
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
        "fs": _EM_HK_FS,
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,"
        "f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152",
    }
    headers = {
        "User-Agent": _SINA_HEADERS["User-Agent"],
        "Referer": "https://quote.eastmoney.com/center/gridlist.html",
    }

    def _page_json(pn: int) -> dict:
        p = {**params, "pn": str(pn)}
        last: Optional[Exception] = None
        for attempt in range(3):
            for url in _EM_URLS:
                try:
                    r = requests.get(url, params=p, headers=headers, timeout=30)
                    r.raise_for_status()
                    return r.json()
                except Exception as exc:  # noqa: BLE001
                    last = exc
            time.sleep(fp_settings.hk_stock_daily_retry_sleep_sec() * (attempt + 1))
        if last:
            raise last
        return {}

    page_delay = fp_settings.hk_stock_daily_page_delay_sec()
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
        if partial < _MIN_ROWS_OK:
            raise exc
        logger.warning("em hk spot partial pages ok rows=%s: %s", partial, exc)
    df = pd.concat(frames, ignore_index=True)
    em_names = [
        "index",
        "_",
        "最新价",
        "涨跌幅",
        "涨跌额",
        "成交量",
        "成交额",
        "振幅",
        "换手率",
        "市盈率-动态",
        "量比",
        "_",
        "代码",
        "_",
        "名称",
        "最高",
        "最低",
        "今开",
        "昨收",
        "_",
        "_",
        "涨速",
        "市净率",
        "60日涨跌幅",
        "年初至今涨跌幅",
        "-",
        "-",
        "-",
        "-",
        "-",
        "-",
        "-",
    ]
    ncol = len(df.columns)
    if ncol != len(em_names):
        if ncol > len(em_names):
            em_names = em_names + [f"_x{i}" for i in range(ncol - len(em_names))]
        else:
            em_names = em_names[:ncol]
    df.columns = em_names
    return df


def _rows_from_em_df(df) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        sym = normalize_hk_code(str(rec.get("代码", "")))
        if not sym:
            continue
        name = str(rec.get("名称", "")).strip()
        if not name:
            continue
        rows.append(
            {
                "code": sym,
                "name": name,
                "name_en": None,
                "security_type": None,
                "price": _opt_float(rec.get("最新价")),
                "change_pct": _opt_float(rec.get("涨跌幅")),
                "change_amt": _opt_float(rec.get("涨跌额")),
                "open_px": _opt_float(rec.get("今开")),
                "high_px": _opt_float(rec.get("最高")),
                "low_px": _opt_float(rec.get("最低")),
                "prev_close": _opt_float(rec.get("昨收")),
                "volume": _int_or_none(rec.get("成交量")),
                "amount": _amount_to_yi_hkd(rec.get("成交额")),
                "turnover_pct": _opt_float(rec.get("换手率")),
                "pe_dynamic": _opt_float(rec.get("市盈率-动态")),
                "pb": _opt_float(rec.get("市净率")),
                "amplitude_pct": _opt_float(rec.get("振幅")),
            }
        )
    return rows


def fetch_hk_spot_em(*, max_attempts: int = 3) -> list[dict[str, Any]]:
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, max_attempts)):
        try:
            df = _fetch_hk_spot_em_dataframe()
            rows = _rows_from_em_df(df)
            if len(rows) >= _MIN_ROWS_OK:
                return rows
            raise RuntimeError(f"em hk spot rows too few: {len(rows)}")
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("em hk spot attempt %s failed: %s", attempt + 1, exc)
            time.sleep(fp_settings.hk_stock_daily_retry_sleep_sec() * (attempt + 1))
    if last_exc:
        raise last_exc
    return []


_CAP_ENRICH_KEYS = ("turnover_pct", "pe_dynamic", "pb", "amplitude_pct")


def _merge_em_quote_fields(base: list[dict[str, Any]], em_rows: list[dict[str, Any]]) -> int:
    by_code = {r["code"]: r for r in em_rows}
    merged = 0
    for row in base:
        em = by_code.get(row["code"])
        if not em:
            continue
        touched = False
        for key in _CAP_ENRICH_KEYS:
            val = em.get(key)
            if val is not None:
                row[key] = val
                touched = True
        if touched:
            merged += 1
    return merged


def fetch_hk_spot(*, max_attempts: int = 4) -> tuple[list[dict[str, Any]], str]:
    """East Money primary; Sina fallback; optional EM enrich when EM is reachable."""
    em_attempts = 1
    try:
        rows = fetch_hk_spot_em(max_attempts=em_attempts)
        return rows, "eastmoney"
    except Exception as em_exc:  # noqa: BLE001
        logger.warning("em hk spot failed, trying sina: %s", em_exc)

    rows = fetch_hk_spot_sina(max_attempts=max_attempts)
    source = "sina"
    return rows, source


def count_hk_stock_daily(conn, trade_date: date) -> int:
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM hk_stock_daily WHERE trade_date = %s",
        (trade_date.isoformat(),),
    )
    row = cur.fetchone()
    return int(row[0] if row else 0)


_HK_STOCK_DAILY_UPSERT_SQL = """
    INSERT INTO hk_stock_daily (
      trade_date, code, name, price, change_pct, change_amt,
      open_px, high_px, low_px, prev_close, volume, amount,
      turnover_pct, pe_dynamic, pb, amplitude_pct, updated_at
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
      turnover_pct = VALUES(turnover_pct),
      pe_dynamic = VALUES(pe_dynamic),
      pb = VALUES(pb),
      amplitude_pct = VALUES(amplitude_pct),
      updated_at = VALUES(updated_at)
"""


def hk_stock_daily_row_params(
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
            r.get("turnover_pct"),
            r.get("pe_dynamic"),
            r.get("pb"),
            r.get("amplitude_pct"),
            now,
        )
        for r in payload
    ]


def _upsert_hk_stock_daily(cur, td_s: str, payload: list[dict[str, Any]], *, now: str) -> None:
    chunk = fp_settings.hk_stock_daily_db_chunk_size()
    params = hk_stock_daily_row_params(td_s, payload, now)
    for i in range(0, len(params), chunk):
        cur.executemany(_HK_STOCK_DAILY_UPSERT_SQL, params[i : i + chunk])


def _prune_hk_stock_daily_codes(cur, td_s: str, keep_codes: set[str]) -> int:
    cur.execute("SELECT code FROM hk_stock_daily WHERE trade_date = %s", (td_s,))
    existing = {normalize_hk_code(str(row[0])) for row in cur.fetchall()}
    existing = {c for c in existing if c}
    to_remove = sorted(existing - keep_codes)
    if not to_remove:
        return 0
    chunk = fp_settings.hk_stock_daily_db_chunk_size()
    removed = 0
    for i in range(0, len(to_remove), chunk):
        part = to_remove[i : i + chunk]
        placeholders = ",".join(["%s"] * len(part))
        cur.execute(
            f"DELETE FROM hk_stock_daily WHERE trade_date = %s AND code IN ({placeholders})",
            (td_s, *part),
        )
        removed += len(part)
    return removed


def sync_hk_stock_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    td = trade_date or _trade_date_today()
    td_s = td.isoformat()
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    job_id = None
    try:
        cur.execute(
            """
            INSERT INTO hk_stock_daily_jobs (trade_date, started_at, ok)
            VALUES (%s, %s, 0)
            """,
            (td_s, _utc_now_iso()),
        )
        job_id = cur.lastrowid
        raw.commit()

        logger.info("hk_stock_daily fetch start trade_date=%s job_id=%s", td_s, job_id)
        payload, source = fetch_hk_spot()
        if len(payload) < _MIN_ROWS_OK:
            raise RuntimeError(f"hk spot rows too few: {len(payload)}")

        now = _utc_now_iso()
        keep_codes = {str(r["code"]) for r in payload}
        chunk = fp_settings.hk_stock_daily_db_chunk_size()
        _upsert_hk_stock_daily(cur, td_s, payload, now=now)
        basic_rows = [hk_basic_row_from_spot(r) for r in payload]
        basic_rows = [b for b in basic_rows if b]
        basic_n = upsert_hk_stock_basic(cur, basic_rows, now=now, chunk_size=chunk)
        pruned = _prune_hk_stock_daily_codes(cur, td_s, keep_codes)
        enrich = enrich_hk_stock_basic_em(cur, now=now)
        cur.execute(
            """
            UPDATE hk_stock_daily_jobs
            SET finished_at = %s, ok = 1, row_count = %s, error = NULL
            WHERE id = %s
            """,
            (now, len(payload), job_id),
        )
        raw.commit()
        logger.info(
            "hk_stock_daily sync OK %s rows=%s basic=%s pruned=%s source=%s",
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
            "basic_enrich": enrich,
        }
    except Exception as exc:  # noqa: BLE001
        err = f"{exc}\n{traceback.format_exc()}"
        logger.exception("sync_hk_stock_daily failed")
        if job_id is not None:
            try:
                cur.execute(
                    """
                    UPDATE hk_stock_daily_jobs
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


def ensure_hk_stock_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    td = trade_date or _trade_date_today()
    engine = get_engine()
    raw = engine.raw_connection()
    try:
        n = count_hk_stock_daily(raw, td)
        if n >= _MIN_ROWS_OK:
            return {"ok": True, "trade_date": td.isoformat(), "count": n, "skipped": True}
    finally:
        raw.close()
    return sync_hk_stock_daily(td)
