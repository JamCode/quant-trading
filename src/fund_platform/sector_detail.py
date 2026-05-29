"""Sector detail bundle for API and redirects."""

from __future__ import annotations

from typing import Any, Optional

from fund_platform import sector_constituents, sector_queries, stock_queries


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
    """DB-first constituents; falls back to live THS (may take minutes on cold cache)."""
    lookup_date = trade_date or stock_queries.latest_stock_daily_date(conn) or ""
    alias_note: Optional[str] = None
    bundle = _constituents_from_db(conn, industry=industry, lookup_date=lookup_date) if lookup_date else None
    if bundle:
        items = bundle.get("items") or []
        return {
            "industry": industry,
            "trade_date": lookup_date,
            "items": items,
            "count": len(items),
            "data_source": "db",
            "alias_note": bundle.get("alias_note"),
            "fetch_error": "",
        }
    try:
        bundle = sector_constituents.fetch_industry_constituents_ths(industry)
        items = bundle.get("items") or []
        items = sorted(
            items,
            key=lambda x: (x.get("change_pct") is None, -(x.get("change_pct") or 0)),
        )
        return {
            "industry": industry,
            "trade_date": lookup_date,
            "items": items,
            "count": len(items),
            "data_source": "ths",
            "alias_note": bundle.get("alias_note"),
            "fetch_error": "",
        }
    except ValueError as exc:
        return {
            "industry": industry,
            "trade_date": lookup_date,
            "items": [],
            "count": 0,
            "data_source": "",
            "alias_note": alias_note,
            "fetch_error": str(exc),
        }
    except Exception:
        return {
            "industry": industry,
            "trade_date": lookup_date,
            "items": [],
            "count": 0,
            "data_source": "",
            "alias_note": alias_note,
            "fetch_error": "成分股拉取失败，请稍后重试",
        }


def load_sector_detail_bundle(
    conn,
    *,
    industry: str,
    period: str,
    trade_date: Optional[str] = None,
) -> dict[str, Any]:
    """Fast drawer payload: fund summary + history; constituents from DB only."""
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
    constituents_pending = False
    bundle = None
    if lookup_date:
        bundle = _constituents_from_db(conn, industry=industry, lookup_date=lookup_date)
    if bundle:
        constituents = bundle.get("items") or []
        data_source = "db"
        alias_note = bundle.get("alias_note")
    else:
        constituents_pending = True
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
        "constituents_pending": constituents_pending,
        "fetch_error": "",
        "data_source": data_source,
        "lookup_date": lookup_date,
        "flow_history": flow_history,
    }
