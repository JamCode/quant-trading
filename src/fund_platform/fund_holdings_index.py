"""Upsert fund_holdings from holdings JSON (detail cache / on-demand fetch)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fund_platform.fund_holdings_common import (
    report_date_from_holdings,
    rows_from_holdings_payload,
)

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def upsert_fund_holdings_from_payload(
    conn,
    fund_code: str,
    holdings: dict[str, Any],
) -> int:
    """Index quarterly stocks into ``fund_holdings`` for reverse lookup."""
    import pymysql.cursors

    rows = rows_from_holdings_payload(holdings)
    if not rows:
        return 0
    report_date = report_date_from_holdings(holdings)
    sym = fund_code.strip()
    now = _utc_now_iso()
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "DELETE FROM fund_holdings WHERE fund_code = %s AND report_date = %s",
        (sym, report_date),
    )
    params = [
        (sym, report_date, r["stock_code"], r.get("stock_name") or "", r.get("weight_pct"), now)
        for r in rows
    ]
    cur.executemany(
        """
        INSERT INTO fund_holdings (
          fund_code, report_date, stock_code, stock_name, weight_pct, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        params,
    )
    logger.debug("Indexed %s holdings for fund %s report %s", len(params), sym, report_date)
    return len(params)
