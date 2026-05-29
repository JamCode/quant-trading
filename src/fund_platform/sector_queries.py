"""Read helpers for sector_fund_flow."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional

import pymysql.cursors

from fund_platform.units import amount_to_yi

_CUMULATIVE_PERIOD_RE = re.compile(r"^近(\d+)日累计$")


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


_FLOW_YI_KEYS = frozenset({"net_amt", "inflow_amt", "outflow_amt", "float_market_cap"})


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat() if isinstance(v, date) else v.strftime("%Y-%m-%d %H:%M:%S")
        elif k in _FLOW_YI_KEYS:
            out[k] = amount_to_yi(v)
        elif isinstance(v, float):
            out[k] = v
        else:
            out[k] = v
    return out


def parse_cumulative_days(period: str) -> Optional[int]:
    """Return N for period like ``近5日累计``, else None."""
    m = _CUMULATIVE_PERIOD_RE.match((period or "").strip())
    if not m:
        return None
    n = int(m.group(1))
    return n if n >= 2 else None


def is_cumulative_period(period: str) -> bool:
    return parse_cumulative_days(period) is not None


def _date_str(d: Any) -> str:
    if isinstance(d, date):
        return d.isoformat()
    return str(d)[:10]


def _list_trade_dates(
    conn,
    *,
    period: str,
    end_date: str,
    count: int,
) -> list[str]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT DISTINCT trade_date AS d
        FROM sector_fund_flow
        WHERE period = %s AND trade_date <= %s
        ORDER BY trade_date DESC
        LIMIT %s
        """,
        (period.strip(), end_date, max(1, count)),
    )
    rows = cur.fetchall()
    dates = [_date_str(r["d"]) for r in rows if r.get("d")]
    dates.reverse()
    return dates


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


def query_sector_flow_cumulative(
    conn,
    *,
    trade_date: Optional[str],
    days: int,
    sort: str = "net_desc",
    limit: int = 90,
) -> tuple[list[dict[str, Any]], Optional[str], dict[str, Any]]:
    """Sum daily ``即时`` snapshots over the last ``days`` stored trade dates."""
    base_period = "即时"
    td = trade_date or latest_trade_date(conn, base_period)
    if not td:
        return [], None, {}
    window = _list_trade_dates(conn, period=base_period, end_date=td, count=days)
    if not window:
        return [], td, {}

    order_sql = "net_amt DESC"
    if sort == "net_asc":
        order_sql = "net_amt ASC"
    elif sort == "inflow_desc":
        order_sql = "inflow_amt DESC"
    elif sort == "outflow_desc":
        order_sql = "outflow_amt DESC"

    lim = max(1, min(limit, 200))
    placeholders = ",".join(["%s"] * len(window))
    cur = _cursor(conn)
    cur.execute(
        f"""
        SELECT agg.industry,
               agg.inflow_amt,
               agg.outflow_amt,
               agg.net_amt,
               agg.day_count,
               lat.industry_index,
               lat.change_pct,
               lat.float_market_cap,
               lat.company_count,
               lat.leader_stock,
               lat.leader_change_pct,
               lat.leader_price,
               lat.updated_at
        FROM (
            SELECT industry,
                   SUM(inflow_amt) AS inflow_amt,
                   SUM(outflow_amt) AS outflow_amt,
                   SUM(net_amt) AS net_amt,
                   COUNT(DISTINCT trade_date) AS day_count
            FROM sector_fund_flow
            WHERE period = %s AND trade_date IN ({placeholders})
            GROUP BY industry
        ) agg
        LEFT JOIN sector_fund_flow lat
          ON lat.trade_date = %s
         AND lat.period = %s
         AND lat.industry = agg.industry
        ORDER BY {order_sql}
        LIMIT %s
        """,
        [base_period, *window, td, base_period, lim],
    )
    rows = [_serialize_row(dict(r)) for r in cur.fetchall()]
    meta = {
        "start_date": window[0],
        "end_date": window[-1],
        "days_requested": days,
        "days_actual": len(window),
    }
    return rows, td, meta


def query_sector_industry_history(
    conn,
    *,
    industry: str,
    trade_date: Optional[str],
    limit: int = 20,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    """Daily ``即时`` net flow points for one industry (ascending by date)."""
    period = "即时"
    name = industry.strip()
    td = trade_date or latest_trade_date(conn, period)
    if not td:
        return [], None
    lim = max(1, min(limit, 60))
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT trade_date, net_amt, inflow_amt, outflow_amt, change_pct
        FROM sector_fund_flow
        WHERE industry = %s AND period = %s AND trade_date <= %s
        ORDER BY trade_date DESC
        LIMIT %s
        """,
        (name, period, td, lim),
    )
    rows = [_serialize_row(dict(r)) for r in cur.fetchall()]
    rows.reverse()
    return rows, td


def query_sector_flow(
    conn,
    *,
    trade_date: Optional[str],
    period: str,
    sort: str = "net_desc",
    limit: int = 90,
) -> tuple[list[dict[str, Any]], Optional[str]]:
    cum_days = parse_cumulative_days(period)
    if cum_days:
        rows, td, _ = query_sector_flow_cumulative(
            conn,
            trade_date=trade_date,
            days=cum_days,
            sort=sort,
            limit=limit,
        )
        return rows, td

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
    cum_days = parse_cumulative_days(period)
    if cum_days:
        rows, td, _ = query_sector_flow_cumulative(
            conn,
            trade_date=trade_date,
            days=cum_days,
            sort="net_desc",
            limit=500,
        )
        for row in rows:
            if row.get("industry") == industry.strip():
                out = dict(row)
                out["trade_date"] = td
                out["period"] = period
                return out, td
        return None, td

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
