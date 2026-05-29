"""Aggregate fund_holdings into per-stock popularity ranks."""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

import pymysql.cursors

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine

logger = logging.getLogger(__name__)

_LATEST_HOLDINGS_SQL = """
INNER JOIN (
  SELECT fund_code, MAX(report_date) AS rd
  FROM fund_holdings
  GROUP BY fund_code
) latest ON latest.fund_code = h.fund_code AND latest.rd = h.report_date
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


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


def rebuild_fund_stock_popularity(
    conn,
    *,
    min_fund_count: Optional[int] = None,
) -> dict[str, Any]:
    """Rebuild ``fund_stock_popularity`` from latest quarterly holdings per fund."""
    min_n = min_fund_count
    if min_n is None:
        min_n = fp_settings.fund_stock_popularity_min_funds()
    min_n = max(1, int(min_n))
    now = _utc_now_iso()
    cur = _cursor(conn)
    cur.execute("DELETE FROM fund_stock_popularity")
    cur.execute(
        f"""
        INSERT INTO fund_stock_popularity (
          stock_code, stock_name, fund_count, avg_weight_pct, updated_at
        )
        SELECT
          h.stock_code,
          SUBSTRING(MAX(h.stock_name), 1, 128) AS stock_name,
          COUNT(DISTINCT h.fund_code) AS fund_count,
          ROUND(AVG(h.weight_pct), 4) AS avg_weight_pct,
          %s AS updated_at
        FROM fund_holdings h
        {_LATEST_HOLDINGS_SQL}
        WHERE TRIM(h.stock_code) != ''
        GROUP BY h.stock_code
        HAVING COUNT(DISTINCT h.fund_code) >= %s
        """,
        (now, min_n),
    )
    count = cur.rowcount
    logger.info("fund_stock_popularity rebuilt rows=%s min_funds=%s", count, min_n)
    return {"ok": True, "rows": count, "min_fund_count": min_n, "updated_at": now}


def sync_fund_stock_popularity() -> dict[str, Any]:
    engine = get_engine()
    raw = engine.raw_connection()
    try:
        result = rebuild_fund_stock_popularity(raw)
        raw.commit()
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_fund_stock_popularity failed")
        try:
            raw.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(exc), "trace": traceback.format_exc()[:2000]}
    finally:
        raw.close()


def _market_clause(market: str) -> tuple[str, str]:
    """Return (SQL AND fragment, market label). market: cn | global | all."""
    m = (market or "all").strip().lower()
    if m == "cn":
        return "AND stock_code REGEXP '^[0-9]{6}$'", "cn"
    if m == "global":
        return (
            "AND (stock_code REGEXP '[A-Za-z]' OR stock_code NOT REGEXP '^[0-9]{6}$')",
            "global",
        )
    return "", "all"


def _default_min_funds(market_norm: str, min_fund_count: Optional[int]) -> int:
    if min_fund_count is not None and min_fund_count > 0:
        return max(1, int(min_fund_count))
    if market_norm == "global":
        return fp_settings.fund_stock_popularity_global_min_funds()
    return fp_settings.fund_stock_popularity_min_funds()


def query_popular_stocks(
    conn,
    *,
    limit: int = 50,
    offset: int = 0,
    min_fund_count: Optional[int] = None,
    market: str = "all",
) -> tuple[list[dict[str, Any]], int, Optional[str], str]:
    cur = _cursor(conn)
    market_sql, market_norm = _market_clause(market)
    min_n = _default_min_funds(market_norm, min_fund_count)
    lim = max(1, min(int(limit), 200))
    off = max(0, int(offset))

    cur.execute(
        f"""
        SELECT COUNT(*) AS c FROM fund_stock_popularity
        WHERE fund_count >= %s {market_sql}
        """,
        (min_n,),
    )
    total = int((cur.fetchone() or {}).get("c") or 0)

    cur.execute(
        f"""
        SELECT stock_code, stock_name, fund_count, avg_weight_pct, updated_at
        FROM fund_stock_popularity
        WHERE fund_count >= %s {market_sql}
        ORDER BY fund_count DESC, stock_code ASC
        LIMIT %s OFFSET %s
        """,
        (min_n, lim, off),
    )
    items = [_serialize_row(dict(r)) for r in cur.fetchall()]
    updated_at = items[0]["updated_at"] if items else None
    if not updated_at:
        cur.execute("SELECT MAX(updated_at) AS t FROM fund_stock_popularity")
        row = cur.fetchone()
        updated_at = row.get("t") if row else None
    updated_s = str(updated_at)[:19] if updated_at else ""
    return items, total, updated_s, market_norm
