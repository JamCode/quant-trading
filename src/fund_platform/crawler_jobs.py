"""Crawler task catalog and unified job run records (MySQL)."""

from __future__ import annotations

import json
import logging
import traceback
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Optional

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine

logger = logging.getLogger(__name__)

_STATUS_RUNNING = "running"
_STATUS_SUCCESS = "success"
_STATUS_FAILED = "failed"
_STATUS_SKIPPED = "skipped"

_LEGACY_TABLE_BY_PREFIX: list[tuple[str, str]] = [
    ("fund_mysql_", "sync_jobs"),
    ("stock_daily_", "stock_daily_jobs"),
    ("sector_fund_flow_", "sector_flow_jobs"),
    ("fund_holdings_", "fund_holdings_jobs"),
]

# Removed from scheduler; purge from DB on catalog upsert.
_REMOVED_TASK_KEYS: tuple[str, ...] = (
    "fund_mysql_startup_sync",
    "stock_daily_startup",
    "sector_fund_flow_startup",
    "sector_fund_flow_daily",
    "market_index_intraday",
    "fund_holdings_startup",
    "market_index_startup",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _legacy_table(task_key: str) -> Optional[str]:
    for prefix, table in _LEGACY_TABLE_BY_PREFIX:
        if task_key.startswith(prefix):
            return table
    return None


def _schedule_summary(task_key: str) -> str:
    h = fp_settings.crawler_cron_hour()
    m = fp_settings.crawler_cron_minute()
    if task_key == "fund_mysql_daily_sync":
        return (
            f"每天 {h:02d}:{m:02d}（北京时间）"
        )
    if task_key == "stock_daily_sync":
        return (
            f"每天 {fp_settings.stock_daily_cron_hour():02d}:"
            f"{fp_settings.stock_daily_cron_minute():02d}"
        )
    if task_key == "fund_holdings_pipeline":
        dow = fp_settings.fund_holdings_cron_day_of_week()
        return (
            f"每周 {dow} {fp_settings.fund_holdings_cron_hour():02d}:"
            f"{fp_settings.fund_holdings_cron_minute():02d}"
        )
    if task_key == "market_index_intraday_cn":
        mins = fp_settings.market_index_intraday_cn_interval_minutes()
        return f"A 股/港股交易日盘中 每 {mins} 分钟"
    if task_key == "market_index_daily_cn":
        return (
            f"周一至周五 {fp_settings.market_index_daily_cron_hour():02d}:"
            f"{fp_settings.market_index_daily_cron_minute():02d}"
        )
    if task_key == "market_index_daily_hk":
        return (
            f"周一至周五 {fp_settings.market_index_hk_daily_cron_hour():02d}:"
            f"{fp_settings.market_index_hk_daily_cron_minute():02d}"
        )
    if task_key == "market_index_daily_global":
        return (
            f"周一至周六 {fp_settings.market_index_global_daily_cron_hour():02d}:"
            f"{fp_settings.market_index_global_daily_cron_minute():02d}"
        )
    if task_key == "index_valuation_daily_sync":
        return (
            f"周一至周六 {fp_settings.index_valuation_cron_hour():02d}:"
            f"{fp_settings.index_valuation_cron_minute():02d}"
        )
    if task_key == "industry_pe_cninfo_daily_sync":
        return (
            f"周一至周五 {fp_settings.industry_pe_cron_hour():02d}:"
            f"{fp_settings.industry_pe_cron_minute():02d}"
        )
    if task_key == "fund_stock_popularity_daily":
        return (
            f"每天 {fp_settings.fund_stock_popularity_cron_hour():02d}:"
            f"{fp_settings.fund_stock_popularity_cron_minute():02d}"
        )
    return ""


def upsert_task_catalog(*, registered: set[str]) -> None:
    """Refresh schedule text and enabled flags for all known tasks."""
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        for task_key in _all_task_keys():
            enabled = 1 if task_key in registered else 0
            cur.execute(
                """
                UPDATE crawler_tasks
                SET schedule_summary = %s, enabled = %s
                WHERE task_key = %s
                """,
                (_schedule_summary(task_key), enabled, task_key),
            )
        placeholders = ",".join(["%s"] * len(_REMOVED_TASK_KEYS))
        cur.execute(
            f"DELETE FROM crawler_job_runs WHERE task_key IN ({placeholders})",
            _REMOVED_TASK_KEYS,
        )
        cur.execute(
            f"DELETE FROM crawler_tasks WHERE task_key IN ({placeholders})",
            _REMOVED_TASK_KEYS,
        )
        raw.commit()
        logger.info("crawler task catalog updated registered=%s", len(registered))
    except Exception:
        logger.exception("upsert_task_catalog failed")
        raw.rollback()
        raise
    finally:
        cur.close()
        raw.close()


def _all_task_keys() -> tuple[str, ...]:
    return (
        "fund_mysql_daily_sync",
        "stock_daily_sync",
        "fund_holdings_pipeline",
        "market_index_intraday_cn",
        "market_index_daily_cn",
        "market_index_daily_hk",
        "market_index_daily_global",
        "index_valuation_daily_sync",
        "industry_pe_cninfo_daily_sync",
        "fund_stock_popularity_daily",
    )


def close_stale_runs(
    *,
    max_age_hours: Optional[float] = None,
    task_key: Optional[str] = None,
) -> int:
    """Fail orphaned ``running`` rows (e.g. crawler restarted mid-job)."""
    hours = fp_settings.crawler_stale_run_hours() if max_age_hours is None else max_age_hours
    if hours <= 0:
        return 0
    err = f"stale: no finish within {hours:g}h (process restart or hung job)"
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        clauses = [
            "status = %s",
            "finished_at IS NULL",
            "started_at < DATE_SUB(UTC_TIMESTAMP(3), INTERVAL %s HOUR)",
        ]
        params: list[Any] = [_STATUS_RUNNING, hours]
        if task_key:
            clauses.append("task_key = %s")
            params.append(task_key)
        cur.execute(
            f"""
            UPDATE crawler_job_runs
            SET finished_at = UTC_TIMESTAMP(3), status = %s, error = %s
            WHERE {' AND '.join(clauses)}
            """,
            (_STATUS_FAILED, err[:4000], *params),
        )
        n = int(cur.rowcount or 0)
        raw.commit()
        if n:
            logger.warning(
                "closed %s stale crawler run(s) task_key=%s max_age_hours=%s",
                n,
                task_key or "*",
                hours,
            )
        return n
    except Exception:
        raw.rollback()
        raise
    finally:
        cur.close()
        raw.close()


def begin_run(task_key: str) -> int:
    close_stale_runs(task_key=task_key)
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        cur.execute(
            """
            INSERT INTO crawler_job_runs (task_key, status, started_at)
            VALUES (%s, %s, %s)
            """,
            (task_key, _STATUS_RUNNING, _utc_now_iso()),
        )
        run_id = int(cur.lastrowid)
        raw.commit()
        return run_id
    except Exception:
        raw.rollback()
        raise
    finally:
        cur.close()
        raw.close()


def abort_run(run_id: int) -> None:
    """Drop a run row (e.g. intentional skip with nothing to audit)."""
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        cur.execute("DELETE FROM crawler_job_runs WHERE id = %s", (run_id,))
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        cur.close()
        raw.close()


def finish_run(
    run_id: int,
    *,
    status: str,
    error: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    detail_blob = json.dumps(detail, ensure_ascii=False) if detail else None
    err = (error or "")[:4000] or None
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        cur.execute(
            """
            UPDATE crawler_job_runs
            SET finished_at = %s, status = %s, error = %s, detail_json = %s
            WHERE id = %s
            """,
            (_utc_now_iso(), status, err, detail_blob, run_id),
        )
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        cur.close()
        raw.close()


def map_result_to_detail(task_key: str, result: dict[str, Any]) -> dict[str, Any]:
    """Extract scalar fields for detail_json (no nested blobs)."""
    detail: dict[str, Any] = {}
    if result.get("total_rows") is not None:
        detail["row_count"] = result["total_rows"]
    elif result.get("count") is not None:
        detail["row_count"] = result["count"]
    for key in ("trade_date", "quote_time", "target", "ok_funds", "failed", "source", "scope"):
        if result.get(key) is not None:
            detail[key] = result[key]

    holdings = result.get("holdings")
    if isinstance(holdings, dict):
        if holdings.get("job_id") is not None:
            detail["legacy_table"] = "fund_holdings_jobs"
            detail["legacy_id"] = holdings["job_id"]
        for k in ("target", "ok_funds", "failed"):
            if holdings.get(k) is not None:
                detail[k] = holdings[k]

    job_id = result.get("job_id")
    if job_id is not None and "legacy_id" not in detail:
        legacy = _legacy_table(task_key)
        if legacy:
            detail["legacy_table"] = legacy
            detail["legacy_id"] = job_id

    periods = result.get("periods")
    if isinstance(periods, list):
        for p in periods:
            if isinstance(p, dict) and p.get("job_id") is not None:
                detail["legacy_table"] = "sector_flow_jobs"
                detail["legacy_id"] = p["job_id"]
                break

    if result.get("skipped") and result.get("reason"):
        detail["skipped_reason"] = str(result["reason"])[:500]

    if result.get("source") is not None and "source" not in detail:
        detail["source"] = str(result["source"])

    return {k: v for k, v in detail.items() if _is_json_scalar(v)}


def _is_json_scalar(v: Any) -> bool:
    return isinstance(v, (str, int, float, bool)) or v is None


def resolve_run_outcome(
    task_key: str, result: Optional[dict[str, Any]]
) -> tuple[str, Optional[str], Optional[dict[str, Any]]]:
    if result is None:
        return _STATUS_FAILED, "job returned no result", None
    detail = map_result_to_detail(task_key, result) or None
    if result.get("skipped"):
        return _STATUS_SKIPPED, None, detail
    if result.get("ok"):
        return _STATUS_SUCCESS, None, detail
    err = result.get("error")
    if not err and isinstance(result.get("holdings"), dict):
        err = result["holdings"].get("error")
    return _STATUS_FAILED, str(err or "job failed")[:4000], detail


def run_scheduled_job(task_key: str, fn: Callable[[], dict[str, Any]]) -> None:
    """Execute a crawler job with DB run record (used by crawler_cli._scheduled)."""
    run_id = begin_run(task_key)
    logger.info("job start id=%s run_id=%s", task_key, run_id)
    try:
        result = fn()
        status, error, detail = resolve_run_outcome(task_key, result)
        if status == _STATUS_SKIPPED:
            abort_run(run_id)
            logger.info("job skipped id=%s (not recorded)", task_key)
            return
        finish_run(run_id, status=status, error=error, detail=detail)
        if status == _STATUS_SUCCESS:
            logger.info("job end id=%s run_id=%s status=success", task_key, run_id)
        else:
            logger.error("job end id=%s run_id=%s status=%s err=%s", task_key, run_id, status, error)
    except Exception:
        err = traceback.format_exc()
        finish_run(run_id, status=_STATUS_FAILED, error=err[:4000], detail=None)
        logger.exception("job failed id=%s run_id=%s", task_key, run_id)
