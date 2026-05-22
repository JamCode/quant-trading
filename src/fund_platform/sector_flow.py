"""Daily A-share industry sector fund flow (AkShare → MySQL)."""

from __future__ import annotations

import logging
import time
import traceback
from datetime import date, datetime, timezone
from typing import Any, Optional

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine

logger = logging.getLogger(__name__)

_PERIOD_COLUMN_MAP = {
    "即时": {
        "change": "行业-涨跌幅",
        "leader_chg": "领涨股-涨跌幅",
        "leader_price": "当前价",
    },
    "3日排行": {
        "change": "阶段涨跌幅",
        "leader_chg": None,
        "leader_price": None,
    },
    "5日排行": {
        "change": "阶段涨跌幅",
        "leader_chg": None,
        "leader_price": None,
    },
    "10日排行": {
        "change": "阶段涨跌幅",
        "leader_chg": None,
        "leader_price": None,
    },
    "20日排行": {
        "change": "阶段涨跌幅",
        "leader_chg": None,
        "leader_price": None,
    },
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _trade_date_today() -> date:
    return datetime.now().date()


def _parse_amount(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in ("-", "--", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _normalize_row(period: str, rec: dict[str, Any]) -> Optional[dict[str, Any]]:
    industry = str(rec.get("行业", "")).strip()
    if not industry:
        return None
    cols = _PERIOD_COLUMN_MAP.get(period, _PERIOD_COLUMN_MAP["即时"])
    change_val = rec.get(cols["change"], "")
    leader_chg = ""
    leader_price = ""
    if cols["leader_chg"]:
        leader_chg = str(rec.get(cols["leader_chg"], "") or "").strip()
    if cols["leader_price"]:
        leader_price = str(rec.get(cols["leader_price"], "") or "").strip()
    return {
        "industry": industry,
        "industry_index": str(rec.get("行业指数", "") or "").strip(),
        "change_pct": str(change_val or "").strip(),
        "inflow_amt": _parse_amount(rec.get("流入资金")),
        "outflow_amt": _parse_amount(rec.get("流出资金")),
        "net_amt": _parse_amount(rec.get("净额")),
        "company_count": _parse_int(rec.get("公司家数")),
        "leader_stock": str(rec.get("领涨股", "") or "").strip(),
        "leader_change_pct": leader_chg,
        "leader_price": leader_price,
    }


def fetch_sector_flow_em(period: str) -> list[dict[str, Any]]:
    import akshare as ak

    df = ak.stock_fund_flow_industry(symbol=period)
    if df is None or df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        row = _normalize_row(period, rec)
        if row:
            rows.append(row)
    return rows


def sync_sector_fund_flow_for_period(
    cur,
    trade_date: date,
    period: str,
) -> dict[str, Any]:
    job_id = None
    td = trade_date.isoformat()
    try:
        cur.execute(
            """
            INSERT INTO sector_flow_jobs (trade_date, period, started_at, ok)
            VALUES (%s, %s, %s, 0)
            """,
            (td, period, _utc_now_iso()),
        )
        job_id = cur.lastrowid

        raw_rows = fetch_sector_flow_em(period)
        by_industry: dict[str, dict[str, Any]] = {}
        for row in raw_rows:
            by_industry[row["industry"]] = row
        payload = list(by_industry.values())
        now = _utc_now_iso()
        cur.execute(
            "DELETE FROM sector_fund_flow WHERE trade_date = %s AND period = %s",
            (td, period),
        )
        if payload:
            params = [
                (
                    td,
                    period,
                    r["industry"],
                    r["industry_index"],
                    r["change_pct"],
                    r["inflow_amt"],
                    r["outflow_amt"],
                    r["net_amt"],
                    r["company_count"],
                    r["leader_stock"],
                    r["leader_change_pct"],
                    r["leader_price"],
                    now,
                )
                for r in payload
            ]
            cur.executemany(
                """
                INSERT INTO sector_fund_flow (
                  trade_date, period, industry, industry_index, change_pct,
                  inflow_amt, outflow_amt, net_amt, company_count,
                  leader_stock, leader_change_pct, leader_price, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                params,
            )

        cur.execute(
            """
            UPDATE sector_flow_jobs
            SET finished_at = %s, ok = 1, row_count = %s, error = NULL
            WHERE id = %s
            """,
            (_utc_now_iso(), len(payload), job_id),
        )
        return {"ok": True, "period": period, "count": len(payload), "job_id": job_id}
    except Exception as exc:  # noqa: BLE001
        err = f"{exc}\n{traceback.format_exc()}"
        logger.exception("sector flow failed period=%s", period)
        if job_id is not None:
            cur.execute(
                """
                UPDATE sector_flow_jobs
                SET finished_at = %s, ok = 0, row_count = NULL, error = %s
                WHERE id = %s
                """,
                (_utc_now_iso(), err[:4000], job_id),
            )
        return {"ok": False, "period": period, "error": str(exc), "job_id": job_id}


def sync_sector_fund_flow_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    """Pull all configured periods for ``trade_date`` (default: today)."""
    td = trade_date or _trade_date_today()
    periods = fp_settings.sector_flow_periods()
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    results: list[dict[str, Any]] = []
    try:
        period_delay = fp_settings.sector_flow_period_delay_sec()
        for i, period in enumerate(periods):
            if i > 0 and period_delay > 0:
                time.sleep(period_delay)
            logger.info("Sector fund flow sync %s %s", td, period)
            results.append(sync_sector_fund_flow_for_period(cur, td, period))
        raw.commit()
        ok = all(r.get("ok") for r in results)
        total = sum(int(r.get("count") or 0) for r in results)
        out: dict[str, Any] = {
            "ok": ok,
            "trade_date": td.isoformat(),
            "periods": results,
            "total_rows": total,
        }
        if ok:
            from fund_platform.sector_market_cap import run_after_sector_flow

            cap_result = run_after_sector_flow(td)
            out["market_cap"] = cap_result
            if not cap_result.get("ok") and not cap_result.get("skipped"):
                out["ok"] = False
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_sector_fund_flow_daily failed")
        try:
            raw.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(exc), "trade_date": td.isoformat(), "periods": results}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()
