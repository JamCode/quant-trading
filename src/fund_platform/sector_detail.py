"""Sector detail bundle for API and redirects."""

from __future__ import annotations

from typing import Any, Optional

from fund_platform import sector_constituents, sector_queries, stock_queries


def load_sector_detail_bundle(
    conn,
    *,
    industry: str,
    period: str,
    trade_date: Optional[str] = None,
) -> dict[str, Any]:
    summary, td = sector_queries.query_sector_industry(
        conn,
        industry=industry,
        trade_date=trade_date,
        period=period,
    )
    lookup_date = td or stock_queries.latest_stock_daily_date(conn) or ""
    constituents: list[dict[str, Any]] = []
    fetch_error = ""
    data_source = ""
    bundle = None
    if lookup_date:
        bundle = stock_queries.query_industry_constituents_from_db(
            conn,
            industry=industry,
            trade_date=lookup_date,
        )
    if bundle:
        constituents = bundle.get("items") or []
        data_source = "db"
    else:
        try:
            bundle = sector_constituents.fetch_industry_constituents_ths(industry)
            constituents = bundle.get("items") or []
            data_source = "ths"
        except ValueError as exc:
            fetch_error = str(exc)
        except Exception:
            fetch_error = "成分股拉取失败，请稍后重试"
    if not fetch_error:
        constituents = sorted(
            constituents,
            key=lambda x: (x.get("change_pct") is None, -(x.get("change_pct") or 0)),
        )
    flow_history, _ = sector_queries.query_sector_industry_history(
        conn,
        industry=industry,
        trade_date=td or trade_date,
        limit=20,
    )
    return {
        "industry": industry,
        "period": period,
        "trade_date": td or trade_date or "",
        "summary": summary,
        "constituents": constituents,
        "fetch_error": fetch_error,
        "data_source": data_source,
        "lookup_date": lookup_date,
        "flow_history": flow_history,
    }
