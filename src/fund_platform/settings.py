"""Environment-driven configuration for fund_platform (MySQL + crawler)."""

from __future__ import annotations

import os
from pathlib import Path


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required, e.g. mysql+pymysql://user:pass@127.0.0.1:3306/fund_svc"
        )
    return url


def sync_include_daily_snapshot() -> bool:
    return os.environ.get("FUND_SYNC_INCLUDE_DAILY", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def detail_cache_hours() -> int:
    return max(1, int(os.environ.get("FUND_DETAIL_CACHE_HOURS", "24")))


def crawler_cron_hour() -> int:
    return int(os.environ.get("CRAWLER_CRON_HOUR", "2"))


def crawler_cron_minute() -> int:
    return int(os.environ.get("CRAWLER_CRON_MINUTE", "0"))


def crawler_log_dir() -> Path:
    """Directory for rotating crawler.log (default: logs/crawler under cwd)."""
    raw = os.environ.get("CRAWLER_LOG_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path("logs/crawler")


def sector_flow_periods() -> list[str]:
    raw = os.environ.get(
        "SECTOR_FLOW_PERIODS", "即时,3日排行,5日排行,10日排行,20日排行"
    )
    return [p.strip() for p in raw.split(",") if p.strip()]


def sector_flow_cron_hour() -> int:
    return int(os.environ.get("SECTOR_FLOW_CRON_HOUR", "18"))


def sector_flow_cron_minute() -> int:
    return int(os.environ.get("SECTOR_FLOW_CRON_MINUTE", "30"))


def sector_flow_period_delay_sec() -> float:
    """Pause between industry fund-flow period fetches."""
    return max(0.0, float(os.environ.get("SECTOR_FLOW_PERIOD_DELAY_SEC", "3")))


def sector_market_cap_on_sync() -> bool:
    """After sector fund flow, sum stock_daily caps over constituent codes."""
    return os.environ.get("SECTOR_MARKET_CAP_ON_SYNC", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def sector_constituents_on_sync() -> bool:
    """Refresh THS industry constituent code lists (daily with sector flow)."""
    return os.environ.get("SECTOR_CONSTITUENTS_ON_SYNC", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )


def ths_request_delay_sec() -> float:
    """Pause after each successful THS HTTP response (anti rate-limit)."""
    return max(0.0, float(os.environ.get("THS_REQUEST_DELAY_SEC", "1.5")))


def ths_page_delay_sec() -> float:
    """Pause between THS constituent list pages."""
    return max(0.0, float(os.environ.get("THS_PAGE_DELAY_SEC", "2.0")))


def ths_retry_sleep_sec() -> float:
    """Base seconds before THS retry (multiplied by attempt index)."""
    return max(1.0, float(os.environ.get("THS_RETRY_SLEEP_SEC", "8")))


def ths_retries() -> int:
    return max(3, int(os.environ.get("THS_RETRIES", "8")))


def em_stock_industry_delay_sec() -> float:
    """Pause between East Money per-stock industry lookups (holdings fallback)."""
    return max(0.0, float(os.environ.get("EM_STOCK_INDUSTRY_DELAY_SEC", "0.35")))


def sector_constituent_delay_sec() -> float:
    """Pause between syncing each THS industry (~90 industries)."""
    return max(0.0, float(os.environ.get("SECTOR_CONSTITUENT_DELAY_SEC", "2.5")))


def sector_constituent_retry_pause_sec() -> float:
    """Pause before retrying failed industries."""
    return max(0.0, float(os.environ.get("SECTOR_CONSTITUENT_RETRY_PAUSE_SEC", "20")))


def sector_constituent_retry_delay_sec() -> float:
    """Per-industry delay on retry pass (should be slower than first pass)."""
    return max(0.0, float(os.environ.get("SECTOR_CONSTITUENT_RETRY_DELAY_SEC", "5")))


def stock_daily_page_delay_sec() -> float:
    """Pause between East Money spot pagination pages."""
    return max(0.0, float(os.environ.get("STOCK_DAILY_PAGE_DELAY_SEC", "3")))


def stock_daily_retry_sleep_sec() -> float:
    return max(1.0, float(os.environ.get("STOCK_DAILY_RETRY_SLEEP_SEC", "8")))


def stock_daily_cron_hour() -> int:
    return int(os.environ.get("STOCK_DAILY_CRON_HOUR", "17"))


def stock_daily_cron_minute() -> int:
    return int(os.environ.get("STOCK_DAILY_CRON_MINUTE", "0"))


def fund_holdings_type_keywords() -> list[str]:
    raw = os.environ.get("FUND_HOLDINGS_TYPE_KEYWORDS", "股票,混合,指数,ETF")
    return [k.strip() for k in raw.split(",") if k.strip()]


def fund_holdings_delay_sec() -> float:
    return max(0.0, float(os.environ.get("FUND_HOLDINGS_DELAY_SEC", "1.0")))


def fund_holdings_max_per_run() -> int:
    return max(0, int(os.environ.get("FUND_HOLDINGS_MAX_PER_RUN", "0")))


def fund_holdings_cron_hour() -> int:
    return int(os.environ.get("FUND_HOLDINGS_CRON_HOUR", "3"))


def fund_holdings_cron_minute() -> int:
    return int(os.environ.get("FUND_HOLDINGS_CRON_MINUTE", "0"))


def fund_holdings_cron_day_of_week() -> str:
    """APScheduler day_of_week: 0=Mon … 6=Sun; default Sun=6."""
    return os.environ.get("FUND_HOLDINGS_CRON_DOW", "sun")


def fund_metrics_delay_sec() -> float:
    return max(0.0, float(os.environ.get("FUND_METRICS_DELAY_SEC", "0.6")))


def fund_metrics_max_per_run() -> int:
    return max(0, int(os.environ.get("FUND_METRICS_MAX_PER_RUN", "500")))


def fund_exposure_min_pct() -> float:
    return float(os.environ.get("FUND_EXPOSURE_MIN_PCT", "10"))


def dashboard_default_period() -> str:
    return os.environ.get("DASHBOARD_DEFAULT_PERIOD", "即时").strip() or "即时"


def market_index_codes() -> list[str]:
    """Comma list: 000001 or 000001:上证指数."""
    raw = os.environ.get("MARKET_INDEX_CODES", "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def market_index_interval_minutes() -> int:
    return max(1, int(os.environ.get("MARKET_INDEX_INTERVAL_MINUTES", "5")))


def market_index_request_delay_sec() -> float:
    return max(0.0, float(os.environ.get("MARKET_INDEX_REQUEST_DELAY_SEC", "0.8")))


def market_index_retry_sleep_sec() -> float:
    return max(1.0, float(os.environ.get("MARKET_INDEX_RETRY_SLEEP_SEC", "5")))


def market_index_daily_cron_hour() -> int:
    return int(os.environ.get("MARKET_INDEX_DAILY_CRON_HOUR", "17"))


def market_index_daily_cron_minute() -> int:
    return int(os.environ.get("MARKET_INDEX_DAILY_CRON_MINUTE", "0"))


def market_index_global_names() -> list[str]:
    """Comma list: East Money global index names, e.g. 标普500,纳斯达克,道琼斯."""
    raw = os.environ.get("MARKET_INDEX_GLOBAL", "").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def market_index_global_daily_cron_hour() -> int:
    """US close is ~04:00–05:00 Beijing; run after Sina/EM publish the bar."""
    return int(os.environ.get("MARKET_INDEX_GLOBAL_DAILY_CRON_HOUR", "8"))


def market_index_global_daily_cron_minute() -> int:
    return int(os.environ.get("MARKET_INDEX_GLOBAL_DAILY_CRON_MINUTE", "10"))


def market_index_hk_names() -> list[str]:
    raw = os.environ.get("MARKET_INDEX_HK", "恒生指数").strip()
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def market_index_hk_daily_cron_hour() -> int:
    return int(os.environ.get("MARKET_INDEX_HK_DAILY_CRON_HOUR", "17"))


def market_index_hk_daily_cron_minute() -> int:
    return int(os.environ.get("MARKET_INDEX_HK_DAILY_CRON_MINUTE", "0"))


def market_index_backfill_days() -> int:
    """Days of daily history to backfill; 0 = full available history."""
    return max(0, int(os.environ.get("MARKET_INDEX_BACKFILL_DAYS", "730")))


def index_valuation_cn_symbols() -> list[str]:
    """Legulegu index names, e.g. 沪深300,中证500."""
    raw = os.environ.get(
        "INDEX_VALUATION_CN_SYMBOLS",
        "沪深300,中证500,中证800,中证1000,上证50,创业板50",
    )
    return [p.strip() for p in raw.split(",") if p.strip()]


def index_valuation_request_delay_sec() -> float:
    return max(0.0, float(os.environ.get("INDEX_VALUATION_REQUEST_DELAY_SEC", "2")))


def index_valuation_cron_hour() -> int:
    return int(os.environ.get("INDEX_VALUATION_CRON_HOUR", "17"))


def index_valuation_cron_minute() -> int:
    return int(os.environ.get("INDEX_VALUATION_CRON_MINUTE", "45"))


def index_valuation_shiller_url() -> str:
    return os.environ.get(
        "INDEX_VALUATION_SHILLER_URL",
        "http://www.econ.yale.edu/~shiller/data/ie_data.xls",
    ).strip()


def index_valuation_cn_lookback_days() -> int:
    """Days of CN Legulegu history to upsert per run (full series is large)."""
    return max(30, int(os.environ.get("INDEX_VALUATION_CN_LOOKBACK_DAYS", "60")))


def industry_pe_cninfo_request_delay_sec() -> float:
    return max(0.0, float(os.environ.get("INDUSTRY_PE_CNINFO_REQUEST_DELAY_SEC", "0.35")))


def industry_pe_cron_hour() -> int:
    return int(os.environ.get("INDUSTRY_PE_CRON_HOUR", "18"))


def industry_pe_cron_minute() -> int:
    return int(os.environ.get("INDUSTRY_PE_CRON_MINUTE", "20"))
