"""East Money pingzhongdata swithSameType → MySQL (同类收益 Top5)."""

from __future__ import annotations

import ast
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

import pymysql.cursors
import requests

logger = logging.getLogger(__name__)

_PINGZHONG_URL = "http://fund.eastmoney.com/pingzhongdata/{code}.js"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://fund.eastmoney.com/",
}

# swithSameType: 5 rows aligned with East Money fund page tabs
PERIOD_KEYS: tuple[str, ...] = ("1w", "1m", "3m", "6m", "1y")
PERIOD_LABELS: dict[str, str] = {
    "1w": "近1周",
    "1m": "近1月",
    "3m": "近3月",
    "6m": "近6月",
    "1y": "近1年",
}

_SWITCH_RE = re.compile(r"var\s+swithSameType\s*=\s*(\[.*?\]);", re.DOTALL)


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_entry(raw: str) -> Optional[dict[str, Any]]:
    s = str(raw).strip()
    if not s:
        return None
    parts = s.split("_")
    if len(parts) < 3:
        return None
    peer_code = parts[0].strip()
    if not peer_code:
        return None
    try:
        return_pct = float(parts[-1])
    except ValueError:
        return_pct = None
    peer_name = "_".join(parts[1:-1]).strip()
    return {
        "peer_code": peer_code,
        "peer_name": peer_name,
        "return_pct": return_pct,
    }


def fetch_peer_same_type_em(code: str) -> list[dict[str, Any]]:
    sym = code.strip()
    url = _PINGZHONG_URL.format(code=sym)
    r = requests.get(url, headers=_HEADERS, timeout=30)
    r.raise_for_status()
    m = _SWITCH_RE.search(r.text)
    if not m:
        return []
    try:
        groups = ast.literal_eval(m.group(1))
    except (SyntaxError, ValueError) as exc:
        logger.warning("swithSameType parse failed for %s: %s", sym, exc)
        return []
    if not isinstance(groups, list):
        return []
    rows: list[dict[str, Any]] = []
    for idx, group in enumerate(groups):
        if idx >= len(PERIOD_KEYS):
            break
        if not isinstance(group, list):
            continue
        period = PERIOD_KEYS[idx]
        for pos, entry in enumerate(group[:5], start=1):
            parsed = _parse_entry(str(entry))
            if not parsed:
                continue
            rows.append(
                {
                    "period": period,
                    "rank_pos": pos,
                    **parsed,
                }
            )
    return rows


def peer_same_type_row_count(conn, code: str) -> int:
    cur = _cursor(conn)
    cur.execute(
        "SELECT COUNT(*) AS c FROM fund_peer_same_type WHERE code = %s",
        (code.strip(),),
    )
    return int(cur.fetchone()["c"])


def replace_peer_same_type(conn, code: str, rows: list[dict[str, Any]]) -> int:
    sym = code.strip()
    now = _utc_now()
    cur = _cursor(conn)
    cur.execute("DELETE FROM fund_peer_same_type WHERE code = %s", (sym,))
    if not rows:
        return 0
    params = [
        (
            sym,
            r["period"],
            r["rank_pos"],
            r["peer_code"],
            r["peer_name"],
            r.get("return_pct"),
            now,
        )
        for r in rows
    ]
    cur.executemany(
        """
        INSERT INTO fund_peer_same_type (
          code, period, rank_pos, peer_code, peer_name, return_pct, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        params,
    )
    return len(params)


def query_peer_same_type(conn, code: str) -> list[dict[str, Any]]:
    sym = code.strip()
    cur = _cursor(conn)
    order_cases = " ".join(
        f"WHEN '{p}' THEN {i}" for i, p in enumerate(PERIOD_KEYS)
    )
    cur.execute(
        f"""
        SELECT period, rank_pos, peer_code, peer_name, return_pct, updated_at
        FROM fund_peer_same_type
        WHERE code = %s
        ORDER BY CASE period {order_cases} ELSE 99 END, rank_pos ASC
        """,
        (sym,),
    )
    items: list[dict[str, Any]] = []
    for row in cur.fetchall():
        rp = row.get("return_pct")
        items.append(
            {
                "period": row["period"],
                "period_label": PERIOD_LABELS.get(row["period"], row["period"]),
                "rank_pos": int(row["rank_pos"]),
                "peer_code": row["peer_code"],
                "peer_name": row["peer_name"],
                "return_pct": float(rp) if rp is not None else None,
                "updated_at": str(row["updated_at"]),
            }
        )
    return items


def query_peer_same_type_grouped(conn, code: str) -> list[dict[str, Any]]:
    rows = query_peer_same_type(conn, code)
    groups: list[dict[str, Any]] = []
    by_period: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_period.setdefault(r["period"], []).append(r)
    for period in PERIOD_KEYS:
        peers = by_period.get(period)
        if not peers:
            continue
        groups.append(
            {
                "period": period,
                "period_label": PERIOD_LABELS[period],
                "peers": peers,
            }
        )
    return groups


def ensure_peer_same_type(
    conn,
    code: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    sym = code.strip()
    cached = peer_same_type_row_count(conn, sym)
    source = "cache"
    if cached == 0 or force:
        logger.info("Fetching peer same-type for %s (force=%s)", sym, force)
        rows = fetch_peer_same_type_em(sym)
        if not rows:
            return {
                "code": sym,
                "source": "empty",
                "total": 0,
                "periods": 0,
                "fetched_at": _utc_now(),
                "provider": "eastmoney_pingzhongdata",
            }
        replace_peer_same_type(conn, sym, rows)
        source = "eastmoney"
        cached = len(rows)
    periods = len({r["period"] for r in query_peer_same_type(conn, sym)})
    return {
        "code": sym,
        "source": source,
        "total": cached,
        "periods": periods,
        "fetched_at": _utc_now(),
        "provider": "eastmoney_pingzhongdata",
    }
