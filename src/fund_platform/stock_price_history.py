"""Lazy-loaded per-stock daily K-line (AkShare EM qfq → MySQL cache)."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Optional

import pymysql.cursors

logger = logging.getLogger(__name__)

_BATCH = 500
_CODE_RE = re.compile(r"^\d{6}$")


def normalize_stock_code(code: str) -> Optional[str]:
    sym = code.strip()
    return sym if _CODE_RE.fullmatch(sym) else None


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def history_row_count(conn, code: str) -> int:
    sym = normalize_stock_code(code)
    if not sym:
        return 0
    cur = _cursor(conn)
    cur.execute(
        "SELECT COUNT(*) AS c FROM stock_price_daily WHERE code = %s",
        (sym,),
    )
    return int(cur.fetchone()["c"])


def fetch_stock_price_daily_em(code: str) -> list[dict[str, Any]]:
    import akshare as ak

    sym = normalize_stock_code(code)
    if not sym:
        return []
    df = ak.stock_zh_a_hist(symbol=sym, period="daily", adjust="qfq")
    if df is None or df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        d = str(rec.get("日期", "")).strip()[:10]
        if not d:
            continue
        rows.append(
            {
                "trade_date": d,
                "open": _num(rec.get("开盘")),
                "high": _num(rec.get("最高")),
                "low": _num(rec.get("最低")),
                "close": _num(rec.get("收盘")),
                "volume": _int_or_none(rec.get("成交量")),
                "amount": _num(rec.get("成交额")),
                "change_pct": _num(rec.get("涨跌幅")),
            }
        )
    return rows


def replace_stock_price_daily(conn, code: str, rows: list[dict[str, Any]]) -> int:
    sym = normalize_stock_code(code)
    if not sym:
        return 0
    cur = _cursor(conn)
    cur.execute("DELETE FROM stock_price_daily WHERE code = %s", (sym,))
    if not rows:
        return 0
    params = [
        (
            sym,
            r["trade_date"],
            r.get("open"),
            r.get("high"),
            r.get("low"),
            r.get("close"),
            r.get("volume"),
            r.get("amount"),
            r.get("change_pct"),
        )
        for r in rows
    ]
    for i in range(0, len(params), _BATCH):
        chunk = params[i : i + _BATCH]
        cur.executemany(
            """
            INSERT INTO stock_price_daily (
              code, trade_date, open, high, low, close, volume, amount, change_pct
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            chunk,
        )
    return len(params)


def query_stock_price_daily(
    conn,
    code: str,
    *,
    limit: int = 250,
    offset: int = 0,
    order: str = "asc",
) -> tuple[list[dict[str, Any]], int]:
    sym = normalize_stock_code(code)
    if not sym:
        return [], 0
    cur = _cursor(conn)
    cur.execute("SELECT COUNT(*) AS c FROM stock_price_daily WHERE code = %s", (sym,))
    total = int(cur.fetchone()["c"])
    direction = "ASC" if order.lower() == "asc" else "DESC"
    lim = max(1, min(limit, 2000))
    off = max(0, offset)
    cur.execute(
        f"""
        SELECT trade_date, open, high, low, close, volume, amount, change_pct
        FROM stock_price_daily
        WHERE code = %s
        ORDER BY trade_date {direction}
        LIMIT %s OFFSET %s
        """,
        (sym, lim, off),
    )
    items: list[dict[str, Any]] = []
    for row in cur.fetchall():
        td = row["trade_date"]
        if isinstance(td, date):
            td = td.isoformat()
        items.append(
            {
                "trade_date": str(td),
                "open": _num(row.get("open")),
                "high": _num(row.get("high")),
                "low": _num(row.get("low")),
                "close": _num(row.get("close")),
                "volume": row.get("volume"),
                "amount": _num(row.get("amount")),
                "change_pct": _num(row.get("change_pct")),
            }
        )
    return items, total


def ensure_stock_price_daily(
    conn,
    code: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    sym = normalize_stock_code(code)
    if not sym:
        return {"code": code.strip(), "source": "invalid", "total": 0, "fetched_at": _utc_now()}
    cached = history_row_count(conn, sym)
    source = "cache"
    if cached == 0 or force:
        logger.info("Fetching stock price history for %s (force=%s)", sym, force)
        rows = fetch_stock_price_daily_em(sym)
        if not rows:
            return {
                "code": sym,
                "source": "empty",
                "total": 0,
                "fetched_at": _utc_now(),
            }
        replace_stock_price_daily(conn, sym, rows)
        source = "akshare"
        cached = len(rows)
    return {
        "code": sym,
        "source": source,
        "total": cached,
        "fetched_at": _utc_now(),
    }
