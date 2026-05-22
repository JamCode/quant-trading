"""Batch NAV + return metrics for funds with industry exposure."""

from __future__ import annotations

import logging
import time
import traceback
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine
from fund_platform.nav_history import fetch_nav_history_em, replace_nav_history

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _parse_nav_unit(value: str) -> Optional[float]:
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _return_over_days(rows: list[tuple[date, float]], days: int) -> Optional[float]:
    if not rows:
        return None
    rows.sort(key=lambda x: x[0])
    end_d, end_v = rows[-1]
    target = end_d - timedelta(days=days)
    start_v = None
    for d, v in rows:
        if d <= target:
            start_v = v
        else:
            break
    if start_v is None and rows:
        start_v = rows[0][1]
    if start_v is None or start_v <= 0:
        return None
    return round((end_v / start_v - 1.0) * 100.0, 4)


def _exposure_fund_codes(cur) -> list[str]:
    cur.execute("SELECT DISTINCT fund_code FROM fund_industry_exposure ORDER BY fund_code")
    return [str(r[0] if not isinstance(r, dict) else r["fund_code"]).strip() for r in cur.fetchall()]


def _compute_metrics_from_nav(cur, fund_code: str) -> dict[str, Optional[float]]:
    cur.execute(
        """
        SELECT nav_date, nav_unit FROM fund_nav_history
        WHERE code = %s AND nav_unit != ''
        ORDER BY nav_date ASC
        """,
        (fund_code,),
    )
    series: list[tuple[date, float]] = []
    for row in cur.fetchall():
        nd = row[0] if not isinstance(row, dict) else row["nav_date"]
        nu = row[1] if not isinstance(row, dict) else row["nav_unit"]
        if hasattr(nd, "isoformat"):
            d = nd
        else:
            d = date.fromisoformat(str(nd)[:10])
        v = _parse_nav_unit(str(nu))
        if v is not None:
            series.append((d, v))
    return {
        "return_1m": _return_over_days(series, 30),
        "return_3m": _return_over_days(series, 90),
        "return_1y": _return_over_days(series, 365),
    }


def sync_fund_metrics(
    *,
    fund_codes: Optional[list[str]] = None,
    max_funds: Optional[int] = None,
) -> dict[str, Any]:
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    targets: list[str] = []
    ok_n = 0
    fail_n = 0
    try:
        targets = fund_codes or _exposure_fund_codes(cur)
        cap = max_funds if max_funds is not None else fp_settings.fund_metrics_max_per_run()
        if cap > 0:
            targets = targets[:cap]

        delay = fp_settings.fund_metrics_delay_sec()
        now = _utc_now_iso()
        for i, code in enumerate(targets):
            try:
                rows = fetch_nav_history_em(code)
                if rows:
                    replace_nav_history(raw, code, rows)
                metrics = _compute_metrics_from_nav(cur, code)
                cur.execute(
                    """
                    INSERT INTO fund_metrics (
                      fund_code, return_1m, return_3m, return_1y, rank_in_type, aum, updated_at
                    )
                    VALUES (%s, %s, %s, %s, NULL, NULL, %s)
                    ON DUPLICATE KEY UPDATE
                      return_1m = VALUES(return_1m),
                      return_3m = VALUES(return_3m),
                      return_1y = VALUES(return_1y),
                      updated_at = VALUES(updated_at)
                    """,
                    (
                        code,
                        metrics["return_1m"],
                        metrics["return_3m"],
                        metrics["return_1y"],
                        now,
                    ),
                )
                raw.commit()
                ok_n += 1
            except Exception as exc:  # noqa: BLE001
                fail_n += 1
                logger.warning("fund_metrics failed %s: %s", code, exc)
                try:
                    raw.rollback()
                except Exception:
                    pass
            if delay > 0 and (i + 1) < len(targets):
                time.sleep(delay)

        return {"ok": True, "target": len(targets), "ok_funds": ok_n, "failed": fail_n}
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_fund_metrics failed")
        return {"ok": False, "error": str(exc), "failed": fail_n, "ok_funds": ok_n}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()
