"""HTTP API + HTML table for synced fund catalog (reads MySQL written by crawler)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus, urlencode

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from fund_platform import advisor_parse
from fund_platform import advisor_prompt
from fund_platform import crawler_queries
from fund_platform import dashboard_queries
from fund_platform import fund_catalog_queries
from fund_platform import queries
from fund_platform import sector_constituents
from fund_platform import sector_queries
from fund_platform import stock_queries
from fund_platform import settings as fp_settings
from fund_platform.db import get_engine
from fund_platform.detail import ensure_fresh_detail
from fund_platform.market_index import align_index_closes_to_dates, query_index_daily_closes
from fund_platform.nav_history import ensure_nav_history, query_nav_history
from fund_platform.peer_rank import ensure_peer_rank, query_peer_rank
from fund_platform.peer_same_type import (
    ensure_peer_same_type,
    query_peer_same_type,
    query_peer_same_type_grouped,
)
from quant_trading.funds import config

logger = logging.getLogger(__name__)

_HS300_CODE = "000300"

_templates = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_templates))


def _url_quote(value: Optional[str]) -> str:
    return quote_plus("" if value is None else str(value), safe="")


templates.env.filters["uq"] = _url_quote


def get_conn():
    raw = get_engine().raw_connection()
    try:
        yield raw
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def _catalog_query_string(
    *,
    q: str = "",
    fund_type: str = "",
    category: str = "",
    industry: str = "",
    sort: str = "code",
    order: str = "asc",
    subscribe_open: bool = False,
    per_page: int = 50,
    page: int = 1,
) -> str:
    params: dict[str, str | int] = {"page": page, "per_page": per_page, "sort": sort, "order": order}
    if q:
        params["q"] = q
    if fund_type:
        params["fund_type"] = fund_type
    if category:
        params["category"] = category
    if industry:
        params["industry"] = industry
    if subscribe_open:
        params["subscribe_open"] = "1"
    return urlencode(params)


def _page_slice(page: int, per_page: int) -> tuple[int, int]:
    page = max(1, page)
    offset = (page - 1) * per_page
    return offset, page


def _nav_chart_points(conn, code: str, *, max_points: int = 2000) -> list[dict[str, Any]]:
    """Chronological points: ``d`` date, ``v`` unit NAV, ``idx`` HS300 close (aligned)."""
    rows, _ = query_nav_history(conn, code.strip(), limit=max_points, offset=0, order="desc")
    points: list[dict[str, Any]] = []
    for r in reversed(rows):
        raw = (r.get("nav_unit") or "").strip()
        if not raw:
            continue
        try:
            val = float(raw)
        except ValueError:
            continue
        points.append({"d": r["nav_date"], "v": val})
    if not points:
        return []
    dates = [p["d"] for p in points]
    idx_map = query_index_daily_closes(
        conn, _HS300_CODE, min_date=dates[0], max_date=dates[-1]
    )
    for p, close in zip(points, align_index_closes_to_dates(dates, idx_map)):
        if close is not None:
            p["idx"] = close
    return points


def _peer_rank_chart_points(conn, code: str, *, max_points: int = 2000) -> list[dict[str, Any]]:
    rows, _ = query_peer_rank(conn, code.strip(), limit=max_points, offset=0, order="desc")
    points: list[dict[str, Any]] = []
    for r in reversed(rows):
        if r.get("rank_in_type") is None and r.get("rank_total") is None:
            continue
        points.append(
            {
                "d": r["rank_date"],
                "type": r.get("rank_in_type"),
                "total": r.get("rank_total"),
            }
        )
    return points


app = FastAPI(title="Fund catalog")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/sync/status")
def sync_status(conn=Depends(get_conn)):
    summary = queries.latest_sync_summary(conn)
    n = queries.fund_count(conn)
    return {"funds_stored": n, "last_job": summary}


@app.get("/api/crawler/tasks")
def api_crawler_tasks(conn=Depends(get_conn)):
    return {
        "tasks": crawler_queries.list_tasks_with_latest_run(conn),
        "last_activity": crawler_queries.crawler_last_activity(conn),
        "running_count": crawler_queries.count_running(conn),
    }


@app.get("/api/crawler/runs")
def api_crawler_runs(
    conn=Depends(get_conn),
    task_key: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    return {
        "runs": crawler_queries.list_runs(
            conn,
            task_key=task_key,
            status=status,
            limit=limit,
            offset=offset,
        ),
    }


@app.get("/crawler", response_class=HTMLResponse)
def crawler_page(
    request: Request,
    conn=Depends(get_conn),
    task_key: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
):
    return templates.TemplateResponse(
        request,
        "crawler.html",
        {
            "tasks": crawler_queries.list_tasks_with_latest_run(conn),
            "runs": crawler_queries.list_runs(
                conn,
                task_key=task_key,
                status=status,
                limit=50,
            ),
            "last_activity": crawler_queries.crawler_last_activity(conn),
            "running_count": crawler_queries.count_running(conn),
            "filter_task_key": task_key or "",
            "filter_status": status or "",
            "url_prefix": config.url_prefix(),
        },
    )


@app.get("/api/sector-fund-flow")
def api_sector_fund_flow(
    conn=Depends(get_conn),
    period: str = Query(default="即时"),
    trade_date: Optional[str] = Query(default=None),
    sort: str = Query(default="net_desc"),
    limit: int = Query(default=90, ge=1, le=200),
):
    rows, td = sector_queries.query_sector_flow(
        conn,
        trade_date=trade_date,
        period=period,
        sort=sort,
        limit=limit,
    )
    return {
        "trade_date": td,
        "period": period,
        "sort": sort,
        "items": rows,
    }


@app.get("/sectors", response_class=HTMLResponse)
def sectors_page(
    request: Request,
    conn=Depends(get_conn),
    period: str = Query(default="即时"),
    trade_date: str = Query(default=""),
):
    period_options = _PERIOD_OPTIONS
    if period not in period_options:
        period = "即时"
    rows, td = sector_queries.query_sector_flow(
        conn,
        trade_date=trade_date or None,
        period=period,
        sort="net_desc",
        limit=90,
    )
    with_net = [r for r in rows if r.get("net_amt") is not None]
    top_in = sorted(with_net, key=lambda x: float(x["net_amt"]), reverse=True)[:15]
    top_out = sorted(with_net, key=lambda x: float(x["net_amt"]))[:15]
    import pymysql.cursors

    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT DISTINCT trade_date AS d FROM sector_fund_flow ORDER BY trade_date DESC LIMIT 30"
    )
    date_options = []
    for r in cur.fetchall():
        d = r["d"]
        date_options.append(d.isoformat() if hasattr(d, "isoformat") else str(d))
    return templates.TemplateResponse(
        request,
        "sectors.html",
        {
            "period": period,
            "period_options": period_options,
            "trade_date": td or "",
            "date_options": date_options,
            "rows": rows,
            "top_in": top_in,
            "top_out": top_out,
            "url_prefix": config.url_prefix(),
        },
    )


_PERIOD_OPTIONS = ["即时", "3日排行", "5日排行", "10日排行", "20日排行"]


@app.get("/api/sectors/{industry:path}/constituents")
def api_sector_constituents(
    industry: str,
    conn=Depends(get_conn),
    trade_date: Optional[str] = Query(default=None),
):
    td = trade_date or stock_queries.latest_stock_daily_date(conn)
    if td:
        data = stock_queries.query_industry_constituents_from_db(
            conn, industry=industry, trade_date=td
        )
        if data:
            return data
    try:
        data = sector_constituents.fetch_industry_constituents_ths(industry)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("constituents fetch failed industry=%s", industry)
        raise HTTPException(status_code=502, detail="成分股数据拉取失败") from exc
    return data


@app.get("/sectors/{industry:path}", response_class=HTMLResponse)
def sector_detail_page(
    request: Request,
    industry: str,
    conn=Depends(get_conn),
    period: str = Query(default="即时"),
    trade_date: str = Query(default=""),
):
    if period not in _PERIOD_OPTIONS:
        period = "即时"
    summary, td = sector_queries.query_sector_industry(
        conn,
        industry=industry,
        trade_date=trade_date or None,
        period=period,
    )
    constituents: list[dict[str, Any]] = []
    fetch_error = ""
    data_source = ""
    lookup_date = td or stock_queries.latest_stock_daily_date(conn) or ""
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
        except Exception:  # noqa: BLE001
            logger.exception("sector detail constituents industry=%s", industry)
            fetch_error = "成分股拉取失败，请稍后重试"

    if not fetch_error:
        constituents = sorted(
            constituents,
            key=lambda x: (x.get("change_pct") is None, -(x.get("change_pct") or 0)),
        )
    return templates.TemplateResponse(
        request,
        "sector_detail.html",
        {
            "industry": industry,
            "period": period,
            "trade_date": td or trade_date or "",
            "summary": summary,
            "constituents": constituents,
            "fetch_error": fetch_error,
            "data_source": data_source,
            "lookup_date": lookup_date,
            "period_options": _PERIOD_OPTIONS,
            "url_prefix": config.url_prefix(),
        },
    )


@app.get("/api/funds")
def api_funds(
    conn=Depends(get_conn),
    q: Optional[str] = Query(default=None),
    fund_type: Optional[str] = Query(default=None),
    category: str = Query(default=""),
    industry: Optional[str] = Query(default=None),
    sort: str = Query(default="code"),
    order: str = Query(default="asc"),
    subscribe_open: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    offset, page = _page_slice(page, per_page)
    rows, total = fund_catalog_queries.query_funds_catalog(
        conn,
        q=q,
        fund_type=fund_type,
        category=category or None,
        industry=industry,
        subscribe_open=subscribe_open,
        sort=sort,
        sort_dir=order,
        limit=per_page,
        offset=offset,
    )
    pages = max(1, (total + per_page - 1) // per_page)
    return {
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "items": rows,
        "filters": {
            "q": q,
            "fund_type": fund_type,
            "category": category,
            "industry": industry,
            "sort": sort,
            "order": order,
            "subscribe_open": subscribe_open,
        },
    }


@app.get("/api/funds/{code}")
def api_fund_detail(
    code: str,
    conn=Depends(get_conn),
    refresh: bool = Query(default=False),
):
    row = queries.get_fund_row(conn, code.strip())
    if not row:
        raise HTTPException(status_code=404, detail="unknown fund code")
    try:
        ext = ensure_fresh_detail(conn, code.strip(), force=refresh)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Extended detail fetch failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"fund": row, "extended": ext}


@app.get("/api/funds/{code}/nav-history")
def api_fund_nav_history(
    code: str,
    conn=Depends(get_conn),
    refresh: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default="desc"),
):
    row = queries.get_fund_row(conn, code.strip())
    if not row:
        raise HTTPException(status_code=404, detail="unknown fund code")
    ord_norm = "asc" if order.lower() == "asc" else "desc"
    try:
        meta = ensure_nav_history(conn, code.strip(), force=refresh)
        items, total = query_nav_history(
            conn, code.strip(), limit=limit, offset=offset, order=ord_norm
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("NAV history fetch failed for %s", code)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        **meta,
        "limit": limit,
        "offset": offset,
        "order": ord_norm,
        "items": items,
        "total": total,
    }


@app.get("/api/funds/{code}/peer-same-type")
def api_fund_peer_same_type(
    code: str,
    conn=Depends(get_conn),
    refresh: bool = Query(default=False),
):
    row = queries.get_fund_row(conn, code.strip())
    if not row:
        raise HTTPException(status_code=404, detail="unknown fund code")
    try:
        meta = ensure_peer_same_type(conn, code.strip(), force=refresh)
        groups = query_peer_same_type_grouped(conn, code.strip())
        items = query_peer_same_type(conn, code.strip())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Peer same-type fetch failed for %s", code)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {**meta, "groups": groups, "items": items}


@app.get("/api/funds/{code}/peer-rank")
def api_fund_peer_rank(
    code: str,
    conn=Depends(get_conn),
    refresh: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default="desc"),
):
    row = queries.get_fund_row(conn, code.strip())
    if not row:
        raise HTTPException(status_code=404, detail="unknown fund code")
    ord_norm = "asc" if order.lower() == "asc" else "desc"
    try:
        meta = ensure_peer_rank(conn, code.strip(), force=refresh)
        items, total = query_peer_rank(
            conn, code.strip(), limit=limit, offset=offset, order=ord_norm
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Peer rank fetch failed for %s", code)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        **meta,
        "limit": limit,
        "offset": offset,
        "order": ord_norm,
        "items": items,
        "total": total,
    }


@app.get("/funds/{code}", response_class=HTMLResponse)
def fund_detail_page(
    request: Request,
    code: str,
    conn=Depends(get_conn),
    refresh: bool = Query(default=False),
    nav_refresh: bool = Query(default=False),
    rank_refresh: bool = Query(default=False),
    peers_refresh: bool = Query(default=False),
):
    row = queries.get_fund_row(conn, code.strip())
    if not row:
        raise HTTPException(status_code=404, detail="unknown fund code")
    ext = None
    err: Optional[str] = None
    nav_meta: Optional[dict] = None
    nav_rows: list = []
    nav_chart_json = "[]"
    nav_err: Optional[str] = None
    rank_meta: Optional[dict] = None
    rank_rows: list = []
    rank_chart_json = "[]"
    rank_err: Optional[str] = None
    peers_meta: Optional[dict] = None
    peers_groups: list = []
    peers_err: Optional[str] = None
    try:
        ext = ensure_fresh_detail(conn, code.strip(), force=refresh)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Extended detail fetch failed")
        err = str(exc)
        conn.rollback()
    try:
        nav_meta = ensure_nav_history(conn, code.strip(), force=nav_refresh or refresh)
        nav_rows, _ = query_nav_history(conn, code.strip(), limit=60, offset=0, order="desc")
        chart_pts = _nav_chart_points(conn, code.strip())
        nav_chart_json = json.dumps(chart_pts, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        logger.exception("NAV history failed for %s", code)
        nav_err = str(exc)
        conn.rollback()
    try:
        rank_meta = ensure_peer_rank(
            conn, code.strip(), force=rank_refresh or refresh
        )
        rank_rows, _ = query_peer_rank(conn, code.strip(), limit=60, offset=0, order="desc")
        rank_chart_json = json.dumps(
            _peer_rank_chart_points(conn, code.strip()), ensure_ascii=False
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Peer rank failed for %s", code)
        rank_err = str(exc)
        conn.rollback()
    try:
        peers_meta = ensure_peer_same_type(
            conn, code.strip(), force=peers_refresh or refresh
        )
        peers_groups = query_peer_same_type_grouped(conn, code.strip())
    except Exception as exc:  # noqa: BLE001
        logger.exception("Peer same-type failed for %s", code)
        peers_err = str(exc)
        conn.rollback()
    return templates.TemplateResponse(
        request,
        "detail.html",
        {
            "fund": row,
            "extended": ext,
            "fetch_error": err,
            "nav_meta": nav_meta,
            "nav_rows": nav_rows,
            "nav_chart_json": nav_chart_json,
            "nav_error": nav_err,
            "rank_meta": rank_meta,
            "rank_rows": rank_rows,
            "rank_chart_json": rank_chart_json,
            "rank_error": rank_err,
            "peers_meta": peers_meta,
            "peers_groups": peers_groups,
            "peers_error": peers_err,
            "code": code.strip(),
            "url_prefix": config.url_prefix(),
        },
    )


_PERIOD_OPTIONS = ["即时", "3日排行", "5日排行", "10日排行", "20日排行"]


@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    conn=Depends(get_conn),
    period: str = Query(default=""),
    trade_date: str = Query(default=""),
    industry: str = Query(default=""),
    fund_sort: str = Query(default="return_1y"),
):
    period_options = _PERIOD_OPTIONS
    if not period or period not in period_options:
        period = fp_settings.dashboard_default_period()
    top_in, td = dashboard_queries.sector_flow_top(
        conn, period=period, trade_date=trade_date or None, limit=10, sort="net_desc"
    )
    top_out, td2 = dashboard_queries.sector_flow_top(
        conn, period=period, trade_date=trade_date or None, limit=10, sort="net_asc"
    )
    trade_date = td or td2 or trade_date or ""
    focus = industry.strip() or dashboard_queries.default_focus_industry(
        conn, period=period, trade_date=trade_date or None
    )
    summary = None
    related_funds: list[dict[str, Any]] = []
    exposure_report_date = ""
    has_exposure = dashboard_queries.exposure_pipeline_ready(conn)
    industry_options = dashboard_queries.industry_options_from_flow(
        conn,
        period=period,
        trade_date=trade_date or None,
        top_in=top_in,
        top_out=top_out,
    )
    if focus:
        summary, _ = dashboard_queries.sector_industry_summary(
            conn,
            industry=focus,
            period=period,
            trade_date=trade_date or None,
        )
        related_funds, exposure_report_date, has_exposure = dashboard_queries.funds_for_industry(
            conn,
            industry=focus,
            report_date=None,
            limit=20,
            sort=fund_sort if fund_sort in ("return_1y", "return_3m", "weight_pct", "daily_pct") else "return_1y",
        )
    import pymysql.cursors

    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute(
        "SELECT DISTINCT trade_date AS d FROM sector_fund_flow ORDER BY trade_date DESC LIMIT 30"
    )
    date_options = []
    for r in cur.fetchall():
        d = r["d"]
        date_options.append(d.isoformat() if hasattr(d, "isoformat") else str(d))
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "period": period,
            "period_options": period_options,
            "trade_date": trade_date,
            "date_options": date_options,
            "top_in": top_in,
            "top_out": top_out,
            "focus_industry": focus or "",
            "industry_options": industry_options,
            "summary": summary,
            "related_funds": related_funds,
            "exposure_report_date": exposure_report_date,
            "has_exposure": has_exposure,
            "fund_sort": fund_sort,
            "min_exposure_pct": fp_settings.fund_exposure_min_pct(),
            "url_prefix": config.url_prefix(),
        },
    )


@app.get("/api/dashboard")
def api_dashboard(
    conn=Depends(get_conn),
    period: str = Query(default="即时"),
    trade_date: Optional[str] = Query(default=None),
    industry: Optional[str] = Query(default=None),
    fund_sort: str = Query(default="return_1y"),
):
    if period not in _PERIOD_OPTIONS:
        period = fp_settings.dashboard_default_period()
    top_in, td = dashboard_queries.sector_flow_top(conn, period=period, trade_date=trade_date, limit=15)
    top_out, _ = dashboard_queries.sector_flow_top(
        conn, period=period, trade_date=td, limit=15, sort="net_asc"
    )
    focus = industry or dashboard_queries.default_focus_industry(conn, period=period, trade_date=td)
    summary = None
    funds: list[dict[str, Any]] = []
    exp_rd = ""
    if focus:
        summary, _ = dashboard_queries.sector_industry_summary(
            conn, industry=focus, period=period, trade_date=td
        )
        funds, exp_rd, _ = dashboard_queries.funds_for_industry(
            conn, industry=focus, limit=20, sort=fund_sort
        )
    return {
        "trade_date": td,
        "period": period,
        "focus_industry": focus,
        "summary": summary,
        "top_in": top_in,
        "top_out": top_out,
        "related_funds": funds,
        "exposure_report_date": exp_rd,
    }


@app.get("/funds", response_class=HTMLResponse)
def funds_catalog(
    request: Request,
    conn=Depends(get_conn),
    q: str = "",
    fund_type: str = "",
    category: str = "",
    industry: str = "",
    sort: str = Query(default="code"),
    order: str = Query(default="asc"),
    subscribe_open: bool = Query(default=False),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    valid_sort = {s for s, _ in fund_catalog_queries.CATALOG_SORT_OPTIONS}
    if sort not in valid_sort:
        sort = "code"
    if order not in ("asc", "desc"):
        order = "asc"
    valid_cat = {c for c, _ in fund_catalog_queries.CATALOG_CATEGORIES}
    if category not in valid_cat:
        category = ""

    offset, page = _page_slice(page, per_page)
    rows, total = fund_catalog_queries.query_funds_catalog(
        conn,
        q=q or None,
        fund_type=fund_type or None,
        category=category or None,
        industry=industry or None,
        subscribe_open=subscribe_open,
        sort=sort,
        sort_dir=order,
        limit=per_page,
        offset=offset,
    )
    pages = max(1, (total + per_page - 1) // per_page)
    industry_options = fund_catalog_queries.list_industry_filter_options(conn)
    query_base = _catalog_query_string(
        q=q,
        fund_type=fund_type,
        category=category,
        industry=industry,
        sort=sort,
        order=order,
        subscribe_open=subscribe_open,
        per_page=per_page,
        page=1,
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "rows": rows,
            "q": q,
            "fund_type": fund_type,
            "category": category,
            "industry": industry,
            "sort": sort,
            "order": order,
            "subscribe_open": subscribe_open,
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": pages,
            "query_base": query_base,
            "category_options": fund_catalog_queries.CATALOG_CATEGORIES,
            "sort_options": fund_catalog_queries.CATALOG_SORT_OPTIONS,
            "industry_options": industry_options,
            "url_prefix": config.url_prefix(),
        },
    )


class AdvisorParseBody(BaseModel):
    text: str


def _advisor_api_base() -> str:
    prefix = config.url_prefix().strip().rstrip("/")
    if prefix:
        return f"{prefix}/api/advisor"
    return "/api/advisor"


@app.get("/advisor", response_class=HTMLResponse)
def advisor_page(request: Request):
    initial_prompt = advisor_prompt.build_prompt()
    return templates.TemplateResponse(
        request,
        "advisor.html",
        {
            "tag_options": advisor_prompt.tag_options(),
            "initial_prompt": initial_prompt,
            "url_prefix": config.url_prefix(),
            "advisor_api_base": _advisor_api_base(),
        },
    )


@app.get("/api/advisor/prompt")
def api_advisor_prompt(
    industries: list[str] = Query(default=[]),
    fund_types: list[str] = Query(default=[]),
    style: str = Query(default=""),
    observation: str = Query(default=""),
):
    prompt = advisor_prompt.build_prompt(
        industries=industries,
        fund_types=fund_types,
        style=style,
        observation=observation,
    )
    return {"prompt": prompt}


@app.post("/api/advisor/parse")
def api_advisor_parse(body: AdvisorParseBody, conn=Depends(get_conn)):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="粘贴内容不能为空")
    items = advisor_parse.parse_items(conn, text, url_prefix=config.url_prefix())
    return {"items": items}
