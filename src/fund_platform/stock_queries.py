"""Read stock_daily joined with industry constituents."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import pymysql.cursors

from fund_platform.stock_price_history import normalize_stock_code
from fund_platform.units import amount_to_yi

_STOCK_YI_KEYS = frozenset({"float_market_cap", "total_market_cap", "amount"})

_STOCK_LIST_SORT: dict[str, str] = {
    "code": "code",
    "name": "name",
    "price": "price",
    "change_pct": "change_pct",
    "float_market_cap": "float_market_cap",
    "turnover_pct": "turnover_pct",
    "amount": "amount",
    "pe_dynamic": "pe_dynamic",
    "pb": "pb",
    "change_60d_pct": "change_60d_pct",
    "change_ytd_pct": "change_ytd_pct",
}

STOCK_SORT_OPTIONS: list[tuple[str, str]] = [
    ("change_pct", "涨跌幅"),
    ("code", "代码"),
    ("name", "名称"),
    ("price", "现价"),
    ("float_market_cap", "流通市值"),
    ("amount", "成交额"),
    ("turnover_pct", "换手率"),
    ("pe_dynamic", "市盈率"),
    ("pb", "市净率"),
    ("change_60d_pct", "60日涨跌"),
    ("change_ytd_pct", "年初至今"),
]


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat() if isinstance(v, date) else v.strftime("%Y-%m-%d %H:%M:%S")
        elif k in _STOCK_YI_KEYS:
            out[k] = amount_to_yi(v)
        else:
            out[k] = v
    return out


def latest_stock_daily_date(conn) -> Optional[str]:
    cur = _cursor(conn)
    cur.execute("SELECT MAX(trade_date) AS d FROM stock_daily")
    row = cur.fetchone()
    if not row or not row["d"]:
        return None
    d = row["d"]
    return d.isoformat() if isinstance(d, date) else str(d)


def list_stock_daily_dates(conn, *, limit: int = 30) -> list[str]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT DISTINCT trade_date AS d FROM stock_daily
        ORDER BY trade_date DESC
        LIMIT %s
        """,
        (max(1, min(limit, 90)),),
    )
    out: list[str] = []
    for row in cur.fetchall():
        d = row["d"]
        if isinstance(d, date):
            out.append(d.isoformat())
        elif d:
            out.append(str(d)[:10])
    return out


def query_stock_list(
    conn,
    *,
    trade_date: str,
    q: Optional[str] = None,
    sort: str = "change_pct",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    sort_col = _STOCK_LIST_SORT.get(sort, "change_pct")
    direction = "ASC" if order.lower() == "asc" else "DESC"
    where = "WHERE trade_date = %s"
    params: list[Any] = [trade_date]
    if q and q.strip():
        like = f"%{q.strip()}%"
        where += " AND (code LIKE %s OR name LIKE %s)"
        params.extend([like, like])
    cur = _cursor(conn)
    cur.execute(f"SELECT COUNT(*) AS c FROM stock_daily {where}", params)
    total = int(cur.fetchone()["c"])
    lim = max(1, min(limit, 200))
    off = max(0, offset)
    cur.execute(
        f"""
        SELECT code, name, price, change_pct, float_market_cap, total_market_cap,
               turnover_pct, amount, pe_dynamic, pb, change_60d_pct, change_ytd_pct
        FROM stock_daily
        {where}
        ORDER BY {sort_col} IS NULL, {sort_col} {direction}, code ASC
        LIMIT %s OFFSET %s
        """,
        [*params, lim, off],
    )
    items = [_serialize_row(r) for r in cur.fetchall()]
    return items, total


def query_stock_snapshot(
    conn,
    code: str,
    *,
    trade_date: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    sym = normalize_stock_code(code)
    if not sym:
        return None
    td = trade_date or latest_stock_daily_date(conn)
    if not td:
        return None
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT trade_date, code, name, price, change_pct, float_market_cap, total_market_cap,
               turnover_pct, amount, pe_dynamic, pb, volume_ratio, amplitude_pct,
               change_5m_pct, speed_pct, change_60d_pct, change_ytd_pct, updated_at
        FROM stock_daily
        WHERE trade_date = %s AND code = %s
        """,
        (td, sym),
    )
    row = cur.fetchone()
    if not row:
        return None
    return _serialize_row(row)


def query_stock_industries(
    conn,
    code: str,
    *,
    trade_date: Optional[str] = None,
) -> list[str]:
    sym = normalize_stock_code(code)
    if not sym:
        return []
    td = trade_date
    if not td:
        td = latest_stock_daily_date(conn)
    if not td:
        return []
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT DISTINCT industry
        FROM stock_ths_industry
        WHERE trade_date = %s AND code = %s
        ORDER BY industry
        """,
        (td, sym),
    )
    return [str(r["industry"]) for r in cur.fetchall() if r.get("industry")]


def query_industry_constituents_from_db(
    conn,
    *,
    industry: str,
    trade_date: str,
) -> Optional[dict[str, Any]]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT c.code,
               COALESCE(sd.name, '') AS name,
               sd.price,
               sd.change_pct,
               sd.float_market_cap,
               sd.total_market_cap,
               sd.turnover_pct,
               sd.amount,
               sd.pe_dynamic,
               sd.pb,
               sd.volume_ratio,
               sd.amplitude_pct,
               sd.change_5m_pct,
               sd.speed_pct,
               sd.change_60d_pct,
               sd.change_ytd_pct
        FROM sector_industry_constituent c
        LEFT JOIN stock_daily sd
          ON sd.trade_date = c.trade_date AND sd.code = c.code
        WHERE c.trade_date = %s AND c.industry = %s
        ORDER BY sd.change_pct IS NULL, sd.change_pct DESC
        """,
        (trade_date, industry.strip()),
    )
    rows = cur.fetchall()
    if not rows:
        return None

    items: list[dict[str, Any]] = []
    caps: list[float] = []
    missing_cap = 0
    for r in rows:
        cap = amount_to_yi(r.get("float_market_cap"))
        if cap is None:
            missing_cap += 1
        else:
            caps.append(float(cap))
        amount = amount_to_yi(r.get("amount"))

        def _f(key: str) -> Optional[float]:
            v = r.get(key)
            return float(v) if v is not None else None

        items.append(
            {
                "code": r["code"],
                "name": r.get("name") or "",
                "price": _f("price"),
                "change_pct": _f("change_pct"),
                "float_market_cap": cap,
                "total_market_cap": amount_to_yi(r.get("total_market_cap")),
                "turnover_pct": _f("turnover_pct"),
                "amount": amount,
                "pe_dynamic": _f("pe_dynamic"),
                "pb": _f("pb"),
                "volume_ratio": _f("volume_ratio"),
                "amplitude_pct": _f("amplitude_pct"),
                "change_5m_pct": _f("change_5m_pct"),
                "speed_pct": _f("speed_pct"),
                "change_60d_pct": _f("change_60d_pct"),
                "change_ytd_pct": _f("change_ytd_pct"),
            }
        )
    return {
        "industry": industry,
        "trade_date": trade_date,
        "count": len(items),
        "items": items,
        "float_market_cap_sum": round(sum(caps), 2) if caps else None,
        "float_market_cap_missing": missing_cap,
        "source": "db",
    }
