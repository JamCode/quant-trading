"""US listed tickers: identity from EOD spot (em_symbol for East Money hist APIs)."""

from __future__ import annotations

import re
from typing import Any, Optional

_US_CODE_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")

_EM_MARKET_PREFIX = {
    "105": "NYSE",
    "106": "NASDAQ",
    "107": "AMEX",
}

_US_BASIC_UPSERT_SQL = """
    INSERT INTO us_stock_basic (code, name, name_en, em_symbol, market, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
      name = VALUES(name),
      name_en = COALESCE(VALUES(name_en), name_en),
      em_symbol = COALESCE(VALUES(em_symbol), em_symbol),
      market = COALESCE(VALUES(market), market),
      updated_at = VALUES(updated_at)
"""


def normalize_us_ticker(code: str) -> Optional[str]:
    raw = str(code).strip().upper()
    if not raw:
        return None
    if "." in raw and raw.split(".")[0].isdigit():
        raw = raw.rsplit(".", 1)[-1]
    if not _US_CODE_RE.fullmatch(raw):
        return None
    return raw


def em_symbol_to_ticker(em_symbol: str) -> Optional[str]:
    sym = str(em_symbol).strip().upper()
    if not sym:
        return None
    if "." in sym:
        prefix, ticker = sym.split(".", 1)
        if prefix.isdigit() and ticker:
            return normalize_us_ticker(ticker)
    return normalize_us_ticker(sym)


def market_from_em_symbol(em_symbol: Optional[str]) -> Optional[str]:
    if not em_symbol or "." not in em_symbol:
        return None
    prefix = em_symbol.split(".", 1)[0]
    return _EM_MARKET_PREFIX.get(prefix)


def us_basic_row_from_spot(rec: dict[str, Any]) -> Optional[dict[str, Any]]:
    ticker = normalize_us_ticker(str(rec.get("code", "")))
    if not ticker:
        return None
    name = str(rec.get("name") or "").strip()
    if not name:
        return None
    em_sym = str(rec.get("em_symbol") or "").strip().upper() or None
    return {
        "code": ticker,
        "name": name,
        "name_en": (str(rec["name_en"]).strip() if rec.get("name_en") else None),
        "em_symbol": em_sym,
        "market": rec.get("market") or market_from_em_symbol(em_sym),
    }


def us_basic_row_params(rows: list[dict[str, Any]], now: str) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = []
    for r in rows:
        ticker = normalize_us_ticker(str(r.get("code", "")))
        if not ticker:
            continue
        out.append(
            (
                ticker,
                str(r.get("name") or "").strip(),
                r.get("name_en"),
                r.get("em_symbol"),
                r.get("market"),
                now,
            )
        )
    return out


def upsert_us_stock_basic(cur, payload: list[dict[str, Any]], *, now: str, chunk_size: int = 500) -> int:
    params = us_basic_row_params(payload, now)
    if not params:
        return 0
    for i in range(0, len(params), chunk_size):
        cur.executemany(_US_BASIC_UPSERT_SQL, params[i : i + chunk_size])
    return len(params)
