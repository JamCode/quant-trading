"""Batch sync fund stock holdings (East Money quarterly) for industry exposure."""

from __future__ import annotations

import logging
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine
from fund_platform.fund_holdings_common import dedupe_holdings_rows, row_from_em_record
from fund_platform.holdings import _latest_quarter_label

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def list_target_fund_codes(conn, *, scope: str = "pipeline") -> list[str]:
    import pymysql.cursors

    cur = conn.cursor(pymysql.cursors.DictCursor)
    scope_norm = (scope or "pipeline").strip().lower()
    if scope_norm == "all":
        cur.execute("SELECT code FROM funds ORDER BY code")
        return [str(r["code"]).strip() for r in cur.fetchall() if r.get("code")]
    if scope_norm == "qdii":
        cur.execute(
            """
            SELECT code FROM funds
            WHERE fund_type LIKE %s OR short_name LIKE %s
            ORDER BY code
            """,
            ("%QDII%", "%QDII%"),
        )
        return [str(r["code"]).strip() for r in cur.fetchall() if r.get("code")]

    keywords = fp_settings.fund_holdings_type_keywords()
    clauses = " OR ".join(["fund_type LIKE %s"] * len(keywords))
    params = [f"%{k}%" for k in keywords]
    cur.execute(
        f"""
        SELECT code FROM funds
        WHERE ({clauses})
        ORDER BY code
        """,
        params,
    )
    return [str(r["code"]).strip() for r in cur.fetchall() if r.get("code")]


def fetch_fund_stock_holdings_em(fund_code: str) -> Optional[dict[str, Any]]:
    import akshare as ak

    sym = fund_code.strip()
    now_y = datetime.now().year
    for y in (now_y, now_y - 1):
        try:
            df = ak.fund_portfolio_hold_em(symbol=sym, date=str(y))
        except Exception as exc:  # noqa: BLE001
            logger.warning("holdings fetch %s %s: %s", sym, y, exc)
            continue
        if df is None or df.empty:
            continue
        q = _latest_quarter_label(df)
        if not q:
            continue
        sub = df[df["季度"].astype(str) == q].copy()
        if sub.empty:
            continue
        rows: list[dict[str, Any]] = []
        for rec in sub.to_dict("records"):
            parsed = row_from_em_record(rec)
            if parsed:
                rows.append(parsed)
        if rows:
            return {"report_date": q, "report_year": y, "stocks": rows}
    return None


def _persist_fund_holdings(cur, fund_code: str, bundle: dict[str, Any], now: str) -> int:
    report_date = bundle["report_date"]
    stocks = dedupe_holdings_rows(list(bundle["stocks"]))
    cur.execute(
        "DELETE FROM fund_holdings WHERE fund_code = %s AND report_date = %s",
        (fund_code, report_date),
    )
    params = [
        (
            fund_code,
            report_date,
            r["stock_code"],
            r.get("stock_name") or "",
            r.get("weight_pct"),
            now,
        )
        for r in stocks
    ]
    if params:
        cur.executemany(
            """
            INSERT INTO fund_holdings (
              fund_code, report_date, stock_code, stock_name, weight_pct, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            params,
        )
    return len(params)


def sync_fund_holdings(
    *,
    fund_codes: Optional[list[str]] = None,
    max_funds: Optional[int] = None,
    scope: str = "pipeline",
) -> dict[str, Any]:
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    job_id = None
    targets: list[str] = []
    ok_n = 0
    fail_n = 0
    try:
        if fund_codes is None:
            targets = list_target_fund_codes(raw, scope=scope)
        else:
            targets = [c.strip() for c in fund_codes if c.strip()]
        cap = max_funds if max_funds is not None else fp_settings.fund_holdings_max_per_run()
        if cap > 0:
            targets = targets[:cap]

        cur.execute(
            """
            INSERT INTO fund_holdings_jobs (started_at, ok, funds_target)
            VALUES (%s, 0, %s)
            """,
            (_utc_now_iso(), len(targets)),
        )
        job_id = cur.lastrowid
        raw.commit()

        delay = fp_settings.fund_holdings_delay_sec()
        now = _utc_now_iso()
        for i, code in enumerate(targets):
            try:
                bundle = fetch_fund_stock_holdings_em(code)
                if bundle is None:
                    fail_n += 1
                    logger.debug("no holdings %s", code)
                else:
                    n = _persist_fund_holdings(cur, code, bundle, now)
                    raw.commit()
                    ok_n += 1
                    if (i + 1) % 50 == 0:
                        logger.info("fund_holdings progress %s/%s", i + 1, len(targets))
            except Exception as exc:  # noqa: BLE001
                fail_n += 1
                logger.warning("fund_holdings failed %s: %s", code, exc)
                try:
                    raw.rollback()
                except Exception:
                    pass
            if delay > 0:
                time.sleep(delay)

        cur.execute(
            """
            UPDATE fund_holdings_jobs
            SET finished_at = %s, ok = 1, funds_ok = %s, funds_failed = %s, error = NULL
            WHERE id = %s
            """,
            (_utc_now_iso(), ok_n, fail_n, job_id),
        )
        raw.commit()
        return {
            "ok": True,
            "job_id": job_id,
            "target": len(targets),
            "ok_funds": ok_n,
            "failed": fail_n,
        }
    except Exception as exc:  # noqa: BLE001
        err = f"{exc}\n{traceback.format_exc()}"
        logger.exception("sync_fund_holdings failed")
        if job_id is not None:
            cur.execute(
                """
                UPDATE fund_holdings_jobs
                SET finished_at = %s, ok = 0, error = %s
                WHERE id = %s
                """,
                (_utc_now_iso(), err[:4000], job_id),
            )
            try:
                raw.commit()
            except Exception:
                raw.rollback()
        return {"ok": False, "error": str(exc), "job_id": job_id}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()


def run_fund_industry_pipeline() -> dict[str, Any]:
    """Run all four holdings-related steps in sequence (manual / one-shot only)."""
    from fund_platform.fund_exposure import rebuild_fund_industry_exposure
    from fund_platform.fund_metrics_sync import sync_fund_metrics
    from fund_platform.stock_ths_industry import rebuild_stock_ths_industry

    hold_res = sync_fund_holdings()
    out: dict[str, Any] = {"holdings": hold_res}
    if not hold_res.get("ok"):
        return out
    sti_res = rebuild_stock_ths_industry()
    out["stock_ths_industry"] = sti_res
    exp_res = rebuild_fund_industry_exposure()
    out["exposure"] = exp_res
    met_res = sync_fund_metrics()
    out["metrics"] = met_res
    out["ok"] = all(
        x.get("ok")
        for x in (hold_res, sti_res, exp_res, met_res)
        if isinstance(x, dict)
    )
    return out
