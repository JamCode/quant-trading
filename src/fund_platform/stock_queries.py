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

STOCK_BOARD_OPTIONS: list[tuple[str, str]] = [
    ("sh", "沪市"),
    ("kcb", "科创板"),
    ("sz", "深市"),
    ("cyb", "创业板"),
    ("bj", "北交所"),
]

_STOCK_BOARDS = frozenset(b for b, _ in STOCK_BOARD_OPTIONS)


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


def normalize_stock_board(board: Optional[str]) -> Optional[str]:
    if not board or not str(board).strip():
        return None
    b = str(board).strip().lower()
    return b if b in _STOCK_BOARDS else None


def board_filter_sql(board: Optional[str], *, alias: str = "sd") -> str:
    """SQL AND fragment for A-share board (code prefix rules).

    Literal % in LIKE patterns must be doubled for pymysql parameter binding.
    """
    b = normalize_stock_board(board)
    if not b:
        return ""
    col = f"{alias}.code"
    if b == "sh":
        return (
            f" AND ({col} LIKE '60%%' AND {col} NOT LIKE '688%%' AND {col} NOT LIKE '689%%')"
        )
    if b == "kcb":
        return f" AND ({col} LIKE '688%%' OR {col} LIKE '689%%')"
    if b == "sz":
        return f" AND ({col} LIKE '00%%' OR {col} LIKE '001%%' OR {col} LIKE '002%%')"
    if b == "cyb":
        return f" AND {col} LIKE '30%%'"
    if b == "bj":
        return f" AND ({col} LIKE '4%%' OR {col} LIKE '8%%' OR {col} LIKE '92%%')"
    return ""


def industry_filter_ready(conn, *, trade_date: Optional[str] = None) -> bool:
    """True when code↔industry mapping exists for filtering the stock list."""
    td = trade_date or latest_stock_daily_date(conn)
    if not td:
        return False
    if latest_sector_constituent_date(conn, on_or_before=td):
        return True
    cur = _cursor(conn)
    cur.execute(
        "SELECT 1 AS ok FROM stock_ths_industry WHERE trade_date = %s LIMIT 1",
        (td,),
    )
    return cur.fetchone() is not None


def _distinct_industries(
    cur,
    table: str,
    *,
    trade_date: str,
    limit: int,
) -> list[str]:
    cur.execute(
        f"""
        SELECT DISTINCT industry
        FROM {table}
        WHERE trade_date = %s AND industry IS NOT NULL AND industry != ''
        ORDER BY industry
        LIMIT %s
        """,
        (trade_date, limit),
    )
    return [str(r["industry"]) for r in cur.fetchall() if r.get("industry")]


def list_stock_industry_options(
    conn,
    *,
    trade_date: Optional[str] = None,
    limit: int = 500,
) -> list[str]:
    """Industry names for UI: constituent map, then sti, then sector fund-flow."""
    td = trade_date or latest_stock_daily_date(conn)
    if not td:
        return []
    lim = max(1, min(limit, 1000))
    cur = _cursor(conn)
    cd = latest_sector_constituent_date(conn, on_or_before=td)
    if cd:
        out = _distinct_industries(cur, "sector_industry_constituent", trade_date=cd, limit=lim)
        if out:
            return out
    out = _distinct_industries(cur, "stock_ths_industry", trade_date=td, limit=lim)
    if out:
        return out
    cur.execute(
        """
        SELECT DISTINCT industry
        FROM sector_fund_flow
        WHERE industry IS NOT NULL AND industry != ''
        ORDER BY industry
        LIMIT %s
        """,
        (lim,),
    )
    return [str(r["industry"]) for r in cur.fetchall() if r.get("industry")]


def _industry_filter_sql(
    conn,
    *,
    trade_date: str,
    industry: str,
) -> tuple[str, list[Any]]:
    ind = industry.strip()
    if not ind:
        return "", []
    cd = latest_sector_constituent_date(conn, on_or_before=trade_date)
    if cd:
        return (
            """
          AND EXISTS (
            SELECT 1 FROM sector_industry_constituent c
            WHERE c.trade_date = %s AND c.code = sd.code AND c.industry = %s
          )
        """,
            [cd, ind],
        )
    cur = _cursor(conn)
    cur.execute(
        "SELECT 1 AS ok FROM stock_ths_industry WHERE trade_date = %s LIMIT 1",
        (trade_date,),
    )
    if cur.fetchone():
        return (
            """
          AND EXISTS (
            SELECT 1 FROM stock_ths_industry sti
            WHERE sti.trade_date = sd.trade_date
              AND sti.code = sd.code
              AND sti.industry = %s
          )
        """,
            [ind],
        )
    return " AND 1=0", []


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
    board: Optional[str] = None,
    industry: Optional[str] = None,
    sort: str = "change_pct",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    sort_col = _STOCK_LIST_SORT.get(sort, "change_pct")
    direction = "ASC" if order.lower() == "asc" else "DESC"
    where = "WHERE sd.trade_date = %s"
    params: list[Any] = [trade_date]
    if q and q.strip():
        like = f"%{q.strip()}%"
        where += " AND (sd.code LIKE %s OR sd.name LIKE %s)"
        params.extend([like, like])
    where += board_filter_sql(board, alias="sd")
    ind_sql, ind_params = _industry_filter_sql(conn, trade_date=trade_date, industry=industry or "")
    where += ind_sql
    params.extend(ind_params)
    cur = _cursor(conn)
    cur.execute(f"SELECT COUNT(*) AS c FROM stock_daily sd {where}", params)
    total = int(cur.fetchone()["c"])
    lim = max(1, min(limit, 200))
    off = max(0, offset)
    cur.execute(
        f"""
        SELECT sd.code, sd.name, sd.price, sd.change_pct, sd.float_market_cap, sd.total_market_cap,
               sd.turnover_pct, sd.amount, sd.pe_dynamic, sd.pb, sd.change_60d_pct, sd.change_ytd_pct
        FROM stock_daily sd
        {where}
        ORDER BY sd.{sort_col} IS NULL, sd.{sort_col} {direction}, sd.code ASC
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


def latest_sector_constituent_date(
    conn,
    *,
    on_or_before: Optional[str] = None,
) -> Optional[str]:
    """Latest sector_industry_constituent snapshot date (optionally capped)."""
    cur = _cursor(conn)
    if on_or_before:
        cur.execute(
            """
            SELECT MAX(trade_date) AS d
            FROM sector_industry_constituent
            WHERE trade_date <= %s
            """,
            (on_or_before.strip(),),
        )
    else:
        cur.execute("SELECT MAX(trade_date) AS d FROM sector_industry_constituent")
    row = cur.fetchone()
    if not row or not row.get("d"):
        return None
    d = row["d"]
    return d.isoformat()[:10] if hasattr(d, "isoformat") else str(d)[:10]


def query_industry_constituents_from_db(
    conn,
    *,
    industry: str,
    trade_date: str,
) -> Optional[dict[str, Any]]:
    """Constituent codes from latest DB snapshot; quotes from ``trade_date`` stock_daily."""
    quote_date = trade_date.strip()
    constituent_date = latest_sector_constituent_date(conn, on_or_before=quote_date)
    if not constituent_date:
        return None

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
          ON sd.trade_date = %s AND sd.code = c.code
        WHERE c.trade_date = %s AND c.industry = %s
        ORDER BY sd.change_pct IS NULL, sd.change_pct DESC
        """,
        (quote_date, constituent_date, industry.strip()),
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
        "trade_date": quote_date,
        "constituent_date": constituent_date,
        "count": len(items),
        "items": items,
        "float_market_cap_sum": round(sum(caps), 2) if caps else None,
        "float_market_cap_missing": missing_cap,
        "source": "db",
    }
