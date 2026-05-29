"""Daily A-share snapshot (Sina spot primary; East Money optional enrich)."""

from __future__ import annotations

import json
import logging
import math
import re
import time
import traceback
from datetime import date, datetime, timezone
from typing import Any, Optional

import requests

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine
from fund_platform.stock_basic import upsert_stock_basic

logger = logging.getLogger(__name__)

_MIN_ROWS_OK = 3000

_SINA_COUNT_URL = (
    "http://vip.stock.finance.sina.com.cn/quotes_service/api/"
    "json_v2.php/Market_Center.getHQNodeStockCount?node=hs_a"
)
_SINA_SPOT_URL = (
    "http://vip.stock.finance.sina.com.cn/quotes_service/api/"
    "json_v2.php/Market_Center.getHQNodeData"
)
_SINA_SPOT_PARAMS = {
    "num": "80",
    "sort": "symbol",
    "asc": "1",
    "node": "hs_a",
    "symbol": "",
    "_s_r_a": "page",
}
_SINA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn/",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _trade_date_today() -> date:
    return datetime.now().date()


def _cap_to_yi(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    if v <= 0:
        return None
    if v >= 1e6:
        return round(v / 1e8, 2)
    return round(v, 2)


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in ("-", "--", "nan", "NaN", "—"):
        return None
    try:
        v = float(s)
        if v != v:  # NaN
            return None
        return v
    except ValueError:
        return None


def _amount_to_yi(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v <= 0:
        return None
    if v >= 1e6:
        return round(v / 1e8, 2)
    return round(v, 2)


def _cap_wan_to_yi(value: Any) -> Optional[float]:
    """Sina mktcap/nmc fields are in 万元."""
    v = _opt_float(value)
    if v is None or v <= 0:
        return None
    return round(v / 10000, 2)


def _sina_page_count() -> int:
    last: Optional[Exception] = None
    for attempt in range(4):
        try:
            r = requests.get(_SINA_COUNT_URL, headers=_SINA_HEADERS, timeout=20)
            r.raise_for_status()
            nums = re.findall(r"\d+", r.text)
            if not nums:
                raise RuntimeError("sina count parse failed")
            return max(1, math.ceil(int(nums[0]) / 80))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(fp_settings.stock_daily_retry_sleep_sec() * (attempt + 1))
    if last:
        raise last
    return 1


def _fetch_spot_sina_dataframe() -> list[dict[str, Any]]:
    """Sina paginated A-share spot; includes 流通/总市值 (万元 → 亿)."""
    page_count = _sina_page_count()
    page_delay = fp_settings.stock_daily_page_delay_sec()
    rows: list[dict[str, Any]] = []

    for page in range(1, page_count + 1):
        if page > 1 and page_delay > 0:
            time.sleep(page_delay)
        params = {**_SINA_SPOT_PARAMS, "page": str(page)}
        last: Optional[Exception] = None
        data: list[dict[str, Any]] = []
        for attempt in range(4):
            try:
                r = requests.get(
                    _SINA_SPOT_URL, params=params, headers=_SINA_HEADERS, timeout=30
                )
                r.raise_for_status()
                text = r.text.strip()
                if not text or text[0] not in "[{":
                    raise RuntimeError(f"sina spot non-json page={page}: {text[:80]!r}")
                payload = json.loads(text)
                if not isinstance(payload, list):
                    raise RuntimeError(f"sina spot unexpected page={page}")
                data = payload
                break
            except Exception as exc:  # noqa: BLE001
                last = exc
                time.sleep(fp_settings.stock_daily_retry_sleep_sec() * (attempt + 1))
        if not data and last:
            if len(rows) >= _MIN_ROWS_OK:
                logger.warning("sina spot partial ok rows=%s page=%s: %s", len(rows), page, last)
                break
            raise last

        for rec in data:
            code = str(rec.get("code", "")).strip()
            if not code.isdigit():
                continue
            code = code.zfill(6)
            rows.append(
                {
                    "code": code,
                    "name": str(rec.get("name", "")).strip(),
                    "price": _opt_float(rec.get("trade")),
                    "change_pct": _opt_float(rec.get("changepercent")),
                    "float_market_cap": _cap_wan_to_yi(rec.get("nmc")),
                    "total_market_cap": _cap_wan_to_yi(rec.get("mktcap")),
                    "turnover_pct": _opt_float(rec.get("turnoverratio")),
                    "amount": _amount_to_yi(rec.get("amount")),
                    "pe_dynamic": _opt_float(rec.get("per")),
                    "pb": _opt_float(rec.get("pb")),
                    "volume_ratio": None,
                    "amplitude_pct": None,
                    "change_5m_pct": None,
                    "speed_pct": None,
                    "change_60d_pct": None,
                    "change_ytd_pct": None,
                    "industry": None,
                }
            )

    if len(rows) < _MIN_ROWS_OK:
        raise RuntimeError(f"sina spot rows too few: {len(rows)}")
    return rows


def _fetch_spot_em_dataframe() -> "pd.DataFrame":
    """East Money A-share spot with slower pagination (ECS-friendly)."""
    import math

    import pandas as pd
    import requests

    urls = (
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        "https://63.push2.eastmoney.com/api/qt/clist/get",
        "https://push2.eastmoney.com/api/qt/clist/get",
    )
    params = {
        "pn": "1",
        "pz": "50",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f12",
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,"
        "f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://quote.eastmoney.com/center/gridlist.html",
    }

    def _page_json(pn: int) -> dict:
        p = {**params, "pn": str(pn)}
        last: Optional[Exception] = None
        for attempt in range(6):
            for url in urls:
                try:
                    r = requests.get(url, params=p, headers=headers, timeout=30)
                    r.raise_for_status()
                    return r.json()
                except Exception as exc:  # noqa: BLE001
                    last = exc
            time.sleep(fp_settings.stock_daily_retry_sleep_sec() * (attempt + 1))
        if last:
            raise last
        return {}

    page_delay = fp_settings.stock_daily_page_delay_sec()
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
        logger.warning("em spot partial pages ok rows=%s: %s", partial, exc)
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
        "5分钟涨跌",
        "代码",
        "_",
        "名称",
        "最高",
        "最低",
        "今开",
        "昨收",
        "总市值",
        "流通市值",
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
        logger.warning("em spot columns %s (expected %s), padding names", ncol, len(em_names))
        if ncol > len(em_names):
            em_names = em_names + [f"_x{i}" for i in range(ncol - len(em_names))]
        else:
            em_names = em_names[:ncol]
    df.columns = em_names
    wanted = [
        "代码",
        "名称",
        "最新价",
        "涨跌幅",
        "换手率",
        "成交额",
        "振幅",
        "市盈率-动态",
        "量比",
        "5分钟涨跌",
        "总市值",
        "流通市值",
        "涨速",
        "市净率",
        "60日涨跌幅",
        "年初至今涨跌幅",
    ]
    present = [c for c in wanted if c in df.columns]
    if "代码" not in present:
        raise ValueError(f"em spot missing 代码 column; got {list(df.columns)}")
    return df[present]


def fetch_a_share_spot_sina(*, max_attempts: int = 3) -> list[dict[str, Any]]:
    """Sina paginated spot (ECS-friendly; includes float/total market cap)."""
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, max_attempts)):
        try:
            return _fetch_spot_sina_dataframe()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("sina spot attempt %s failed: %s", attempt + 1, exc)
            time.sleep(fp_settings.stock_daily_retry_sleep_sec() * (attempt + 1))
    if last_exc:
        raise last_exc
    return []


_CAP_ENRICH_KEYS = (
    "float_market_cap",
    "total_market_cap",
    "turnover_pct",
    "pe_dynamic",
    "pb",
    "volume_ratio",
    "amplitude_pct",
    "change_5m_pct",
    "speed_pct",
    "change_60d_pct",
    "change_ytd_pct",
)


def _merge_em_cap_fields(base: list[dict[str, Any]], em_rows: list[dict[str, Any]]) -> int:
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


def fetch_a_share_spot(*, max_attempts: int = 6) -> tuple[list[dict[str, Any]], str]:
    """Primary Sina spot; best-effort East Money enrich; EM-only fallback."""
    try:
        rows = fetch_a_share_spot_sina(max_attempts=max_attempts)
    except Exception as sina_exc:  # noqa: BLE001
        logger.warning("sina spot failed, trying eastmoney: %s", sina_exc)
        rows = fetch_a_share_spot_em(max_attempts=2)
        if len(rows) < _MIN_ROWS_OK:
            raise RuntimeError(f"stock spot rows too few: {len(rows)}") from sina_exc
        return rows, "eastmoney"

    source = "sina"
    if not fp_settings.stock_daily_em_enrich_enabled():
        return rows, source
    try:
        em_rows = fetch_a_share_spot_em(max_attempts=1)
        if em_rows:
            n = _merge_em_cap_fields(rows, em_rows)
            if n > 0:
                source = "sina+em_caps"
            logger.info("stock spot em cap enrich merged=%s", n)
    except Exception as exc:  # noqa: BLE001
        logger.warning("stock spot em cap enrich skipped: %s", exc)
    return rows, source


def fetch_a_share_spot_em(*, max_attempts: int = 3) -> list[dict[str, Any]]:
    df = None
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            df = _fetch_spot_em_dataframe()
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("em spot fetch attempt %s failed: %s", attempt + 1, exc)
            time.sleep(fp_settings.stock_daily_retry_sleep_sec() * (attempt + 1))
    if df is None:
        if last_exc:
            raise last_exc
        return []
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        code = str(rec.get("代码", "")).strip()
        if not code.isdigit():
            continue
        code = code.zfill(6)
        rows.append(
            {
                "code": code,
                "name": str(rec.get("名称", "")).strip(),
                "price": _opt_float(rec.get("最新价")),
                "change_pct": _opt_float(rec.get("涨跌幅")),
                "float_market_cap": _cap_to_yi(rec.get("流通市值")),
                "total_market_cap": _cap_to_yi(rec.get("总市值")),
                "turnover_pct": _opt_float(rec.get("换手率")),
                "amount": _amount_to_yi(rec.get("成交额")),
                "pe_dynamic": _opt_float(rec.get("市盈率-动态")),
                "pb": _opt_float(rec.get("市净率")),
                "volume_ratio": _opt_float(rec.get("量比")),
                "amplitude_pct": _opt_float(rec.get("振幅")),
                "change_5m_pct": _opt_float(rec.get("5分钟涨跌")),
                "speed_pct": _opt_float(rec.get("涨速")),
                "change_60d_pct": _opt_float(rec.get("60日涨跌幅")),
                "change_ytd_pct": _opt_float(rec.get("年初至今涨跌幅")),
                "industry": None,
            }
        )
    return rows


def count_stock_daily(conn, trade_date: date) -> int:
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM stock_daily WHERE trade_date = %s",
        (trade_date.isoformat(),),
    )
    row = cur.fetchone()
    return int(row[0] if row else 0)


_STOCK_DAILY_UPSERT_SQL = """
    INSERT INTO stock_daily (
      trade_date, code, name, industry, price, change_pct,
      float_market_cap, total_market_cap, turnover_pct, amount,
      pe_dynamic, pb, volume_ratio, amplitude_pct,
      change_5m_pct, speed_pct, change_60d_pct, change_ytd_pct,
      updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
      name = VALUES(name),
      industry = COALESCE(VALUES(industry), industry),
      price = VALUES(price),
      change_pct = VALUES(change_pct),
      float_market_cap = VALUES(float_market_cap),
      total_market_cap = VALUES(total_market_cap),
      turnover_pct = VALUES(turnover_pct),
      amount = VALUES(amount),
      pe_dynamic = VALUES(pe_dynamic),
      pb = VALUES(pb),
      volume_ratio = VALUES(volume_ratio),
      amplitude_pct = VALUES(amplitude_pct),
      change_5m_pct = VALUES(change_5m_pct),
      speed_pct = VALUES(speed_pct),
      change_60d_pct = VALUES(change_60d_pct),
      change_ytd_pct = VALUES(change_ytd_pct),
      updated_at = VALUES(updated_at)
"""


def _stock_daily_row_params(td_s: str, payload: list[dict[str, Any]], now: str) -> list[tuple[Any, ...]]:
    return [
        (
            td_s,
            r["code"],
            r["name"],
            r.get("industry"),
            r["price"],
            r["change_pct"],
            r["float_market_cap"],
            r["total_market_cap"],
            r["turnover_pct"],
            r["amount"],
            r["pe_dynamic"],
            r["pb"],
            r["volume_ratio"],
            r["amplitude_pct"],
            r["change_5m_pct"],
            r["speed_pct"],
            r["change_60d_pct"],
            r["change_ytd_pct"],
            now,
        )
        for r in payload
    ]


def _upsert_stock_daily(cur, td_s: str, payload: list[dict[str, Any]], *, now: str) -> None:
    chunk = fp_settings.stock_daily_db_chunk_size()
    params = _stock_daily_row_params(td_s, payload, now)
    for i in range(0, len(params), chunk):
        cur.executemany(_STOCK_DAILY_UPSERT_SQL, params[i : i + chunk])


def _prune_stock_daily_codes(cur, td_s: str, keep_codes: set[str]) -> int:
    cur.execute("SELECT code FROM stock_daily WHERE trade_date = %s", (td_s,))
    existing = {str(row[0]).zfill(6) for row in cur.fetchall()}
    to_remove = sorted(existing - keep_codes)
    if not to_remove:
        return 0
    chunk = fp_settings.stock_daily_db_chunk_size()
    removed = 0
    for i in range(0, len(to_remove), chunk):
        part = to_remove[i : i + chunk]
        placeholders = ",".join(["%s"] * len(part))
        cur.execute(
            f"DELETE FROM stock_daily WHERE trade_date = %s AND code IN ({placeholders})",
            (td_s, *part),
        )
        removed += len(part)
    return removed


def sync_stock_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    td = trade_date or _trade_date_today()
    td_s = td.isoformat()
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    job_id = None
    try:
        cur.execute(
            """
            INSERT INTO stock_daily_jobs (trade_date, started_at, ok)
            VALUES (%s, %s, 0)
            """,
            (td_s, _utc_now_iso()),
        )
        job_id = cur.lastrowid
        raw.commit()

        logger.info("stock_daily fetch start trade_date=%s job_id=%s", td_s, job_id)
        payload, source = fetch_a_share_spot()
        if len(payload) < _MIN_ROWS_OK:
            raise RuntimeError(f"stock spot rows too few: {len(payload)}")
        logger.info(
            "stock_daily fetch done trade_date=%s rows=%s source=%s",
            td_s,
            len(payload),
            source,
        )

        now = _utc_now_iso()
        keep_codes = {str(r["code"]).zfill(6) for r in payload}
        chunk = fp_settings.stock_daily_db_chunk_size()
        logger.info("stock_daily db write start trade_date=%s", td_s)
        _upsert_stock_daily(cur, td_s, payload, now=now)
        basic_n = upsert_stock_basic(cur, payload, now=now, chunk_size=chunk)
        pruned = _prune_stock_daily_codes(cur, td_s, keep_codes)
        cur.execute(
            """
            UPDATE stock_daily_jobs
            SET finished_at = %s, ok = 1, row_count = %s, error = NULL
            WHERE id = %s
            """,
            (now, len(payload), job_id),
        )
        raw.commit()
        logger.info(
            "stock_daily sync OK %s rows=%s basic=%s pruned=%s source=%s",
            td_s,
            len(payload),
            basic_n,
            pruned,
            source,
        )
        out: dict[str, Any] = {
            "ok": True,
            "trade_date": td_s,
            "count": len(payload),
            "job_id": job_id,
            "source": source,
        }
        from fund_platform.stock_industry_sync import run_after_stock_daily

        ind = run_after_stock_daily(td)
        out["industry_sync"] = ind
        return out
    except Exception as exc:  # noqa: BLE001
        err = f"{exc}\n{traceback.format_exc()}"
        logger.exception("sync_stock_daily failed")
        if job_id is not None:
            try:
                cur.execute(
                    """
                    UPDATE stock_daily_jobs
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


def ensure_stock_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    """Sync spot table for ``trade_date`` if missing or too few rows."""
    td = trade_date or _trade_date_today()
    engine = get_engine()
    raw = engine.raw_connection()
    try:
        n = count_stock_daily(raw, td)
        if n >= _MIN_ROWS_OK:
            return {"ok": True, "trade_date": td.isoformat(), "count": n, "skipped": True}
    finally:
        raw.close()
    return sync_stock_daily(td)
