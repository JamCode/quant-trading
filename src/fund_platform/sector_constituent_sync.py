"""Persist THS industry constituent codes (names/caps come from stock_daily)."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any, Optional

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine
from fund_platform.sector_constituents import (
    _industry_code_map,
    fetch_industry_constituent_codes,
)

logger = logging.getLogger(__name__)


def _trade_date_today() -> date:
    return datetime.now().date()


def sync_sector_constituents_daily(
    trade_date: Optional[date] = None,
    *,
    industries: Optional[list[str]] = None,
    request_delay_sec: Optional[float] = None,
) -> dict[str, Any]:
    td = trade_date or _trade_date_today()
    td_s = td.isoformat()
    delay = (
        request_delay_sec
        if request_delay_sec is not None
        else fp_settings.sector_constituent_delay_sec()
    )
    targets = industries or list(_industry_code_map().keys())
    logger.info(
        "Constituent sync start date=%s industries=%s delay=%.1fs",
        td_s,
        len(targets),
        delay,
    )
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    results: list[dict[str, Any]] = []
    try:
        cur.execute(
            "DELETE FROM sector_industry_constituent WHERE trade_date = %s",
            (td_s,),
        )
        def _sync_batch(names: list[str], delay: float) -> None:
            for industry in names:
                try:
                    codes = fetch_industry_constituent_codes(industry)
                    codes = [c for c in codes if len(c) == 6 and c.isdigit()]
                    if codes:
                        cur.executemany(
                            """
                            INSERT INTO sector_industry_constituent (trade_date, industry, code)
                            VALUES (%s, %s, %s)
                            """,
                            [(td_s, industry, c) for c in codes],
                        )
                    results.append({"industry": industry, "ok": True, "count": len(codes)})
                except Exception as exc:  # noqa: BLE001
                    logger.exception("constituent sync failed industry=%s", industry)
                    results.append({"industry": industry, "ok": False, "error": str(exc)})
                if delay > 0:
                    time.sleep(delay)

        _sync_batch(targets, delay)
        failed = [r["industry"] for r in results if not r.get("ok")]
        if failed:
            retry_pause = fp_settings.sector_constituent_retry_pause_sec()
            retry_delay = max(delay, fp_settings.sector_constituent_retry_delay_sec())
            logger.info(
                "Constituent retry %s industries after %.0fs pause (delay=%.1fs)",
                len(failed),
                retry_pause,
                retry_delay,
            )
            if retry_pause > 0:
                time.sleep(retry_pause)
            results[:] = [r for r in results if r.get("industry") not in failed]
            _sync_batch(failed, retry_delay)

        raw.commit()
        ok = all(r.get("ok") for r in results)
        total_codes = sum(int(r.get("count") or 0) for r in results if r.get("ok"))
        return {
            "ok": ok,
            "trade_date": td_s,
            "industries": len(targets),
            "total_codes": total_codes,
            "results": results,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_sector_constituents_daily failed")
        try:
            raw.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(exc), "trade_date": td_s, "results": results}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()


def run_after_stock_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    if not fp_settings.sector_constituents_on_sync():
        return {"ok": True, "skipped": True}
    return sync_sector_constituents_daily(trade_date)
