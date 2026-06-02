"""East Money per-stock industry lookup (东财个股资料「行业」)."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import pymysql.cursors
import requests

from fund_platform import settings as fp_settings
from fund_platform.sector_constituents import normalize_industry_name

logger = logging.getLogger(__name__)

_SUFFIXES = ("Ⅲ", "Ⅱ", "III", "II")

_EM_STOCK_GET_HOSTS = (
    "push2.eastmoney.com",
    "push2his.eastmoney.com",
    "82.push2.eastmoney.com",
    "63.push2.eastmoney.com",
    "48.push2.eastmoney.com",
)

_EM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}


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


def _industry_from_em_payload(payload: dict[str, Any]) -> Optional[str]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    raw = data.get("f127")
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def _fetch_industry_direct(symbol: str, *, timeout: float = 15.0) -> Optional[str]:
    """Read f127 (行业) from East Money stock/get; avoids akshare DataFrame parse bugs."""
    market_code = 1 if symbol.startswith("6") else 0
    params = {
        "fltt": "2",
        "invt": "2",
        "fields": "f57,f58,f127",
        "secid": f"{market_code}.{symbol}",
    }
    last_exc: Optional[Exception] = None
    for host in _EM_STOCK_GET_HOSTS:
        url = f"https://{host}/api/qt/stock/get"
        try:
            resp = requests.get(url, params=params, headers=_EM_HEADERS, timeout=timeout)
            resp.raise_for_status()
            industry = _industry_from_em_payload(resp.json())
            if industry:
                return industry
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    if last_exc:
        logger.debug("direct EM industry %s failed: %s", symbol, last_exc)
    return None


def _fetch_industry_via_akshare(symbol: str) -> Optional[str]:
    import akshare as ak

    df = ak.stock_individual_info_em(symbol=symbol)
    if df is None or df.empty:
        return None
    item_col = "item" if "item" in df.columns else df.columns[0]
    val_col = "value" if "value" in df.columns else df.columns[-1]
    hit = df.loc[df[item_col].astype(str) == "行业", val_col]
    if hit.empty:
        return None
    raw = str(hit.iloc[0]).strip()
    return raw or None


def fetch_stock_industry_em(
    code: str,
    *,
    known: Optional[set[str]] = None,
    max_attempts: int = 3,
) -> Optional[str]:
    """Return industry label for a 6-digit A-share code, or None if unavailable."""
    sym = str(code).strip().zfill(6)
    if not sym.isdigit() or len(sym) != 6:
        return None

    raw: Optional[str] = None
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, max_attempts)):
        try:
            raw = _fetch_industry_direct(sym)
            if raw:
                break
            raw = _fetch_industry_via_akshare(sym)
            if raw:
                break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
        if attempt + 1 < max_attempts:
            time.sleep(0.8 * (attempt + 1))

    if not raw:
        if last_exc:
            logger.debug("fetch_stock_industry_em %s failed: %s", sym, last_exc)
        return None
    if known is None:
        return raw
    normalized = normalize_em_industry(raw, known)
    return normalized or raw


def industry_lookup_delay_sec() -> float:
    return fp_settings.em_stock_industry_delay_sec()
