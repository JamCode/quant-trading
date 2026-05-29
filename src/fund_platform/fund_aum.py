"""Parse and persist fund latest AUM (最新规模) on ``funds``."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def parse_aum_to_yi(text: Any) -> Optional[float]:
    """Parse Chinese fund size strings to 亿元."""
    s = str(text or "").strip().replace(",", "").replace("人民币", "")
    if not s or s in ("-", "--", "未知", "None", "null"):
        return None
    if "亿" in s:
        m = re.search(r"([\d.]+)\s*亿", s)
        if m:
            return round(float(m.group(1)), 4)
    if "万" in s:
        m = re.search(r"([\d.]+)\s*万", s)
        if m:
            return round(float(m.group(1)) / 10000.0, 4)
    m = re.search(r"^([\d.]+)$", s)
    if m:
        v = float(m.group(1))
        if v >= 1e8:
            return round(v / 1e8, 4)
        if v >= 10000:
            return round(v / 10000.0, 4)
        return round(v, 4)
    return None


def aum_from_basic_map(basic: dict[str, Any]) -> tuple[Optional[float], str]:
    for key in ("最新规模", "基金规模", "资产规模", "规模"):
        if key in basic and str(basic[key]).strip():
            raw = str(basic[key]).strip()
            return parse_aum_to_yi(raw), raw[:64]
    return None, ""


def update_fund_aum(conn, fund_code: str, basic: dict[str, Any]) -> bool:
    """Write ``funds.aum_yi`` / ``aum_label`` from Xueqiu basic map."""
    import pymysql.cursors

    aum_yi, label = aum_from_basic_map(basic)
    if aum_yi is None and not label:
        return False
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        """
        UPDATE funds
        SET aum_yi = %s, aum_label = %s
        WHERE code = %s
        """,
        (aum_yi, label or None, fund_code.strip()),
    )
    return cur.rowcount > 0


def backfill_aum_from_fund_details(conn) -> dict[str, int]:
    """One-off: load ``fund_details.payload`` and update ``funds.aum_yi``."""
    import pymysql.cursors

    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT code, payload FROM fund_details")
    updated = 0
    skipped = 0
    for row in cur.fetchall():
        code = str(row["code"]).strip()
        raw = row["payload"]
        if isinstance(raw, dict):
            payload = raw
        else:
            try:
                payload = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                skipped += 1
                continue
        basic = payload.get("basic") if isinstance(payload, dict) else None
        if not isinstance(basic, dict):
            skipped += 1
            continue
        if update_fund_aum(conn, code, basic):
            updated += 1
        else:
            skipped += 1
    return {"updated": updated, "skipped": skipped}
