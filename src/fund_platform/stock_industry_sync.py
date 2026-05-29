"""Fill stock_daily.industry for every listed code (East Money per-stock lookup)."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine
from fund_platform.stock_industry_em import (
    fetch_stock_industry_em,
    industry_lookup_delay_sec,
    load_known_industry_names,
)
from fund_platform.stock_basic import update_stock_basic_industry
from fund_platform.stock_daily import _trade_date_today, _utc_now_iso

logger = logging.getLogger(__name__)


def _codes_needing_industry(
    cur,
    trade_date: str,
    *,
    only_missing: bool,
    limit: int,
) -> list[str]:
    if only_missing:
        cur.execute(
            """
            SELECT code FROM stock_daily
            WHERE trade_date = %s
              AND (industry IS NULL OR industry = '')
            ORDER BY code
            LIMIT %s
            """,
            (trade_date, limit),
        )
    else:
        cur.execute(
            """
            SELECT code FROM stock_daily
            WHERE trade_date = %s
            ORDER BY code
            LIMIT %s
            """,
            (trade_date, limit),
        )
    return [str(row[0] if not isinstance(row, dict) else row["code"]).zfill(6) for row in cur.fetchall()]


def mirror_stock_ths_from_daily(cur, trade_date: str) -> int:
    cur.execute(
        """
        INSERT INTO stock_ths_industry (trade_date, code, industry)
        SELECT trade_date, code, industry
        FROM stock_daily
        WHERE trade_date = %s AND industry IS NOT NULL AND industry != ''
        ON DUPLICATE KEY UPDATE industry = VALUES(industry)
        """,
        (trade_date,),
    )
    return int(cur.rowcount or 0)


def sync_stock_industries_daily(
    trade_date: Optional[date] = None,
    *,
    only_missing: Optional[bool] = None,
    max_codes: Optional[int] = None,
) -> dict[str, Any]:
    """Refresh industry on stock_daily rows for ``trade_date`` (EM 个股资料)."""
    from fund_platform.stock_queries import latest_stock_daily_date

    td = trade_date
    if td is None:
        engine = get_engine()
        raw_probe = engine.raw_connection()
        try:
            latest = latest_stock_daily_date(raw_probe)
            td = date.fromisoformat(latest) if latest else _trade_date_today()
        finally:
            raw_probe.close()
    td_s = td.isoformat()
    if only_missing is None:
        only_missing = fp_settings.stock_industry_sync_only_missing()
    cap = max_codes if max_codes is not None else fp_settings.stock_industry_sync_max_per_run()
    cap = max(1, min(cap, 10_000))
    delay = industry_lookup_delay_sec()

    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    mapped = 0
    failed = 0
    skipped = 0
    try:
        known = load_known_industry_names(raw)
        codes = _codes_needing_industry(cur, td_s, only_missing=only_missing, limit=cap)
        if not codes:
            cur.execute(
                """
                SELECT COUNT(*) FROM stock_daily
                WHERE trade_date = %s AND industry IS NOT NULL AND industry != ''
                """,
                (td_s,),
            )
            have = int((cur.fetchone() or (0,))[0])
            return {
                "ok": True,
                "trade_date": td_s,
                "mapped": 0,
                "failed": 0,
                "skipped": 0,
                "with_industry": have,
                "pending": 0,
                "source": "em",
            }

        for code in codes:
            try:
                industry = fetch_stock_industry_em(code, known=known)
                if not industry:
                    failed += 1
                    continue
                cur.execute(
                    """
                    UPDATE stock_daily
                    SET industry = %s
                    WHERE trade_date = %s AND code = %s
                    """,
                    (industry, td_s, code),
                )
                if cur.rowcount:
                    mapped += 1
                    update_stock_basic_industry(cur, code, industry, now=_utc_now_iso())
                else:
                    skipped += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                logger.warning("industry sync failed code=%s: %s", code, exc)
            if delay > 0:
                import time

                time.sleep(delay)

        ths_rows = mirror_stock_ths_from_daily(cur, td_s)
        raw.commit()

        cur.execute(
            """
            SELECT COUNT(*),
                   SUM(industry IS NOT NULL AND industry != '')
            FROM stock_daily WHERE trade_date = %s
            """,
            (td_s,),
        )
        row = cur.fetchone() or (0, 0)
        total = int(row[0])
        with_ind = int(row[1] or 0)
        pending = max(0, total - with_ind)

        logger.info(
            "stock industry sync %s mapped=%s failed=%s with_industry=%s/%s ths_mirror=%s",
            td_s,
            mapped,
            failed,
            with_ind,
            total,
            ths_rows,
        )
        return {
            "ok": mapped > 0 or with_ind > 0,
            "trade_date": td_s,
            "mapped": mapped,
            "failed": failed,
            "skipped": skipped,
            "with_industry": with_ind,
            "total": total,
            "pending": pending,
            "ths_mirror_rows": ths_rows,
            "source": "em",
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_stock_industries_daily failed")
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


def run_after_stock_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    if not fp_settings.stock_industry_sync_on_daily():
        return {"ok": True, "skipped": True}
    return sync_stock_industries_daily(trade_date)
