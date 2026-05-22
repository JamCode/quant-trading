"""Dashboard: sector fund flow + funds linked by industry exposure."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import pymysql.cursors

from fund_platform import settings as fp_settings
from fund_platform import sector_queries


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat() if isinstance(v, date) else v.strftime("%Y-%m-%d %H:%M:%S")
        else:
            out[k] = v
    return out


def latest_exposure_report_date(conn) -> Optional[str]:
    cur = _cursor(conn)
    cur.execute("SELECT MAX(report_date) AS rd FROM fund_industry_exposure")
    row = cur.fetchone()
    if not row or not row.get("rd"):
        return None
    return str(row["rd"])


def exposure_pipeline_ready(conn) -> bool:
    """True when fund_industry_exposure has at least one row."""
    cur = _cursor(conn)
    cur.execute("SELECT 1 FROM fund_industry_exposure LIMIT 1")
    return cur.fetchone() is not None


def industry_options_from_flow(
    conn,
    *,
    period: str,
    trade_date: Optional[str],
    top_in: list[dict[str, Any]],
    top_out: list[dict[str, Any]],
) -> list[str]:
    """Ordered industry names for dashboard selector (inflow then outflow tops)."""
    seen: set[str] = set()
    ordered: list[str] = []
    for rows in (top_in, top_out):
        for r in rows:
            name = str(r.get("industry") or "").strip()
            if name and name not in seen:
                seen.add(name)
                ordered.append(name)
    if ordered:
        return ordered
    rows, _ = sector_queries.query_sector_flow(
        conn, trade_date=trade_date, period=period, sort="net_desc", limit=30
    )
    return [str(r.get("industry") or "").strip() for r in rows if r.get("industry")]


def sector_flow_top(
    conn,
    *,
    period: str,
    trade_date: Optional[str] = None,
    limit: int = 10,
    sort: str = "net_desc",
) -> tuple[list[dict[str, Any]], Optional[str]]:
    rows, td = sector_queries.query_sector_flow(
        conn,
        trade_date=trade_date,
        period=period,
        sort=sort,
        limit=limit,
    )
    return rows, td


def sector_industry_summary(
    conn,
    *,
    industry: str,
    period: str,
    trade_date: Optional[str] = None,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    return sector_queries.query_sector_industry(
        conn,
        industry=industry,
        trade_date=trade_date,
        period=period,
    )


def funds_for_industry(
    conn,
    *,
    industry: str,
    min_weight_pct: Optional[float] = None,
    report_date: Optional[str] = None,
    limit: int = 20,
    sort: str = "return_1y",
) -> tuple[list[dict[str, Any]], Optional[str], bool]:
    """
    Returns (rows, report_date, has_exposure_data).
    sort: return_1y | daily_pct | weight_pct
    """
    cur = _cursor(conn)
    rd = report_date or latest_exposure_report_date(conn)
    pipeline_ready = exposure_pipeline_ready(conn)
    if not rd:
        return [], None, pipeline_ready

    min_w = min_weight_pct if min_weight_pct is not None else fp_settings.fund_exposure_min_pct()

    order_sql = "e.weight_pct DESC"
    if sort == "daily_pct":
        order_sql = "CAST(NULLIF(REPLACE(f.daily_pct, '%', ''), '') AS DECIMAL(12,4)) DESC"
    elif sort == "return_1y":
        order_sql = "m.return_1y IS NULL, m.return_1y DESC"
    elif sort == "return_3m":
        order_sql = "m.return_3m IS NULL, m.return_3m DESC"

    cur.execute(
        f"""
        SELECT
          f.code,
          f.short_name,
          f.fund_type,
          f.daily_pct,
          f.subscribe_status,
          f.redeem_status,
          e.weight_pct,
          e.stock_count,
          e.report_date,
          m.return_1m,
          m.return_3m,
          m.return_1y
        FROM fund_industry_exposure e
        INNER JOIN funds f ON f.code = e.fund_code
        LEFT JOIN fund_metrics m ON m.fund_code = e.fund_code
        WHERE e.industry = %s
          AND e.report_date = %s
          AND e.weight_pct >= %s
        ORDER BY {order_sql}
        LIMIT %s
        """,
        (industry.strip(), rd, min_w, max(1, min(limit, 100))),
    )
    rows = [_serialize_row(dict(r)) for r in cur.fetchall()]
    return rows, rd, pipeline_ready


def default_focus_industry(conn, *, period: str, trade_date: Optional[str]) -> Optional[str]:
    rows, _ = sector_flow_top(conn, period=period, trade_date=trade_date, limit=1, sort="net_desc")
    if rows:
        return str(rows[0].get("industry") or "")
    rows_all, _ = sector_queries.query_sector_flow(conn, trade_date=trade_date, period=period, limit=1)
    if rows_all:
        return str(rows_all[0].get("industry") or "")
    return None
