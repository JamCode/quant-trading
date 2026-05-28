"""HTTP API + HTML table for synced fund catalog (reads MySQL written by crawler)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus, urlencode

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from fund_platform import advisor_parse
from fund_platform import advisor_prompt
from fund_platform import crawler_queries
from fund_platform import dashboard_queries
from fund_platform import fund_catalog_queries
from fund_platform import index_valuation_queries
from fund_platform import industry_pe_queries
from fund_platform import queries
from fund_platform import sector_constituents
from fund_platform import sector_queries
from fund_platform import market_index_queries
from fund_platform import stock_queries
from fund_platform import settings as fp_settings
from fund_platform import web_meta_queries
from fund_platform.db import get_engine
from fund_platform.sector_detail import load_sector_detail_bundle
from fund_platform.detail import ensure_fresh_detail
from fund_platform.market_index import align_index_closes_to_dates, query_index_daily_closes
from fund_platform.nav_history import ensure_nav_history, query_nav_history
from fund_platform.stock_price_history import (
    enrich_snapshot_period_returns,
    ensure_stock_price_daily,
    history_row_count,
    normalize_stock_code,
    query_stock_price_daily,
)
from fund_platform.peer_rank import ensure_peer_rank, query_peer_rank
from fund_platform.peer_same_type import (
    ensure_peer_same_type,
    query_peer_same_type,
    query_peer_same_type_grouped,
)
from quant_trading.funds import config

logger = logging.getLogger(__name__)

_HS300_CODE = "000300"
_PERIOD_OPTIONS = web_meta_queries.period_options()
_FUND_SORT_OPTIONS = ("return_1y", "return_3m", "weight_pct", "daily_pct")

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

_static_dir = Path(__file__).resolve().parent / "static"
if _static_dir.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static_dir)), name="static")


def _base_path() -> str:
    return config.url_prefix().strip().rstrip("/")


def _bp() -> str:
    base = _base_path()
    return f"{base}/" if base else "/"


def _shell_boot() -> dict[str, str]:
    base = _base_path()
    if base:
        return {"base": base, "apiBase": f"{base}/api"}
    return {"base": "", "apiBase": "/api"}


def _render_shell(request: Request, *, page_title: str = "行业仪表盘") -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "shell.html",
        {
            "bp": _bp(),
            "boot_json": json.dumps(_shell_boot(), ensure_ascii=False),
            "page_title": page_title,
        },
    )


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


@app.get("/api/meta/flow")
def api_meta_flow(conn=Depends(get_conn)):
    return web_meta_queries.flow_meta(conn)


@app.get("/api/meta/funds")
def api_meta_funds(conn=Depends(get_conn)):
    return web_meta_queries.funds_catalog_meta(conn)


@app.get("/api/meta/stocks")
def api_meta_stocks(conn=Depends(get_conn)):
    return web_meta_queries.stocks_catalog_meta(conn)


@app.get("/api/meta/market-indices")
def api_meta_market_indices(conn=Depends(get_conn)):
    return web_meta_queries.market_indices_meta(conn)


@app.get("/api/market-indices")
def api_market_indices(
    conn=Depends(get_conn),
    trade_date: Optional[str] = Query(default=None),
    region: str = Query(default="all"),
):
    items, td = market_index_queries.list_market_indices(
        conn, trade_date=trade_date, region=region
    )
    out: dict[str, Any] = {"region": region, "items": items, "latest_per_code": trade_date is None}
    if td:
        out["trade_date"] = td
    return out


@app.get("/api/market-indices/{code}")
def api_market_index_detail(
    code: str,
    conn=Depends(get_conn),
    trade_date: Optional[str] = Query(default=None),
):
    sym = code.strip()
    if not sym:
        raise HTTPException(status_code=404, detail="unknown index code")
    snap = market_index_queries.query_market_index_snapshot(conn, sym, trade_date=trade_date)
    if not snap:
        raise HTTPException(status_code=404, detail="no snapshot for index on trade date")
    td = trade_date or snap.get("trade_date")
    return {"snapshot": snap, "trade_date": td}


@app.get("/api/market-indices/{code}/history")
def api_market_index_history(
    code: str,
    conn=Depends(get_conn),
    limit: int = Query(default=250, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default="asc"),
):
    sym = code.strip()
    if not sym:
        raise HTTPException(status_code=404, detail="unknown index code")
    ord_norm = "asc" if order.lower() == "asc" else "desc"
    items, total = market_index_queries.query_market_index_history(
        conn, sym, limit=limit, offset=offset, order=ord_norm
    )
    return {
        "code": sym,
        "source": "db",
        "limit": limit,
        "offset": offset,
        "order": ord_norm,
        "items": items,
        "total": total,
    }


def _require_stock_code(code: str) -> str:
    sym = normalize_stock_code(code)
    if not sym:
        raise HTTPException(status_code=404, detail="unknown stock code")
    return sym


@app.get("/api/stocks")
def api_stocks(
    conn=Depends(get_conn),
    trade_date: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    sort: str = Query(default="change_pct"),
    order: str = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1, le=200),
):
    td = trade_date or stock_queries.latest_stock_daily_date(conn)
    if not td:
        return {
            "trade_date": None,
            "page": page,
            "per_page": per_page,
            "total": 0,
            "pages": 1,
            "items": [],
        }
    offset, page = _page_slice(page, per_page)
    items, total = stock_queries.query_stock_list(
        conn,
        trade_date=td,
        q=q,
        sort=sort,
        order=order,
        limit=per_page,
        offset=offset,
    )
    pages = max(1, (total + per_page - 1) // per_page)
    return {
        "trade_date": td,
        "page": page,
        "per_page": per_page,
        "total": total,
        "pages": pages,
        "items": items,
        "filters": {"q": q, "sort": sort, "order": order, "trade_date": td},
    }


@app.get("/api/stocks/{code}")
def api_stock_detail(
    code: str,
    conn=Depends(get_conn),
    trade_date: Optional[str] = Query(default=None),
):
    sym = _require_stock_code(code)
    snap = stock_queries.query_stock_snapshot(conn, sym, trade_date=trade_date)
    if not snap:
        raise HTTPException(status_code=404, detail="no snapshot for stock on trade date")
    enrich_snapshot_period_returns(conn, snap)
    td = trade_date or snap.get("trade_date") or stock_queries.latest_stock_daily_date(conn)
    industries = stock_queries.query_stock_industries(conn, sym, trade_date=td)
    return {"snapshot": snap, "industries": industries, "trade_date": td}


@app.get("/api/stocks/{code}/price-history")
def api_stock_price_history(
    code: str,
    conn=Depends(get_conn),
    refresh: bool = Query(default=False),
    limit: int = Query(default=250, ge=1, le=2000),
    offset: int = Query(default=0, ge=0),
    order: str = Query(default="asc"),
):
    sym = _require_stock_code(code)
    ord_norm = "asc" if order.lower() == "asc" else "desc"
    try:
        meta = ensure_stock_price_daily(conn, sym, force=refresh)
        if meta.get("source") in ("empty", "invalid") and meta.get("total", 0) == 0:
            return {
                **meta,
                "limit": limit,
                "offset": offset,
                "order": ord_norm,
                "items": [],
                "total": 0,
            }
        if meta.get("source") == "invalid":
            raise HTTPException(status_code=404, detail="unknown stock code")
        _, total = query_stock_price_daily(conn, sym, limit=1, offset=0, order="desc")
        if ord_norm == "asc" and offset == 0:
            items_desc, _ = query_stock_price_daily(
                conn, sym, limit=limit, offset=0, order="desc"
            )
            items = list(reversed(items_desc))
        else:
            items, _ = query_stock_price_daily(
                conn, sym, limit=limit, offset=offset, order=ord_norm
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Stock price history fetch failed for %s", sym)
        if history_row_count(conn, sym) > 0:
            _, total = query_stock_price_daily(conn, sym, limit=1, offset=0, order="desc")
            if ord_norm == "asc" and offset == 0:
                items_desc, _ = query_stock_price_daily(
                    conn, sym, limit=limit, offset=0, order="desc"
                )
                items = list(reversed(items_desc))
            else:
                items, _ = query_stock_price_daily(
                    conn, sym, limit=limit, offset=offset, order=ord_norm
                )
            return {
                "code": sym,
                "source": "cache",
                "total": total,
                "warning": str(exc),
                "limit": limit,
                "offset": offset,
                "order": ord_norm,
                "items": items,
            }
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        **meta,
        "limit": limit,
        "offset": offset,
        "order": ord_norm,
        "items": items,
        "total": total,
    }


@app.get("/api/sectors/{industry:path}")
def api_sector_detail(
    industry: str,
    conn=Depends(get_conn),
    period: str = Query(default="即时"),
    trade_date: Optional[str] = Query(default=None),
):
    if period not in _PERIOD_OPTIONS:
        period = fp_settings.dashboard_default_period()
    return load_sector_detail_bundle(
        conn,
        industry=industry,
        period=period,
        trade_date=trade_date,
    )


@app.get("/api/valuation/indices")
def api_valuation_indices(
    conn=Depends(get_conn),
    region: Optional[str] = Query(default=None, description="cn|hk|us"),
    limit: int = Query(default=50, ge=1, le=200),
):
    return {
        "items": index_valuation_queries.list_latest_index_valuation(
            conn, region=region, limit=limit
        ),
    }


@app.get("/api/valuation/indices/history")
def api_valuation_indices_history(
    conn=Depends(get_conn),
    region: str = Query(..., description="cn|hk|us"),
    index_code: str = Query(...),
    limit: int = Query(default=730, ge=1, le=5000),
):
    history = index_valuation_queries.query_index_valuation_history(
        conn,
        region=region,
        index_code=index_code,
        limit=limit,
    )
    name = history[-1]["index_name"] if history else index_code
    return {
        "region": region.strip().lower(),
        "index_code": index_code.strip(),
        "index_name": name,
        "points": history,
    }


def _valuation_chart_points(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in history:
        pt: dict[str, Any] = {"d": row["trade_date"]}
        if row.get("pe_ttm") is not None:
            pt["ttm"] = row["pe_ttm"]
        if row.get("pe_static") is not None:
            pt["static"] = row["pe_static"]
        if row.get("pe_cape") is not None:
            pt["cape"] = row["pe_cape"]
        if len(pt) > 1:
            points.append(pt)
    return points


def _pick_valuation_selection(
    latest: list[dict[str, Any]],
    *,
    region: Optional[str],
    index_code: Optional[str],
) -> tuple[str, str, Optional[dict[str, Any]]]:
    reg = (region or "cn").strip().lower()
    code = (index_code or "").strip()
    by_region = index_valuation_queries.group_latest_by_region(latest)
    if code:
        for item in latest:
            if item.get("region") == reg and item.get("index_code") == code:
                return reg, code, item
    for item in by_region.get(reg) or []:
        if item.get("index_code") == "000300.SH":
            return reg, str(item["index_code"]), item
    pool = by_region.get(reg) or []
    if pool:
        first = pool[0]
        return reg, str(first["index_code"]), first
    for fallback_reg in ("cn", "hk", "us"):
        pool = by_region.get(fallback_reg) or []
        if pool:
            first = pool[0]
            return fallback_reg, str(first["index_code"]), first
    return reg, code or "000300.SH", None


def _industry_pe_chart_points(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for row in history:
        pt: dict[str, Any] = {"d": row["trade_date"]}
        if row.get("pe_weighted") is not None:
            pt["weighted"] = row["pe_weighted"]
        if row.get("pe_median") is not None:
            pt["median"] = row["pe_median"]
        if row.get("pe_avg") is not None:
            pt["avg"] = row["pe_avg"]
        if len(pt) > 1:
            points.append(pt)
    return points


def _pick_industry_pe_selection(
    latest: list[dict[str, Any]],
    *,
    industry_code: Optional[str],
    default_level: int = 2,
) -> tuple[str, Optional[dict[str, Any]]]:
    code = (industry_code or "").strip()
    if code:
        for item in latest:
            if item.get("industry_code") == code:
                return code, item
    pool = [x for x in latest if int(x.get("industry_level") or 0) == default_level]
    if not pool:
        pool = latest
    if pool:
        first = pool[0]
        return str(first["industry_code"]), first
    return code or "", None


@app.get("/api/valuation/industry")
def api_valuation_industry(
    conn=Depends(get_conn),
    industry_level: Optional[int] = Query(default=2, ge=1, le=4),
    limit: int = Query(default=200, ge=1, le=500),
):
    return {
        "trade_date": industry_pe_queries.latest_industry_pe_date(conn),
        "items": industry_pe_queries.list_latest_industry_pe(
            conn,
            industry_level=industry_level,
            limit=limit,
        ),
    }


@app.get("/api/valuation/industry/history")
def api_valuation_industry_history(
    conn=Depends(get_conn),
    industry_code: str = Query(...),
    limit: int = Query(default=730, ge=1, le=5000),
):
    history = industry_pe_queries.query_industry_pe_history(
        conn,
        industry_code=industry_code,
        limit=limit,
    )
    name = history[-1]["industry_name"] if history else industry_code
    return {
        "industry_code": industry_code.strip(),
        "industry_name": name,
        "points": history,
    }


@app.get("/valuation", response_class=HTMLResponse)
def valuation_page(request: Request):
    return _render_shell(request, page_title="宽基 PE")


@app.get("/crawler", response_class=HTMLResponse)
def crawler_page(request: Request):
    return _render_shell(request, page_title="爬虫任务")


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
def sectors_page(request: Request):
    return _render_shell(request, page_title="行业资金流向")


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


@app.get("/sectors/{industry:path}")
def sector_detail_redirect(
    industry: str,
    period: str = Query(default="即时"),
    trade_date: str = Query(default=""),
):
    if period not in _PERIOD_OPTIONS:
        period = "即时"
    q = urlencode(
        {
            "drawer": "sector",
            "industry": industry,
            "period": period,
            "trade_date": trade_date,
        }
    )
    return RedirectResponse(url=f"{_bp()}sectors?{q}", status_code=302)


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


@app.get("/funds/{code}")
def fund_detail_redirect(code: str):
    q = urlencode({"drawer": "fund", "code": code.strip()})
    return RedirectResponse(url=f"{_bp()}funds?{q}", status_code=302)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return _render_shell(request, page_title="行业仪表盘")


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
    if fund_sort not in _FUND_SORT_OPTIONS:
        fund_sort = "return_1y"
    top_in, td = dashboard_queries.sector_flow_top(conn, period=period, trade_date=trade_date, limit=15)
    top_out, _ = dashboard_queries.sector_flow_top(
        conn, period=period, trade_date=td, limit=15, sort="net_asc"
    )
    focus = industry or dashboard_queries.default_focus_industry(conn, period=period, trade_date=td)
    summary = None
    funds: list[dict[str, Any]] = []
    exp_rd = ""
    has_exposure = dashboard_queries.exposure_pipeline_ready(conn)
    industry_options: list[str] = []
    if focus:
        summary, _ = dashboard_queries.sector_industry_summary(
            conn, industry=focus, period=period, trade_date=td
        )
        funds, exp_rd, has_exposure = dashboard_queries.funds_for_industry(
            conn, industry=focus, limit=20, sort=fund_sort
        )
    industry_options = dashboard_queries.industry_options_from_flow(
        conn,
        period=period,
        trade_date=td,
        top_in=top_in,
        top_out=top_out,
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
        "has_exposure": has_exposure,
        "industry_options": industry_options,
        "period_options": _PERIOD_OPTIONS,
        "min_exposure_pct": fp_settings.fund_exposure_min_pct(),
        "fund_sort": fund_sort,
    }


@app.get("/funds", response_class=HTMLResponse)
def funds_catalog(request: Request):
    return _render_shell(request, page_title="基金目录")


@app.get("/indices", response_class=HTMLResponse)
def market_indices_page(request: Request):
    return _render_shell(request, page_title="指数行情")


@app.get("/indices/{code}", response_class=HTMLResponse)
def market_index_detail_page(request: Request, code: str):
    if not code.strip():
        raise HTTPException(status_code=404, detail="unknown index code")
    return _render_shell(request, page_title="指数详情")


@app.get("/stocks", response_class=HTMLResponse)
def stocks_catalog(request: Request):
    return _render_shell(request, page_title="A 股行情")


@app.get("/stocks/{code}", response_class=HTMLResponse)
def stock_detail_page(request: Request, code: str):
    _require_stock_code(code)
    return _render_shell(request, page_title="个股详情")


class AdvisorParseBody(BaseModel):
    text: str


def _advisor_api_base() -> str:
    prefix = config.url_prefix().strip().rstrip("/")
    if prefix:
        return f"{prefix}/api/advisor"
    return "/api/advisor"


@app.get("/advisor", response_class=HTMLResponse)
def advisor_page(request: Request):
    return _render_shell(request, page_title="基金 AI 助手")


@app.get("/api/advisor/options")
def api_advisor_options():
    opts = advisor_prompt.tag_options()
    return {key: list(values) for key, values in opts.items()}


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
