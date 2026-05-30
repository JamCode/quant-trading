"""HK listed codes: static profile (spot identity + optional East Money F10 enrich)."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Any, Optional

from fund_platform import settings as fp_settings

logger = logging.getLogger(__name__)

_HK_BASIC_UPSERT_SQL = """
    INSERT INTO hk_stock_basic (
      code, name, name_en, security_type, board, exchange,
      listing_date, issue_price, lot_size, par_value, isin,
      hk_connect_sh, hk_connect_sz, updated_at
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
      name = VALUES(name),
      name_en = COALESCE(VALUES(name_en), name_en),
      security_type = COALESCE(VALUES(security_type), security_type),
      board = COALESCE(VALUES(board), board),
      exchange = COALESCE(VALUES(exchange), exchange),
      listing_date = COALESCE(VALUES(listing_date), listing_date),
      issue_price = COALESCE(VALUES(issue_price), issue_price),
      lot_size = COALESCE(VALUES(lot_size), lot_size),
      par_value = COALESCE(VALUES(par_value), par_value),
      isin = COALESCE(VALUES(isin), isin),
      hk_connect_sh = COALESCE(VALUES(hk_connect_sh), hk_connect_sh),
      hk_connect_sz = COALESCE(VALUES(hk_connect_sz), hk_connect_sz),
      updated_at = VALUES(updated_at)
"""


def normalize_hk_code(code: str) -> Optional[str]:
    raw = str(code).strip().upper()
    if not raw.isdigit():
        return None
    if len(raw) > 5:
        return None
    return raw.zfill(5)


def hk_basic_row_from_spot(rec: dict[str, Any]) -> Optional[dict[str, Any]]:
    sym = normalize_hk_code(str(rec.get("code", "")))
    if not sym:
        return None
    name = str(rec.get("name") or "").strip()
    if not name:
        return None
    return {
        "code": sym,
        "name": name,
        "name_en": (str(rec["name_en"]).strip() if rec.get("name_en") else None),
        "security_type": (str(rec["security_type"]).strip() if rec.get("security_type") else None),
        "board": None,
        "exchange": None,
        "listing_date": None,
        "issue_price": None,
        "lot_size": None,
        "par_value": None,
        "isin": None,
        "hk_connect_sh": None,
        "hk_connect_sz": None,
    }


def hk_basic_row_params(rows: list[dict[str, Any]], now: str) -> list[tuple[Any, ...]]:
    out: list[tuple[Any, ...]] = []
    for r in rows:
        sym = normalize_hk_code(str(r.get("code", "")))
        if not sym:
            continue
        listing = r.get("listing_date")
        if isinstance(listing, date):
            listing_s = listing.isoformat()
        elif listing:
            listing_s = str(listing).strip()[:10]
        else:
            listing_s = None
        out.append(
            (
                sym,
                str(r.get("name") or "").strip(),
                r.get("name_en"),
                r.get("security_type"),
                r.get("board"),
                r.get("exchange"),
                listing_s,
                r.get("issue_price"),
                r.get("lot_size"),
                r.get("par_value"),
                r.get("isin"),
                r.get("hk_connect_sh"),
                r.get("hk_connect_sz"),
                now,
            )
        )
    return out


def upsert_hk_stock_basic(cur, payload: list[dict[str, Any]], *, now: str, chunk_size: int = 500) -> int:
    params = hk_basic_row_params(payload, now)
    if not params:
        return 0
    for i in range(0, len(params), chunk_size):
        cur.executemany(_HK_BASIC_UPSERT_SQL, params[i : i + chunk_size])
    return len(params)


def _yes_no_to_bool(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("-", "--", "否", "N", "No"):
        return 0
    if s in ("是", "Y", "Yes", "1"):
        return 1
    return None


def fetch_hk_security_profile_em(code: str) -> Optional[dict[str, Any]]:
    """East Money HK F10 security info for one symbol."""
    import akshare as ak

    sym = normalize_hk_code(code)
    if not sym:
        return None
    df = ak.stock_hk_security_profile_em(symbol=sym)
    if df is None or df.empty:
        return None
    rec = df.iloc[0].to_dict()
    listing_raw = rec.get("上市日期")
    listing: Optional[date] = None
    if listing_raw is not None and str(listing_raw).strip():
        try:
            listing = date.fromisoformat(str(listing_raw).strip()[:10])
        except ValueError:
            listing = None
    issue = rec.get("发行价")
    lot = rec.get("每手股数")
    par = rec.get("每股面值")
    try:
        issue_f = float(issue) if issue is not None else None
    except (TypeError, ValueError):
        issue_f = None
    try:
        lot_i = int(float(lot)) if lot is not None else None
    except (TypeError, ValueError):
        lot_i = None
    try:
        par_f = float(par) if par is not None else None
    except (TypeError, ValueError):
        par_f = None
    return {
        "code": sym,
        "name": str(rec.get("证券简称") or "").strip() or None,
        "name_en": None,
        "security_type": str(rec.get("证券类型") or "").strip() or None,
        "board": str(rec.get("板块") or "").strip() or None,
        "exchange": str(rec.get("交易所") or "").strip() or None,
        "listing_date": listing,
        "issue_price": issue_f,
        "lot_size": lot_i,
        "par_value": par_f,
        "isin": str(rec.get("ISIN（国际证券识别编码）") or "").strip() or None,
        "hk_connect_sh": _yes_no_to_bool(rec.get("是否沪港通标的")),
        "hk_connect_sz": _yes_no_to_bool(rec.get("是否深港通标的")),
    }


def enrich_hk_stock_basic_em(cur, *, now: str, max_codes: Optional[int] = None) -> dict[str, Any]:
    """Backfill F10 fields for rows missing listing_date (rate-limited)."""
    if not fp_settings.hk_stock_basic_enrich_enabled():
        return {"ok": True, "skipped": True, "reason": "disabled"}
    limit = max_codes if max_codes is not None else fp_settings.hk_stock_basic_enrich_max_per_run()
    cur.execute(
        """
        SELECT code FROM hk_stock_basic
        WHERE listing_date IS NULL
        ORDER BY code ASC
        LIMIT %s
        """,
        (limit,),
    )
    codes = [str(row[0]) for row in cur.fetchall()]
    if not codes:
        return {"ok": True, "enriched": 0, "failed": 0}
    delay = fp_settings.hk_stock_basic_enrich_delay_sec()
    enriched = 0
    failed = 0
    rows: list[dict[str, Any]] = []
    for sym in codes:
        try:
            prof = fetch_hk_security_profile_em(sym)
            if prof:
                cur.execute("SELECT name FROM hk_stock_basic WHERE code = %s", (sym,))
                existing = cur.fetchone()
                if existing and existing[0] and not prof.get("name"):
                    prof["name"] = str(existing[0])
                rows.append(prof)
                enriched += 1
            else:
                failed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            logger.warning("hk basic enrich %s: %s", sym, exc)
        if delay > 0:
            time.sleep(delay)
    if rows:
        upsert_hk_stock_basic(cur, rows, now=now)
    return {"ok": True, "enriched": enriched, "failed": failed, "attempted": len(codes)}
