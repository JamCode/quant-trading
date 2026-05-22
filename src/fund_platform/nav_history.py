"""Lazy-loaded per-fund NAV history (AkShare EM → MySQL cache)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import pymysql.cursors

logger = logging.getLogger(__name__)

_BATCH = 500


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def history_row_count(conn, code: str) -> int:
    cur = _cursor(conn)
    cur.execute(
        "SELECT COUNT(*) AS c FROM fund_nav_history WHERE code = %s",
        (code.strip(),),
    )
    return int(cur.fetchone()["c"])


def fetch_nav_history_em(code: str) -> list[dict[str, str]]:
    import akshare as ak

    df = ak.fund_open_fund_info_em(symbol=code.strip(), indicator="单位净值走势")
    if df is None or df.empty:
        return []
    rows: list[dict[str, str]] = []
    for rec in df.to_dict("records"):
        d = str(rec.get("净值日期", "")).strip()[:10]
        if not d:
            continue
        rows.append(
            {
                "nav_date": d,
                "nav_unit": "" if rec.get("单位净值") is None else str(rec.get("单位净值")).strip(),
                "daily_pct": "" if rec.get("日增长率") is None else str(rec.get("日增长率")).strip(),
            }
        )
    return rows


def replace_nav_history(conn, code: str, rows: list[dict[str, str]]) -> int:
    sym = code.strip()
    cur = _cursor(conn)
    cur.execute("DELETE FROM fund_nav_history WHERE code = %s", (sym,))
    if not rows:
        return 0
    params = [(sym, r["nav_date"], r["nav_unit"], r["daily_pct"]) for r in rows]
    for i in range(0, len(params), _BATCH):
        chunk = params[i : i + _BATCH]
        cur.executemany(
            """
            INSERT INTO fund_nav_history (code, nav_date, nav_unit, daily_pct)
            VALUES (%s, %s, %s, %s)
            """,
            chunk,
        )
    return len(params)


def query_nav_history(
    conn,
    code: str,
    *,
    limit: int = 200,
    offset: int = 0,
    order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    sym = code.strip()
    cur = _cursor(conn)
    cur.execute("SELECT COUNT(*) AS c FROM fund_nav_history WHERE code = %s", (sym,))
    total = int(cur.fetchone()["c"])
    direction = "DESC" if order.lower() != "asc" else "ASC"
    lim = max(1, min(limit, 2000))
    off = max(0, offset)
    cur.execute(
        f"""
        SELECT nav_date, nav_unit, daily_pct
        FROM fund_nav_history
        WHERE code = %s
        ORDER BY nav_date {direction}
        LIMIT %s OFFSET %s
        """,
        (sym, lim, off),
    )
    items = []
    for row in cur.fetchall():
        nd = row["nav_date"]
        if isinstance(nd, date):
            nd = nd.isoformat()
        items.append(
            {
                "nav_date": str(nd),
                "nav_unit": row["nav_unit"] or "",
                "daily_pct": row["daily_pct"] or "",
            }
        )
    return items, total


def ensure_nav_history(
    conn,
    code: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """Return cached rows; fetch from AkShare and persist when missing or ``force``."""
    sym = code.strip()
    cached = history_row_count(conn, sym)
    source = "cache"
    if cached == 0 or force:
        logger.info("Fetching NAV history for %s (force=%s)", sym, force)
        rows = fetch_nav_history_em(sym)
        if not rows:
            return {
                "code": sym,
                "source": "empty",
                "total": 0,
                "fetched_at": _utc_now(),
            }
        replace_nav_history(conn, sym, rows)
        source = "akshare"
        cached = len(rows)
    return {
        "code": sym,
        "source": source,
        "total": cached,
        "fetched_at": _utc_now(),
    }
