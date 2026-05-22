"""Aggregate fund industry exposure from holdings + stock_ths_industry."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from fund_platform.db import get_engine

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _latest_stock_map_date(cur) -> Optional[str]:
    cur.execute("SELECT MAX(trade_date) AS d FROM stock_ths_industry")
    row = cur.fetchone()
    if not row:
        return None
    d = row[0] if not isinstance(row, dict) else row.get("d")
    if not d:
        return None
    return d.isoformat() if hasattr(d, "isoformat") else str(d)


def _latest_report_date(cur) -> Optional[str]:
    cur.execute("SELECT MAX(report_date) AS rd FROM fund_holdings")
    row = cur.fetchone()
    if not row:
        return None
    rd = row[0] if not isinstance(row, dict) else row.get("rd")
    return str(rd) if rd else None


def rebuild_fund_industry_exposure(
    *,
    report_date: Optional[str] = None,
    stock_map_date: Optional[str] = None,
) -> dict[str, Any]:
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        rd = report_date or _latest_report_date(cur)
        td = stock_map_date or _latest_stock_map_date(cur)
        if not rd:
            return {"ok": False, "error": "no fund_holdings report_date"}
        if not td:
            return {"ok": False, "error": "no stock_ths_industry trade_date (run rebuild_stock_ths_industry)"}

        cur.execute(
            "DELETE FROM fund_industry_exposure WHERE report_date = %s",
            (rd,),
        )
        cur.execute(
            """
            INSERT INTO fund_industry_exposure (
              fund_code, report_date, industry, weight_pct, stock_count, updated_at
            )
            SELECT
              h.fund_code,
              h.report_date,
              s.industry,
              ROUND(SUM(h.weight_pct), 4) AS weight_pct,
              COUNT(*) AS stock_count,
              %s
            FROM fund_holdings h
            INNER JOIN stock_ths_industry s
              ON s.code = h.stock_code AND s.trade_date = %s
            WHERE h.report_date = %s
              AND h.weight_pct IS NOT NULL
              AND h.weight_pct > 0
            GROUP BY h.fund_code, h.report_date, s.industry
            """,
            (_utc_now_iso(), td, rd),
        )
        count = cur.rowcount
        raw.commit()
        logger.info(
            "fund_industry_exposure rebuilt report=%s map=%s rows=%s",
            rd,
            td,
            count,
        )
        return {
            "ok": True,
            "report_date": rd,
            "stock_map_date": td,
            "count": count,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("rebuild_fund_industry_exposure failed")
        try:
            raw.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()
