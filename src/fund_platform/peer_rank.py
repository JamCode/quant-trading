"""Lazy-loaded peer rank trend (AkShare EM 同类排名走势 → MySQL)."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

import pymysql.cursors

logger = logging.getLogger(__name__)

_BATCH = 500
_INDICATOR = "同类排名走势"


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_rank(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("-", "--", "nan", "NaN"):
        return None
    try:
        n = int(float(s))
        return n if n > 0 else None
    except ValueError:
        return None


def peer_rank_row_count(conn, code: str) -> int:
    cur = _cursor(conn)
    cur.execute(
        "SELECT COUNT(*) AS c FROM fund_peer_rank WHERE code = %s",
        (code.strip(),),
    )
    return int(cur.fetchone()["c"])


def fetch_peer_rank_em(code: str) -> list[dict[str, Any]]:
    import akshare as ak

    df = ak.fund_open_fund_info_em(symbol=code.strip(), indicator=_INDICATOR)
    if df is None or df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        d = str(rec.get("报告日期", "")).strip()[:10]
        if not d:
            continue
        rows.append(
            {
                "rank_date": d,
                "rank_in_type": _parse_rank(rec.get("同类型排名-每日近三月排名")),
                "rank_total": _parse_rank(rec.get("总排名-每日近三月排名")),
            }
        )
    return rows


def replace_peer_rank(conn, code: str, rows: list[dict[str, Any]]) -> int:
    sym = code.strip()
    cur = _cursor(conn)
    cur.execute("DELETE FROM fund_peer_rank WHERE code = %s", (sym,))
    if not rows:
        return 0
    params = [
        (sym, r["rank_date"], r["rank_in_type"], r["rank_total"])
        for r in rows
    ]
    for i in range(0, len(params), _BATCH):
        chunk = params[i : i + _BATCH]
        cur.executemany(
            """
            INSERT INTO fund_peer_rank (code, rank_date, rank_in_type, rank_total)
            VALUES (%s, %s, %s, %s)
            """,
            chunk,
        )
    return len(params)


def query_peer_rank(
    conn,
    code: str,
    *,
    limit: int = 200,
    offset: int = 0,
    order: str = "desc",
) -> tuple[list[dict[str, Any]], int]:
    sym = code.strip()
    cur = _cursor(conn)
    cur.execute("SELECT COUNT(*) AS c FROM fund_peer_rank WHERE code = %s", (sym,))
    total = int(cur.fetchone()["c"])
    direction = "DESC" if order.lower() != "asc" else "ASC"
    lim = max(1, min(limit, 2000))
    off = max(0, offset)
    cur.execute(
        f"""
        SELECT rank_date, rank_in_type, rank_total
        FROM fund_peer_rank
        WHERE code = %s
        ORDER BY rank_date {direction}
        LIMIT %s OFFSET %s
        """,
        (sym, lim, off),
    )
    items: list[dict[str, Any]] = []
    for row in cur.fetchall():
        rd = row["rank_date"]
        if isinstance(rd, date):
            rd = rd.isoformat()
        items.append(
            {
                "rank_date": str(rd),
                "rank_in_type": row["rank_in_type"],
                "rank_total": row["rank_total"],
            }
        )
    return items, total


def ensure_peer_rank(
    conn,
    code: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    sym = code.strip()
    cached = peer_rank_row_count(conn, sym)
    source = "cache"
    if cached == 0 or force:
        logger.info("Fetching peer rank for %s (force=%s)", sym, force)
        rows = fetch_peer_rank_em(sym)
        if not rows:
            return {
                "code": sym,
                "source": "empty",
                "total": 0,
                "fetched_at": _utc_now(),
                "indicator": _INDICATOR,
            }
        replace_peer_rank(conn, sym, rows)
        source = "akshare"
        cached = len(rows)
    return {
        "code": sym,
        "source": source,
        "total": cached,
        "fetched_at": _utc_now(),
        "indicator": _INDICATOR,
    }
