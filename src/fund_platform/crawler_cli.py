"""Blocking scheduler: daily MySQL catalog refresh."""

from __future__ import annotations

import logging
import signal
import sys
from collections.abc import Callable
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from fund_platform import settings as fp_settings
from fund_platform.crawler_jobs import close_stale_runs, run_scheduled_job, upsert_task_catalog
from fund_platform.crawler_logging import setup_crawler_logging
from fund_platform.fund_holdings_sync import run_fund_industry_pipeline
from fund_platform.index_valuation import sync_index_valuation_daily
from fund_platform.industry_pe import sync_industry_pe_cninfo_daily
from fund_platform.market_index import (
    is_index_intraday_poll_window,
    sync_market_index_daily_close,
    sync_market_index_intraday_cn,
)
from fund_platform.sector_flow import sync_sector_fund_flow_daily
from fund_platform.sector_market_cap import run_after_sector_flow
from fund_platform.hk_stock_daily import sync_hk_stock_daily
from fund_platform.stock_daily import sync_stock_daily
from fund_platform.fund_stock_popularity import sync_fund_stock_popularity
from fund_platform.sync import sync_catalog_mysql

logger = logging.getLogger(__name__)


def _scheduled(job_id: str, fn: Callable[[], dict[str, Any]]) -> Callable[[], None]:
    def wrapper() -> None:
        run_scheduled_job(job_id, fn)

    return wrapper


def _scheduled_when(
    job_id: str,
    fn: Callable[[], dict[str, Any]],
    *,
    when: Callable[[], bool],
) -> Callable[[], None]:
    """Run job only when ``when()`` is true (no DB run row when skipped)."""

    def wrapper() -> None:
        if not when():
            return
        run_scheduled_job(job_id, fn)

    return wrapper


def _run_job() -> dict[str, Any]:
    return sync_catalog_mysql()


def _run_stock_daily_job() -> dict[str, Any]:
    return sync_stock_daily()


def _run_hk_stock_daily_job() -> dict[str, Any]:
    return sync_hk_stock_daily()


def _run_sector_fund_flow_job() -> dict[str, Any]:
    flow = sync_sector_fund_flow_daily()
    if not flow.get("ok"):
        return flow
    from datetime import date

    follow = run_after_sector_flow(date.fromisoformat(str(flow["trade_date"])))
    return {
        "ok": bool(flow.get("ok") and follow.get("ok", True)),
        "trade_date": flow.get("trade_date"),
        "total_rows": flow.get("total_rows"),
        "periods": flow.get("periods"),
        "source": flow.get("source"),
        "follow_up": follow,
    }


def _run_fund_holdings_job() -> dict[str, Any]:
    return run_fund_industry_pipeline()


def _run_fund_stock_popularity_job() -> dict[str, Any]:
    return sync_fund_stock_popularity()


def _run_market_index_intraday_cn_job() -> dict[str, Any]:
    return sync_market_index_intraday_cn()


def _run_market_index_daily_cn_job() -> dict[str, Any]:
    return sync_market_index_daily_close(scope="cn")


def _run_market_index_daily_hk_job() -> dict[str, Any]:
    return sync_market_index_daily_close(scope="hk")


def _run_market_index_daily_global_job() -> dict[str, Any]:
    return sync_market_index_daily_close(scope="global")


def _run_index_valuation_job() -> dict[str, Any]:
    return sync_index_valuation_daily()


def _run_industry_pe_cninfo_job() -> dict[str, Any]:
    return sync_industry_pe_cninfo_daily()


def main() -> None:
    log_file = setup_crawler_logging()

    scheduler = BlockingScheduler()
    registered: set[str] = set()

    def _shutdown(signum: int, frame) -> None:  # noqa: ARG001
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    scheduler.add_job(
        _scheduled("fund_mysql_daily_sync", _run_job),
        CronTrigger(hour=fp_settings.crawler_cron_hour(), minute=fp_settings.crawler_cron_minute()),
        id="fund_mysql_daily_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("fund_mysql_daily_sync")

    scheduler.add_job(
        _scheduled("stock_daily_sync", _run_stock_daily_job),
        CronTrigger(
            hour=fp_settings.stock_daily_cron_hour(),
            minute=fp_settings.stock_daily_cron_minute(),
        ),
        id="stock_daily_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("stock_daily_sync")

    scheduler.add_job(
        _scheduled("hk_stock_daily_sync", _run_hk_stock_daily_job),
        CronTrigger(
            day_of_week="mon-fri",
            hour=fp_settings.hk_stock_daily_cron_hour(),
            minute=fp_settings.hk_stock_daily_cron_minute(),
        ),
        id="hk_stock_daily_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("hk_stock_daily_sync")

    scheduler.add_job(
        _scheduled("sector_fund_flow_daily", _run_sector_fund_flow_job),
        CronTrigger(
            hour=fp_settings.sector_flow_cron_hour(),
            minute=fp_settings.sector_flow_cron_minute(),
        ),
        id="sector_fund_flow_daily",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("sector_fund_flow_daily")

    scheduler.add_job(
        _scheduled("fund_holdings_pipeline", _run_fund_holdings_job),
        CronTrigger(
            day_of_week=fp_settings.fund_holdings_cron_day_of_week(),
            hour=fp_settings.fund_holdings_cron_hour(),
            minute=fp_settings.fund_holdings_cron_minute(),
        ),
        id="fund_holdings_pipeline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("fund_holdings_pipeline")

    scheduler.add_job(
        _scheduled("fund_stock_popularity_daily", _run_fund_stock_popularity_job),
        CronTrigger(
            hour=fp_settings.fund_stock_popularity_cron_hour(),
            minute=fp_settings.fund_stock_popularity_cron_minute(),
        ),
        id="fund_stock_popularity_daily",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("fund_stock_popularity_daily")

    intraday_mins = fp_settings.market_index_intraday_cn_interval_minutes()
    scheduler.add_job(
        _scheduled_when(
            "market_index_intraday_cn",
            _run_market_index_intraday_cn_job,
            when=is_index_intraday_poll_window,
        ),
        IntervalTrigger(minutes=intraday_mins),
        id="market_index_intraday_cn",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("market_index_intraday_cn")

    scheduler.add_job(
        _scheduled("market_index_daily_cn", _run_market_index_daily_cn_job),
        CronTrigger(
            day_of_week="mon-fri",
            hour=fp_settings.market_index_daily_cron_hour(),
            minute=fp_settings.market_index_daily_cron_minute(),
        ),
        id="market_index_daily_cn",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("market_index_daily_cn")

    scheduler.add_job(
        _scheduled("market_index_daily_hk", _run_market_index_daily_hk_job),
        CronTrigger(
            day_of_week="mon-fri",
            hour=fp_settings.market_index_hk_daily_cron_hour(),
            minute=fp_settings.market_index_hk_daily_cron_minute(),
        ),
        id="market_index_daily_hk",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("market_index_daily_hk")

    scheduler.add_job(
        _scheduled("market_index_daily_global", _run_market_index_daily_global_job),
        CronTrigger(
            day_of_week="mon-sat",
            hour=fp_settings.market_index_global_daily_cron_hour(),
            minute=fp_settings.market_index_global_daily_cron_minute(),
        ),
        id="market_index_daily_global",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("market_index_daily_global")

    scheduler.add_job(
        _scheduled("index_valuation_daily_sync", _run_index_valuation_job),
        CronTrigger(
            day_of_week="mon-sat",
            hour=fp_settings.index_valuation_cron_hour(),
            minute=fp_settings.index_valuation_cron_minute(),
        ),
        id="index_valuation_daily_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("index_valuation_daily_sync")

    scheduler.add_job(
        _scheduled("industry_pe_cninfo_daily_sync", _run_industry_pe_cninfo_job),
        CronTrigger(
            day_of_week="mon-fri",
            hour=fp_settings.industry_pe_cron_hour(),
            minute=fp_settings.industry_pe_cron_minute(),
        ),
        id="industry_pe_cninfo_daily_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    registered.add("industry_pe_cninfo_daily_sync")

    closed = close_stale_runs()
    upsert_task_catalog(registered=registered)

    logger.info(
        "Fund crawler running log=%s stale_closed=%s; fund %02d:%02d stock %02d:%02d "
        "sector %02d:%02d holdings %s %02d:%02d index intraday %sm index close %02d:%02d",
        log_file,
        closed,
        fp_settings.crawler_cron_hour(),
        fp_settings.crawler_cron_minute(),
        fp_settings.stock_daily_cron_hour(),
        fp_settings.stock_daily_cron_minute(),
        fp_settings.sector_flow_cron_hour(),
        fp_settings.sector_flow_cron_minute(),
        fp_settings.fund_holdings_cron_day_of_week(),
        fp_settings.fund_holdings_cron_hour(),
        fp_settings.fund_holdings_cron_minute(),
        intraday_mins,
        fp_settings.market_index_daily_cron_hour(),
        fp_settings.market_index_daily_cron_minute(),
    )
    scheduler.start()


if __name__ == "__main__":
    main()
