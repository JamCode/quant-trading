"""Small meta payloads for fund web SPA bootstrapping."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pymysql.cursors

from fund_platform import settings as fp_settings

_PERIOD_OPTIONS = ["即时", "3日排行", "5日排行", "10日排行", "20日排行"]


def period_options() -> list[str]:
    return list(_PERIOD_OPTIONS)


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def flow_meta(conn) -> dict[str, Any]:
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT DISTINCT trade_date AS d FROM sector_fund_flow
        ORDER BY trade_date DESC LIMIT 30
        """
    )
    date_options: list[str] = []
    for row in cur.fetchall():
        d = row["d"]
        if isinstance(d, (datetime, date)):
            date_options.append(d.isoformat()[:10])
        else:
            date_options.append(str(d)[:10])
    return {
        "period_options": period_options(),
        "date_options": date_options,
        "default_period": fp_settings.dashboard_default_period(),
    }


def funds_catalog_meta(conn) -> dict[str, Any]:
    from fund_platform import fund_catalog_queries

    return {
        "category_options": [
            {"id": c, "label": label} for c, label in fund_catalog_queries.CATALOG_CATEGORIES
        ],
        "sort_options": [
            {"id": s, "label": label} for s, label in fund_catalog_queries.CATALOG_SORT_OPTIONS
        ],
        "industry_options": fund_catalog_queries.list_industry_filter_options(conn),
    }
