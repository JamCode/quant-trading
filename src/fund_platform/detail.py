"""Lazy-loaded fund detail cache (AkShare) persisted in MySQL ``fund_details``."""

from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import pymysql.cursors
from pymysql.err import DataError

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _mysql_json_safe(value: Any) -> Any:
    """Make structures safe for MySQL JSON (no NaN / Infinity)."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _mysql_json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_mysql_json_safe(v) for v in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    try:
        import numpy as np

        if isinstance(value, (np.floating, np.integer)):
            f = float(value)
            if math.isnan(f) or math.isinf(f):
                return None
            if isinstance(value, np.integer):
                return int(value)
            return f
        if isinstance(value, np.bool_):
            return bool(value)
    except ImportError:
        pass
    return str(value)


def _dumps_payload(payload: dict[str, Any]) -> str:
    clean = _mysql_json_safe(payload)
    return json.dumps(clean, ensure_ascii=False, allow_nan=False)


def fetch_detail_bundle(symbol: str) -> dict[str, Any]:
    import akshare as ak

    from fund_platform import holdings as holdings_mod

    basic = ak.fund_individual_basic_info_xq(symbol=symbol)
    fees = ak.fund_individual_detail_info_xq(symbol=symbol)
    basic_map: dict[str, str] = {}
    if basic is not None and not basic.empty:
        basic_map = dict(zip(basic["item"].astype(str), basic["value"].astype(str)))
    fee_rows: list[dict[str, Any]] = []
    if fees is not None and not fees.empty:
        fee_rows = holdings_mod._records_clean(fees)
    hold_payload = holdings_mod.fetch_holdings_bundle(symbol)
    return {"basic": basic_map, "fees": fee_rows, "holdings": hold_payload}


def detail_cache_ttl_hours() -> int:
    from fund_platform import settings as fp_settings

    return fp_settings.detail_cache_hours()


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def _delete_cached_detail(conn, code: str) -> None:
    cur = _cursor(conn)
    cur.execute("DELETE FROM fund_details WHERE code = %s", (code.strip(),))


def load_cached_detail(conn, code: str) -> Optional[dict[str, Any]]:
    cur = _cursor(conn)
    try:
        cur.execute(
            "SELECT payload, updated_at FROM fund_details WHERE code = %s",
            (code.strip(),),
        )
        row = cur.fetchone()
    except DataError as exc:
        # Corrupt JSON in table (e.g. legacy NaN from pandas); drop and refetch.
        if exc.args and exc.args[0] == 3140:
            logger.warning("Invalid fund_details.payload for %s, deleting cache", code)
            _delete_cached_detail(conn, code)
            conn.commit()
            return None
        raise
    if not row:
        return None
    raw = row["payload"]
    if isinstance(raw, dict):
        payload = raw
    else:
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    return {"payload": payload, "updated_at": row["updated_at"]}


def _as_utc_datetime(val: Any) -> datetime:
    if isinstance(val, datetime):
        dt = val
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    s = str(val).strip().replace("T", " ")[:26]
    try:
        dt = datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        dt = datetime.min.replace(tzinfo=timezone.utc)
        return dt
    return dt.replace(tzinfo=timezone.utc)


def cache_is_fresh(updated_at_val: Any, ttl_hours: int) -> bool:
    dt = _as_utc_datetime(updated_at_val)
    if dt.year < 2000:
        return False
    return _utc_now() - dt < timedelta(hours=ttl_hours)


def upsert_detail(conn, code: str, payload: dict[str, Any]) -> None:
    now = _utc_now().strftime("%Y-%m-%d %H:%M:%S")
    cur = _cursor(conn)
    cur.execute(
        """
        INSERT INTO fund_details (code, payload, updated_at)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE payload = VALUES(payload), updated_at = VALUES(updated_at)
        """,
        (
            code.strip(),
            _dumps_payload(payload),
            now,
        ),
    )


def _safe_detail_payload(payload: Any) -> dict[str, Any]:
    """API/JSON-safe detail blob (no NaN/Inf; matches upsert sanitization)."""
    if not isinstance(payload, dict):
        return {}
    cleaned = _mysql_json_safe(payload)
    return cleaned if isinstance(cleaned, dict) else {}


def _update_aum_from_payload(conn, code: str, payload: dict[str, Any]) -> None:
    basic = payload.get("basic")
    if not isinstance(basic, dict):
        return
    try:
        from fund_platform.fund_aum import update_fund_aum

        update_fund_aum(conn, code, basic)
    except Exception:  # noqa: BLE001
        logger.warning("fund aum update failed for %s", code, exc_info=True)


def _index_holdings_for_lookup(conn, code: str, payload: dict[str, Any]) -> None:
    hold = payload.get("holdings")
    if not isinstance(hold, dict) or not hold.get("stocks"):
        return
    try:
        from fund_platform.fund_holdings_index import upsert_fund_holdings_from_payload

        upsert_fund_holdings_from_payload(conn, code.strip(), hold)
    except Exception:  # noqa: BLE001
        logger.warning("fund_holdings index failed for %s", code, exc_info=True)


def ensure_fresh_detail(conn, code: str, *, force: bool = False) -> dict[str, Any]:
    ttl = detail_cache_ttl_hours()
    cached = load_cached_detail(conn, code)
    if cached and not force:
        if cache_is_fresh(cached["updated_at"], ttl):
            pl = cached["payload"]
            if isinstance(pl, dict) and "holdings" in pl:
                safe = _safe_detail_payload(pl)
                _update_aum_from_payload(conn, code, safe)
                _index_holdings_for_lookup(conn, code, safe)
                return safe
    logger.info("Fetching extended detail for fund %s", code)
    bundle = fetch_detail_bundle(code.strip())
    safe = _safe_detail_payload(bundle)
    upsert_detail(conn, code.strip(), safe)
    _update_aum_from_payload(conn, code, safe)
    _index_holdings_for_lookup(conn, code, safe)
    return safe
