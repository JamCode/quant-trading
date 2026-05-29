"""Sector detail bundle for API and redirects."""

from __future__ import annotations

from typing import Any, Optional

from fund_platform import sector_constituents, sector_queries, stock_queries

_NO_CONSTITUENTS_MSG = "库内暂无行业成分股索引（由爬虫 sector_fund_flow_daily 同步，非页面实时抓取）"


def _constituents_from_db(
    conn,
    *,
    industry: str,
    lookup_date: str,
) -> Optional[dict[str, Any]]:
    bundle = stock_queries.query_industry_constituents_from_db(
        conn,
        industry=industry,
        trade_date=lookup_date,
    )
    if bundle:
        return bundle
    resolved, alias_note = sector_constituents.resolve_ths_industry_name(industry)
    if resolved != industry.strip():
        bundle = stock_queries.query_industry_constituents_from_db(
            conn,
            industry=resolved,
            trade_date=lookup_date,
        )
        if bundle:
            if alias_note:
                bundle = dict(bundle)
                bundle["alias_note"] = alias_note
                bundle["industry_query"] = industry.strip()
            return bundle
    return None


def load_sector_constituents_bundle(
    conn,
    *,
    industry: str,
    trade_date: Optional[str] = None,
) -> dict[str, Any]:
    """Constituents from MySQL only (codes + stock_daily quotes)."""
    lookup_date = trade_date or stock_queries.latest_stock_daily_date(conn) or ""
    bundle = _constituents_from_db(conn, industry=industry, lookup_date=lookup_date) if lookup_date else None
    if bundle:
        items = bundle.get("items") or []
        items = sorted(
            items,
            key=lambda x: (x.get("change_pct") is None, -(x.get("change_pct") or 0)),
        )
        return {
            "industry": industry,
            "trade_date": lookup_date,
            "constituent_date": bundle.get("constituent_date"),
            "quote_date": bundle.get("quote_date"),
            "items": items,
            "count": len(items),
            "data_source": "db",
            "alias_note": bundle.get("alias_note"),
            "fetch_error": "",
        }
    return {
        "industry": industry,
        "trade_date": lookup_date,
        "constituent_date": None,
        "items": [],
        "count": 0,
        "data_source": "",
        "alias_note": None,
        "fetch_error": _NO_CONSTITUENTS_MSG,
    }


def load_sector_detail_bundle(
    conn,
    *,
    industry: str,
    period: str,
    trade_date: Optional[str] = None,
) -> dict[str, Any]:
    """Drawer payload: fund summary + history + DB constituents (no live THS)."""
    summary, td = sector_queries.query_sector_industry(
        conn,
        industry=industry,
        trade_date=trade_date,
        period=period,
    )
    lookup_date = td or stock_queries.latest_stock_daily_date(conn) or ""
    constituents: list[dict[str, Any]] = []
    data_source = ""
    alias_note: Optional[str] = None
    constituent_date: Optional[str] = None
    quote_date: Optional[str] = None
    fetch_error = ""
    bundle = None
    if lookup_date:
        bundle = _constituents_from_db(conn, industry=industry, lookup_date=lookup_date)
    if bundle:
        constituents = bundle.get("items") or []
        data_source = "db"
        alias_note = bundle.get("alias_note")
        constituent_date = bundle.get("constituent_date")
        quote_date = bundle.get("quote_date")
    elif lookup_date:
        fetch_error = _NO_CONSTITUENTS_MSG
    if constituents:
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
    resolved, resolved_alias = sector_constituents.resolve_ths_industry_name(industry)
    if not alias_note and resolved_alias:
        alias_note = resolved_alias
    return {
        "industry": industry,
        "resolved_industry": resolved if resolved != industry.strip() else None,
        "alias_note": alias_note,
        "period": period,
        "trade_date": td or trade_date or "",
        "summary": summary,
        "constituents": constituents,
        "constituents_pending": False,
        "constituent_date": constituent_date,
        "quote_date": quote_date,
        "fetch_error": fetch_error,
        "data_source": data_source,
        "lookup_date": lookup_date,
        "flow_history": flow_history,
    }
