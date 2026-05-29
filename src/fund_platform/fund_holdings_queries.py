"""Reverse lookup: funds holding a stock (by code or name)."""

from __future__ import annotations

import re
from typing import Any, Optional

import pymysql.cursors

from fund_platform.fund_holdings_common import normalize_stock_code, normalize_stock_name


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def _search_tokens(q: str) -> tuple[str, list[str]]:
    """Return (mode, tokens). mode: code | name | mixed."""
    raw = q.strip()
    if not raw:
        return "empty", []
    if re.fullmatch(r"\d{6}", raw):
        return "code", [raw]
    if re.fullmatch(r"[A-Za-z0-9.\-]+", raw) and any(c.isalpha() for c in raw):
        return "code", [normalize_stock_code(raw)]
    parts = [p for p in re.split(r"[\s,，、]+", raw) if p.strip()]
    return "name", parts[:5] if parts else [raw]


def search_funds_holding_stock(
    conn,
    q: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int, str]:
    """
    Funds whose latest quarterly holding matches ``q`` (code or name substring).

    Returns (items, total, report_date_hint).
    """
    mode, tokens = _search_tokens(q)
    if mode == "empty":
        return [], 0, ""

    lim = max(1, min(int(limit), 200))
    off = max(0, int(offset))
    cur = _cursor(conn)

    cur.execute("SELECT MAX(report_date) AS rd FROM fund_holdings")
    global_rd = (cur.fetchone() or {}).get("rd")
    global_rd_s = str(global_rd) if global_rd else ""

    where_parts: list[str] = []
    params: list[Any] = []

    if mode == "code":
        code = tokens[0]
        where_parts.append(
            "(h.stock_code = %s OR UPPER(h.stock_code) = %s OR h.stock_name LIKE %s)"
        )
        params.extend([code, code, f"%{q.strip()}%"])
    else:
        name_clauses = []
        for t in tokens:
            name_clauses.append("(h.stock_name LIKE %s OR h.stock_code LIKE %s)")
            params.extend([f"%{t}%", f"%{normalize_stock_code(t)}%"])
        where_parts.append("(" + " OR ".join(name_clauses) + ")")

    where_sql = " AND ".join(where_parts)

    count_sql = f"""
        SELECT COUNT(DISTINCT h.fund_code) AS c
        FROM fund_holdings h
        INNER JOIN (
          SELECT fund_code, MAX(report_date) AS rd
          FROM fund_holdings
          GROUP BY fund_code
        ) latest ON latest.fund_code = h.fund_code AND latest.rd = h.report_date
        WHERE {where_sql}
        """
    cur.execute(count_sql, params)
    total = int((cur.fetchone() or {}).get("c") or 0)

    list_sql = f"""
        SELECT
          h.fund_code,
          f.short_name AS fund_name,
          f.fund_type,
          h.report_date,
          h.stock_code,
          h.stock_name,
          h.weight_pct
        FROM fund_holdings h
        INNER JOIN funds f ON f.code = h.fund_code
        INNER JOIN (
          SELECT fund_code, MAX(report_date) AS rd
          FROM fund_holdings
          GROUP BY fund_code
        ) latest ON latest.fund_code = h.fund_code AND latest.rd = h.report_date
        WHERE {where_sql}
        ORDER BY h.weight_pct DESC, h.fund_code ASC
        LIMIT %s OFFSET %s
        """
    cur.execute(list_sql, [*params, lim, off])
    items = [_serialize_row(dict(r)) for r in cur.fetchall()]
    return items, total, global_rd_s
