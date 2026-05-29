"""Expand sector_industry_constituent into stock_ths_industry for holdings joins."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Optional

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine

logger = logging.getLogger(__name__)

_SUFFIXES = ("Ⅲ", "Ⅱ", "III", "II")


def _trade_date_today() -> date:
    return datetime.now().date()


def _load_known_industries(cur) -> set[str]:
    cur.execute(
        """
        SELECT DISTINCT industry FROM sector_fund_flow
        WHERE industry IS NOT NULL AND industry != ''
        """
    )
    return {str(row[0] if not isinstance(row, dict) else row["industry"]).strip() for row in cur.fetchall()}


def _normalize_industry(raw: str, known: set[str]) -> str:
    s = str(raw).strip()
    for suffix in _SUFFIXES:
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    if s in known:
        return s
    for name in sorted(known, key=len, reverse=True):
        if name in s or s in name:
            return name
    return s


def rebuild_stock_ths_industry_from_holdings(
    trade_date: Optional[date] = None,
    *,
    delay_sec: Optional[float] = None,
) -> dict[str, Any]:
    """Fallback when THS constituents blocked: map each held stock via East Money profile."""
    from fund_platform.stock_industry_em import (
        fetch_stock_industry_em,
        industry_lookup_delay_sec,
        load_known_industry_names,
    )

    td = trade_date or _trade_date_today()
    td_s = td.isoformat()
    pace = delay_sec if delay_sec is not None else industry_lookup_delay_sec()
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    mapped = 0
    failed = 0
    try:
        known = load_known_industry_names(raw)
        cur.execute("SELECT DISTINCT stock_code FROM fund_holdings WHERE stock_code IS NOT NULL")
        codes = [str(r[0] if not isinstance(r, dict) else r["stock_code"]).zfill(6) for r in cur.fetchall()]
        cur.execute("DELETE FROM stock_ths_industry WHERE trade_date = %s", (td_s,))
        for code in codes:
            if not code.isdigit() or len(code) != 6:
                continue
            try:
                industry = fetch_stock_industry_em(code, known=known)
                if not industry:
                    failed += 1
                    continue
                cur.execute(
                    """
                    INSERT INTO stock_ths_industry (trade_date, code, industry)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE industry = VALUES(industry)
                    """,
                    (td_s, code, industry),
                )
                mapped += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.warning("stock industry lookup failed code=%s: %s", code, exc)
            if pace > 0:
                time.sleep(pace)
        raw.commit()
        logger.info(
            "stock_ths_industry from holdings %s mapped=%s failed=%s",
            td_s,
            mapped,
            failed,
        )
        return {
            "ok": mapped > 0,
            "trade_date": td_s,
            "count": mapped,
            "failed": failed,
            "source": "em_holdings",
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("rebuild_stock_ths_industry_from_holdings failed")
        try:
            raw.rollback()
        except Exception:
            pass
        return {"ok": False, "trade_date": td_s, "error": str(exc)}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()


def rebuild_stock_ths_industry(trade_date: Optional[date] = None) -> dict[str, Any]:
    td = trade_date or _trade_date_today()
    td_s = td.isoformat()
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        cur.execute("DELETE FROM stock_ths_industry WHERE trade_date = %s", (td_s,))
        cur.execute(
            """
            INSERT INTO stock_ths_industry (trade_date, code, industry)
            SELECT trade_date, code, industry
            FROM stock_daily
            WHERE trade_date = %s AND industry IS NOT NULL AND industry != ''
            """,
            (td_s,),
        )
        count = int(cur.rowcount or 0)
        if count <= 0:
            cur.execute(
                """
                INSERT INTO stock_ths_industry (trade_date, code, industry)
                SELECT DISTINCT trade_date, code, industry
                FROM sector_industry_constituent
                WHERE trade_date = %s
                """,
                (td_s,),
            )
            count = int(cur.rowcount or 0)
        raw.commit()
        if count <= 0:
            logger.warning("constituent map empty for %s, using EM holdings fallback", td_s)
            return rebuild_stock_ths_industry_from_holdings(trade_date)
        logger.info("stock_ths_industry rebuilt %s rows=%s", td_s, count)
        return {"ok": True, "trade_date": td_s, "count": count, "source": "constituents"}
    except Exception as exc:  # noqa: BLE001
        logger.exception("rebuild_stock_ths_industry failed")
        try:
            raw.rollback()
        except Exception:
            pass
        return {"ok": False, "trade_date": td_s, "error": str(exc)}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()
