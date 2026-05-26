"""Industry average PE from CNINFO 国证行业分类 (AkShare)."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine

logger = logging.getLogger(__name__)

_CNINFO_SYMBOL = "国证行业分类"
_SOURCE = "cninfo_gics"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
        if v != v:
            return None
        return round(v, 4)
    except (TypeError, ValueError):
        return None


def _opt_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_trade_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip().replace("/", "-")
    if len(s) >= 10:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def _date_to_cninfo(d: date) -> str:
    return d.strftime("%Y%m%d")


def fetch_industry_pe_cninfo_gics(query_date: date) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Fetch one-day snapshot; returns rows and optional error."""
    import akshare as ak

    q = _date_to_cninfo(query_date)
    try:
        df = ak.stock_industry_pe_ratio_cninfo(symbol=_CNINFO_SYMBOL, date=q)
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)
    if df is None or df.empty:
        return [], "empty response"
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        td = _parse_trade_date(rec.get("变动日期"))
        code = str(rec.get("行业编码") or "").strip()
        name = str(rec.get("行业名称") or "").strip()
        if not td or not code or not name:
            continue
        rows.append(
            {
                "trade_date": td.isoformat(),
                "industry_code": code,
                "industry_name": name,
                "industry_level": _opt_int(rec.get("行业层级")) or 0,
                "pe_weighted": _opt_float(rec.get("静态市盈率-加权平均")),
                "pe_median": _opt_float(rec.get("静态市盈率-中位数")),
                "pe_avg": _opt_float(rec.get("静态市盈率-算术平均")),
                "company_count": _opt_int(rec.get("公司数量")),
                "calc_company_count": _opt_int(rec.get("纳入计算公司数量")),
                "source": _SOURCE,
            }
        )
    return rows, None


def upsert_industry_pe_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = _utc_now_iso()
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        params = [
            (
                r["trade_date"],
                r["industry_code"],
                r["industry_name"],
                r["industry_level"],
                r.get("pe_weighted"),
                r.get("pe_median"),
                r.get("pe_avg"),
                r.get("company_count"),
                r.get("calc_company_count"),
                r.get("source", _SOURCE),
                now,
            )
            for r in rows
        ]
        cur.executemany(
            """
            INSERT INTO industry_pe_daily (
              trade_date, industry_code, industry_name, industry_level,
              pe_weighted, pe_median, pe_avg, company_count, calc_company_count,
              source, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              industry_name = VALUES(industry_name),
              industry_level = VALUES(industry_level),
              pe_weighted = VALUES(pe_weighted),
              pe_median = VALUES(pe_median),
              pe_avg = VALUES(pe_avg),
              company_count = VALUES(company_count),
              calc_company_count = VALUES(calc_company_count),
              source = VALUES(source),
              updated_at = VALUES(updated_at)
            """,
            params,
        )
        raw.commit()
        return len(params)
    except Exception:
        raw.rollback()
        raise
    finally:
        cur.close()
        raw.close()


def sync_industry_pe_cninfo_for_date(
    trade_date: date,
    *,
    delay_sec: float = 0,
) -> dict[str, Any]:
    rows, err = fetch_industry_pe_cninfo_gics(trade_date)
    if err:
        return {
            "ok": False,
            "trade_date": trade_date.isoformat(),
            "count": 0,
            "error": err,
        }
    if delay_sec > 0:
        time.sleep(delay_sec)
    n = upsert_industry_pe_rows(rows)
    return {"ok": n > 0, "trade_date": trade_date.isoformat(), "count": n}


def sync_industry_pe_cninfo_daily(
    trade_date: Optional[date] = None,
) -> dict[str, Any]:
    """Sync latest snapshot for ``trade_date`` (default: today)."""
    td = trade_date or datetime.now().date()
    delay = fp_settings.industry_pe_cninfo_request_delay_sec()
    res = sync_industry_pe_cninfo_for_date(td, delay_sec=0)
    if res.get("ok"):
        logger.info("industry_pe_cninfo ok date=%s count=%s", res["trade_date"], res["count"])
        return res
    # Retry a few prior calendar days (weekends / holidays)
    for back in range(1, 8):
        prev = td - timedelta(days=back)
        res = sync_industry_pe_cninfo_for_date(prev, delay_sec=delay)
        if res.get("ok"):
            res["note"] = f"used lag {back}d"
            logger.info(
                "industry_pe_cninfo ok date=%s count=%s (lag %sd)",
                res["trade_date"],
                res["count"],
                back,
            )
            return res
    logger.warning("industry_pe_cninfo failed: %s", res.get("error"))
    return res


def backfill_industry_pe_cninfo(
    *,
    start_date: date,
    end_date: date,
    delay_sec: Optional[float] = None,
) -> dict[str, Any]:
    """Iterate calendar days from start to end; skip days with no CNINFO data."""
    delay = (
        delay_sec
        if delay_sec is not None
        else fp_settings.industry_pe_cninfo_request_delay_sec()
    )
    ok_days = 0
    skipped = 0
    total_rows = 0
    errors: list[str] = []
    cur_day = start_date
    while cur_day <= end_date:
        res = sync_industry_pe_cninfo_for_date(cur_day, delay_sec=delay)
        if res.get("ok"):
            ok_days += 1
            total_rows += int(res.get("count") or 0)
        else:
            skipped += 1
            err = res.get("error") or "unknown"
            if len(errors) < 20:
                errors.append(f"{cur_day.isoformat()}: {err}")
        cur_day += timedelta(days=1)
    return {
        "ok": ok_days > 0,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "ok_days": ok_days,
        "skipped_days": skipped,
        "total_rows": total_rows,
        "errors_sample": errors,
    }
