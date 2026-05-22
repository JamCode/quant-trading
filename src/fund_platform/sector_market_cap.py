"""Industry float market cap = sum(stock_daily) over THS constituent codes."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine
from fund_platform.sector_constituent_sync import run_after_stock_daily
from fund_platform.sector_constituents import fetch_industry_constituents_ths
from fund_platform.stock_daily import ensure_stock_daily

logger = logging.getLogger(__name__)


def _trade_date_today() -> date:
    return datetime.now().date()


def _list_industries_for_date(cur, trade_date: date) -> list[str]:
    cur.execute(
        """
        SELECT DISTINCT industry
        FROM sector_fund_flow
        WHERE trade_date = %s AND period = %s
        ORDER BY industry
        """,
        (trade_date.isoformat(), "即时"),
    )
    rows = cur.fetchall()
    if rows:
        return [str(r[0] if not isinstance(r, dict) else r["industry"]).strip() for r in rows]
    cur.execute(
        """
        SELECT DISTINCT industry
        FROM sector_fund_flow
        WHERE trade_date = %s
        ORDER BY industry
        """,
        (trade_date.isoformat(),),
    )
    return [str(r[0] if not isinstance(r, dict) else r["industry"]).strip() for r in cur.fetchall()]


def _aggregate_cap(cur, trade_date: str, industry: str) -> tuple[Optional[float], int, int]:
    cur.execute(
        """
        SELECT
          SUM(sd.float_market_cap) AS cap_sum,
          COUNT(*) AS cnt,
          SUM(CASE WHEN sd.float_market_cap IS NULL THEN 1 ELSE 0 END) AS missing
        FROM sector_industry_constituent c
        LEFT JOIN stock_daily sd
          ON sd.trade_date = c.trade_date AND sd.code = c.code
        WHERE c.trade_date = %s AND c.industry = %s
        """,
        (trade_date, industry),
    )
    row = cur.fetchone()
    if not row:
        return None, 0, 0
    cap_sum = row[0] if not isinstance(row, dict) else row.get("cap_sum")
    cnt = int(row[1] if not isinstance(row, dict) else row.get("cnt") or 0)
    missing = int(row[2] if not isinstance(row, dict) else row.get("missing") or 0)
    if cap_sum is not None:
        cap_sum = round(float(cap_sum), 2)
    return cap_sum, cnt, missing


def sync_sector_float_market_cap_daily(
    trade_date: Optional[date] = None,
    *,
    industries: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Update sector_fund_flow.float_market_cap via stock_daily + constituent codes."""
    td = trade_date or _trade_date_today()
    td_s = td.isoformat()
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    results: list[dict[str, Any]] = []
    try:
        targets = industries or _list_industries_for_date(cur, td)
        if not targets:
            return {"ok": True, "trade_date": td_s, "updated": 0, "industries": [], "note": "no rows"}

        for industry in targets:
            cap_sum, cnt, missing = _aggregate_cap(cur, td_s, industry)
            method = "stock_daily_join"
            if cnt == 0:
                try:
                    bundle = fetch_industry_constituents_ths(industry)
                    cap_sum = bundle.get("float_market_cap_sum")
                    cnt = int(bundle.get("count") or 0)
                    missing = int(bundle.get("float_market_cap_missing") or 0)
                    method = "ths_direct"
                except Exception as exc:  # noqa: BLE001
                    results.append(
                        {
                            "industry": industry,
                            "ok": False,
                            "error": f"no constituents; ths fallback: {exc}",
                        }
                    )
                    continue
            if cnt == 0:
                results.append(
                    {
                        "industry": industry,
                        "ok": False,
                        "error": "no constituents for date",
                    }
                )
                continue
            cur.execute(
                """
                UPDATE sector_fund_flow
                SET float_market_cap = %s
                WHERE trade_date = %s AND industry = %s
                """,
                (cap_sum, td_s, industry),
            )
            results.append(
                {
                    "industry": industry,
                    "ok": True,
                    "float_market_cap": cap_sum,
                    "constituents": cnt,
                    "cap_missing": missing,
                    "method": method,
                }
            )

        raw.commit()
        ok = all(r.get("ok") for r in results)
        updated = sum(1 for r in results if r.get("ok"))
        methods = {r.get("method") for r in results if r.get("ok")}
        return {
            "ok": ok,
            "trade_date": td_s,
            "updated": updated,
            "industries": results,
            "method": ",".join(sorted(methods)) or "none",
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_sector_float_market_cap_daily failed")
        try:
            raw.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(exc), "trade_date": td_s, "industries": results}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()


def run_after_sector_flow(trade_date: Optional[date] = None) -> dict[str, Any]:
    if not fp_settings.sector_market_cap_on_sync():
        return {"ok": True, "skipped": True}
    td = trade_date or _trade_date_today()
    stock_res = ensure_stock_daily(td)
    if not stock_res.get("ok"):
        logger.warning("stock_daily sync failed, sector cap will use THS fallback: %s", stock_res)
    const_res = run_after_stock_daily(td)
    from fund_platform.stock_ths_industry import rebuild_stock_ths_industry

    sti_res = rebuild_stock_ths_industry(td)
    cap_res = sync_sector_float_market_cap_daily(td)
    ok = cap_res.get("ok") and const_res.get("ok", True) and sti_res.get("ok", True)
    return {
        "ok": ok,
        "stock_daily": stock_res,
        "constituents": const_res,
        "stock_ths_industry": sti_res,
        "market_cap": cap_res,
    }
