"""East Money per-stock industry lookup (东财个股资料「行业」)."""

from __future__ import annotations

import logging
from typing import Optional

import pymysql.cursors

from fund_platform import settings as fp_settings
from fund_platform.sector_constituents import normalize_industry_name

logger = logging.getLogger(__name__)

_SUFFIXES = ("Ⅲ", "Ⅱ", "III", "II")


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def load_known_industry_names(conn) -> set[str]:
    """THS sector-flow labels used to normalize EM industry strings."""
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT DISTINCT industry
        FROM sector_fund_flow
        WHERE industry IS NOT NULL AND industry != ''
        """
    )
    known = {
        str(row["industry"]).strip()
        for row in cur.fetchall()
        if row.get("industry")
    }
    for name in list(known):
        base = normalize_industry_name(name)
        if base:
            known.add(base)
    return known


def normalize_em_industry(raw: str, known: set[str]) -> str:
    s = str(raw).strip()
    if not s:
        return ""
    for suffix in _SUFFIXES:
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    if s in known:
        return s
    for name in sorted(known, key=len, reverse=True):
        if name in s or s in name:
            return name
    return s


def fetch_stock_industry_em(
    code: str,
    *,
    known: Optional[set[str]] = None,
    max_attempts: int = 3,
) -> Optional[str]:
    """Return industry label for a 6-digit A-share code, or None if unavailable."""
    import time

    import akshare as ak

    sym = str(code).strip().zfill(6)
    if not sym.isdigit() or len(sym) != 6:
        return None
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, max_attempts)):
        try:
            df = ak.stock_individual_info_em(symbol=sym)
            if df is None or df.empty:
                return None
            item_col = "item" if "item" in df.columns else df.columns[0]
            val_col = "value" if "value" in df.columns else df.columns[-1]
            hit = df.loc[df[item_col].astype(str) == "行业", val_col]
            if hit.empty:
                return None
            raw = str(hit.iloc[0]).strip()
            if not raw:
                return None
            if known is None:
                return raw
            normalized = normalize_em_industry(raw, known)
            return normalized or raw
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt + 1 < max_attempts:
                time.sleep(0.8 * (attempt + 1))
    if last_exc:
        logger.debug("fetch_stock_industry_em %s failed: %s", sym, last_exc)
    return None


def industry_lookup_delay_sec() -> float:
    return fp_settings.em_stock_industry_delay_sec()
