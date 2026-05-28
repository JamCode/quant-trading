"""Read market_index_daily for Web UI."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional

import pymysql.cursors

_REGION_CN = "cn"
_REGION_HK = "hk"
_REGION_GLOBAL = "global"

_REGION_OPTIONS: list[tuple[str, str]] = [
    ("all", "全部"),
    ("cn", "A 股"),
    ("hk", "港股"),
    ("global", "全球"),
]

_HK_CODES = frozenset({"HSI", "HSCEI", "HSCCI"})


def region_options() -> list[dict[str, str]]:
    return [{"id": rid, "label": label} for rid, label in _REGION_OPTIONS]


def classify_index_region(code: str) -> str:
    c = code.strip().upper()
    if c in _HK_CODES or c.startswith("HK"):
        return _REGION_HK
    if len(c) == 6 and c.isdigit():
        return _REGION_CN
    return _REGION_GLOBAL


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in row.items():
        if isinstance(v, (datetime, date)):
            out[k] = v.isoformat() if isinstance(v, date) else v.strftime("%Y-%m-%d %H:%M:%S")
        elif hasattr(v, "__float__") and k not in ("code", "name"):
            try:
                out[k] = float(v)
            except (TypeError, ValueError):
                out[k] = v
        else:
            out[k] = v
    out["region"] = classify_index_region(str(out.get("code") or ""))
    return out


def _region_where(region: str) -> tuple[str, list[Any]]:
    reg = (region or "all").lower()
    if reg == _REGION_CN:
        return "code REGEXP '^[0-9]{6}$'", []
    if reg == _REGION_HK:
        return "code IN ('HSI', 'HSCEI', 'HSCCI')", []
    if reg == _REGION_GLOBAL:
        return (
            "code NOT REGEXP '^[0-9]{6}$' AND code NOT IN ('HSI', 'HSCEI', 'HSCCI')",
            [],
        )
    return "1=1", []


def latest_market_index_date(conn, *, region: str = "all") -> Optional[str]:
    clause, params = _region_where(region)
    cur = _cursor(conn)
    cur.execute(
        f"SELECT MAX(trade_date) AS d FROM market_index_daily WHERE {clause}",
        params,
    )
    row = cur.fetchone()
    if not row or not row["d"]:
        return None
    d = row["d"]
    return d.isoformat() if isinstance(d, date) else str(d)[:10]


def list_market_index_dates(conn, *, limit: int = 30) -> list[str]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT DISTINCT trade_date AS d FROM market_index_daily
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
        else:
            out.append(str(d)[:10])
    return out


def list_market_indices(
    conn,
    *,
    trade_date: Optional[str] = None,
    region: str = "all",
) -> tuple[list[dict[str, Any]], Optional[str]]:
    reg = (region or "all").lower()
    if reg not in ("all", _REGION_CN, _REGION_HK, _REGION_GLOBAL):
        reg = "all"
    clause, clause_params = _region_where(reg)
    cur = _cursor(conn)

    if trade_date:
        td = trade_date
        cur.execute(
            f"""
            SELECT trade_date, code, name, open_px, high_px, low_px, close_px,
                   prev_close, change_pct, change_amt, volume, amount, updated_at
            FROM market_index_daily
            WHERE trade_date = %s AND ({clause})
            ORDER BY code ASC
            """,
            [td, *clause_params],
        )
    else:
        td = None
        cur.execute(
            f"""
            SELECT m.trade_date, m.code, m.name, m.open_px, m.high_px, m.low_px, m.close_px,
                   m.prev_close, m.change_pct, m.change_amt, m.volume, m.amount, m.updated_at
            FROM market_index_daily m
            INNER JOIN (
                SELECT code, MAX(trade_date) AS max_td
                FROM market_index_daily
                WHERE ({clause})
                GROUP BY code
            ) latest ON m.code = latest.code AND m.trade_date = latest.max_td
            ORDER BY m.code ASC
            """,
            clause_params,
        )

    items = [_serialize_row(r) for r in cur.fetchall()]

    def _sort_key(r: dict[str, Any]) -> tuple[int, str]:
        order = {"cn": 0, "hk": 1, "global": 2}
        return (order.get(r.get("region", "global"), 9), str(r.get("code", "")))

    items.sort(key=_sort_key)
    return items, td


def query_market_index_snapshot(
    conn,
    code: str,
    *,
    trade_date: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    sym = code.strip()
    if not sym:
        return None
    cur = _cursor(conn)
    if trade_date:
        cur.execute(
            """
            SELECT trade_date, code, name, open_px, high_px, low_px, close_px,
                   prev_close, change_pct, change_amt, volume, amount, updated_at
            FROM market_index_daily
            WHERE trade_date = %s AND code = %s
            """,
            (trade_date, sym),
        )
    else:
        cur.execute(
            """
            SELECT trade_date, code, name, open_px, high_px, low_px, close_px,
                   prev_close, change_pct, change_amt, volume, amount, updated_at
            FROM market_index_daily
            WHERE code = %s
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (sym,),
        )
    row = cur.fetchone()
    if not row:
        return None
    return _serialize_row(row)


def query_market_index_history(
    conn,
    code: str,
    *,
    limit: int = 250,
    order: str = "asc",
) -> tuple[list[dict[str, Any]], int]:
    sym = code.strip()
    if not sym:
        return [], 0
    cur = _cursor(conn)
    cur.execute(
        "SELECT COUNT(*) AS c FROM market_index_daily WHERE code = %s AND close_px IS NOT NULL",
        (sym,),
    )
    total = int(cur.fetchone()["c"])
    lim = max(1, min(limit, 2000))
    cur.execute(
        """
        SELECT trade_date, close_px, change_pct, volume, amount
        FROM market_index_daily
        WHERE code = %s AND close_px IS NOT NULL
        ORDER BY trade_date DESC
        LIMIT %s
        """,
        (sym, lim),
    )
    rows = cur.fetchall()
    if order.lower() == "asc":
        rows = list(reversed(rows))

    items: list[dict[str, Any]] = []
    for row in rows:
        td = row["trade_date"]
        if isinstance(td, date):
            td = td.isoformat()
        close = row.get("close_px")
        items.append(
            {
                "trade_date": str(td)[:10],
                "close": float(close) if close is not None else None,
                "change_pct": float(row["change_pct"]) if row.get("change_pct") is not None else None,
                "volume": row.get("volume"),
                "amount": float(row["amount"]) if row.get("amount") is not None else None,
            }
        )
    return items, total
