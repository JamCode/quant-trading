"""Read helpers for sector_fund_flow."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import pymysql.cursors


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat() if isinstance(v, date) else v.strftime("%Y-%m-%d %H:%M:%S")
        elif isinstance(v, float):
            out[k] = v
        else:
            out[k] = v
    return out


def latest_trade_date(conn, period: str) -> Optional[str]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT MAX(trade_date) AS d
        FROM sector_fund_flow
        WHERE period = %s
        """,
        (period.strip(),),
    )
    row = cur.fetchone()
    if not row or not row["d"]:
        return None
    d = row["d"]
    return d.isoformat() if isinstance(d, date) else str(d)


def query_sector_flow(
    conn,
    *,
    trade_date: Optional[str],
    period: str,
    sort: str = "net_desc",
    limit: int = 90,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    cur = _cursor(conn)
    period = period.strip()
    td = trade_date
    if not td:
        td = latest_trade_date(conn, period)
    if not td:
        return [], None

    order_sql = "net_amt DESC"
    if sort == "net_asc":
        order_sql = "net_amt ASC"
    elif sort == "inflow_desc":
        order_sql = "inflow_amt DESC"
    elif sort == "outflow_desc":
        order_sql = "outflow_amt DESC"

    lim = max(1, min(limit, 200))
    cur.execute(
        f"""
        SELECT trade_date, period, industry, industry_index, change_pct,
               inflow_amt, outflow_amt, net_amt, company_count, float_market_cap,
               leader_stock, leader_change_pct, leader_price, updated_at
        FROM sector_fund_flow
        WHERE trade_date = %s AND period = %s
        ORDER BY {order_sql}
        LIMIT %s
        """,
        (td, period, lim),
    )
    rows = [_serialize_row(dict(r)) for r in cur.fetchall()]
    return rows, td


def query_sector_industry(
    conn,
    *,
    industry: str,
    trade_date: Optional[str],
    period: str,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """Single industry row for the given date/period (latest date if omitted)."""
    cur = _cursor(conn)
    period = period.strip()
    name = industry.strip()
    td = trade_date
    if not td:
        td = latest_trade_date(conn, period)
    if not td:
        return None, None
    cur.execute(
        """
        SELECT trade_date, period, industry, industry_index, change_pct,
               inflow_amt, outflow_amt, net_amt, company_count, float_market_cap,
               leader_stock, leader_change_pct, leader_price, updated_at
        FROM sector_fund_flow
        WHERE trade_date = %s AND period = %s AND industry = %s
        LIMIT 1
        """,
        (td, period, name),
    )
    row = cur.fetchone()
    if not row:
        return None, td
    return _serialize_row(dict(row)), td


def latest_jobs_summary(conn, limit: int = 6) -> list[dict[str, Any]]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT trade_date, period, started_at, finished_at, row_count, ok, error
        FROM sector_flow_jobs
        ORDER BY id DESC
        LIMIT %s
        """,
        (max(1, limit),),
    )
    return [_serialize_row(dict(r)) for r in cur.fetchall()]
