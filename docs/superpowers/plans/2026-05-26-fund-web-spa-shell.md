# Fund Web SPA Shell Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace multi-page Jinja fund UI with one JSON-driven SPA: left sidebar, client-rendered modules, right drawer for industry/fund detail.

**Architecture:** FastAPI serves `shell.html` + static ES modules; all views call existing/new `/api/*` endpoints; business logic stays in `fund_platform/*_queries.py`. Three phased releases per [spec](../specs/2026-05-26-fund-web-spa-shell-design.md).

**Tech Stack:** Python 3.12, FastAPI, Jinja2 (shell only), vanilla ES modules, MySQL (existing), Chart.js (valuation, Phase 2), pytest + `httpx`/`TestClient` for API tests.

**Spec:** `docs/superpowers/specs/2026-05-26-fund-web-spa-shell-design.md`

---

## File map (create / modify)

| Path | Role |
|------|------|
| `src/quant_trading/funds/templates/shell.html` | **Create** — sole HTML entry, boot `__FUND_APP__`, sidebar, `#app-main`, drawer mount |
| `src/quant_trading/funds/static/fund-app/theme.css` | **Create** — layout, sidebar, tables, drawer, pct colors |
| `src/quant_trading/funds/static/fund-app/main.js` | **Create** — boot router + drawer on `DOMContentLoaded` |
| `src/quant_trading/funds/static/fund-app/api.js` | **Create** — `apiGet`, `fmtYi`, `fmtPct`, errors |
| `src/quant_trading/funds/static/fund-app/router.js` | **Create** — path → view, `navigate`, drawer query sync |
| `src/quant_trading/funds/static/fund-app/components/drawer.js` | **Create** |
| `src/quant_trading/funds/static/fund-app/components/sector-drawer.js` | **Create** |
| `src/quant_trading/funds/static/fund-app/components/fund-drawer.js` | **Create** |
| `src/quant_trading/funds/static/fund-app/views/dashboard.js` | **Create** |
| `src/quant_trading/funds/static/fund-app/views/sectors.js` | **Create** |
| `src/quant_trading/funds/static/fund-app/views/valuation.js` | **Create** — Phase 2 |
| `src/quant_trading/funds/static/fund-app/views/funds.js` | **Create** — Phase 2 |
| `src/quant_trading/funds/static/fund-app/views/advisor.js` | **Create** — Phase 3 |
| `src/quant_trading/funds/static/fund-app/views/crawler.js` | **Create** — Phase 3 |
| `src/fund_platform/web_meta_queries.py` | **Create** — `flow_meta`, `funds_catalog_meta` (thin SQL/helpers) |
| `src/fund_platform/sector_detail.py` | **Create** — `load_sector_detail_bundle()` shared by API + legacy redirect |
| `src/quant_trading/funds/app.py` | **Modify** — static mount, shell route, catch-all, new APIs, redirects, deprecate HTML routes |
| `tests/test_fund_web_spa_api.py` | **Create** — API contract tests (no DB: mock conn or skip integration) |
| `deploy/ecs/README.md` | **Modify** — single entry URL note (Phase 3) |

**Unchanged:** Crawler systemd, MySQL schemas, `fund_platform/sector_flow.py` (except unrelated fixes).

---

## Phase 1 — Shell, dashboard, sectors, drawer (MVP)

### Task 1: Shared sector detail loader (backend)

**Files:**
- Create: `src/fund_platform/sector_detail.py`
- Modify: `src/quant_trading/funds/app.py` (later tasks use it)

- [ ] **Step 1: Add loader module**

```python
# src/fund_platform/sector_detail.py
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
        conn, industry=industry, trade_date=trade_date, period=period
    )
    lookup_date = td or stock_queries.latest_stock_daily_date(conn) or ""
    constituents: list[dict[str, Any]] = []
    fetch_error = ""
    data_source = ""
    bundle = None
    if lookup_date:
        bundle = stock_queries.query_industry_constituents_from_db(
            conn, industry=industry, trade_date=lookup_date
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
    return {
        "industry": industry,
        "period": period,
        "trade_date": td or trade_date or "",
        "summary": summary,
        "constituents": constituents,
        "fetch_error": fetch_error,
        "data_source": data_source,
        "lookup_date": lookup_date,
    }
```

- [ ] **Step 2: Commit**

```bash
git add src/fund_platform/sector_detail.py
git commit -m "refactor: extract sector detail bundle loader"
```

---

### Task 2: Flow meta + extended dashboard API

**Files:**
- Create: `src/fund_platform/web_meta_queries.py`
- Modify: `src/quant_trading/funds/app.py`
- Test: `tests/test_fund_web_spa_api.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_fund_web_spa_api.py
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from quant_trading.funds.app import app

client = TestClient(app)


def test_meta_flow_shape():
    with patch("quant_trading.funds.app.get_conn") as mock_dep:
        conn = MagicMock()
        mock_dep.return_value = iter([conn])
        with patch("fund_platform.web_meta_queries.flow_meta") as fm:
            fm.return_value = {
                "period_options": ["即时"],
                "date_options": ["2026-05-25"],
                "default_period": "即时",
            }
            r = client.get("/api/meta/flow")
    assert r.status_code == 200
    body = r.json()
    assert "period_options" in body
    assert "date_options" in body


def test_api_dashboard_includes_meta_fields():
    with patch("quant_trading.funds.app.get_conn") as mock_dep:
        conn = MagicMock()
        mock_dep.return_value = iter([conn])
        with patch("quant_trading.funds.app.dashboard_queries") as dq:
            dq.sector_flow_top.side_effect = [([], "2026-05-25"), ([], "2026-05-25")]
            dq.default_focus_industry.return_value = "银行"
            dq.exposure_pipeline_ready.return_value = True
            dq.industry_options_from_flow.return_value = ["银行"]
            dq.sector_industry_summary.return_value = (None, None)
            dq.funds_for_industry.return_value = ([], "", True)
            r = client.get("/api/dashboard")
    assert r.status_code == 200
    body = r.json()
    assert "industry_options" in body
    assert "has_exposure" in body
```

- [ ] **Step 2: Run tests — expect FAIL**

Run: `pytest tests/test_fund_web_spa_api.py -v`  
Expected: `ModuleNotFoundError` or 404 on `/api/meta/flow`

- [ ] **Step 3: Implement `web_meta_queries.py`**

```python
# src/fund_platform/web_meta_queries.py
from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pymysql.cursors

from fund_platform import settings as fp_settings

_PERIOD_OPTIONS = ["即时", "3日排行", "5日排行", "10日排行", "20日排行"]


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def flow_meta(conn) -> dict[str, Any]:
    cur = _cursor(conn)
    cur.execute(
        "SELECT DISTINCT trade_date AS d FROM sector_fund_flow "
        "ORDER BY trade_date DESC LIMIT 30"
    )
    date_options = []
    for row in cur.fetchall():
        d = row["d"]
        date_options.append(d.isoformat() if hasattr(d, "isoformat") else str(d))
    return {
        "period_options": list(_PERIOD_OPTIONS),
        "date_options": date_options,
        "default_period": fp_settings.dashboard_default_period(),
    }


def funds_catalog_meta(conn) -> dict[str, Any]:
    from fund_platform import fund_catalog_queries

    return {
        "category_options": [
            {"id": c, "label": label}
            for c, label in fund_catalog_queries.CATALOG_CATEGORIES
        ],
        "sort_options": [
            {"id": s, "label": label}
            for s, label in fund_catalog_queries.CATALOG_SORT_OPTIONS
        ],
        "industry_options": fund_catalog_queries.list_industry_filter_options(conn),
    }
```

- [ ] **Step 4: Add routes in `app.py`**

```python
from fund_platform import web_meta_queries
from fund_platform.sector_detail import load_sector_detail_bundle

@app.get("/api/meta/flow")
def api_meta_flow(conn=Depends(get_conn)):
    return web_meta_queries.flow_meta(conn)


@app.get("/api/sectors/{industry:path}")
def api_sector_detail(
    industry: str,
    conn=Depends(get_conn),
    period: str = Query(default="即时"),
    trade_date: Optional[str] = Query(default=None),
):
    if period not in _PERIOD_OPTIONS:
        period = "即时"
    return load_sector_detail_bundle(
        conn, industry=industry, period=period, trade_date=trade_date
    )
```

Extend existing `api_dashboard` return dict:

```python
    industry_options = dashboard_queries.industry_options_from_flow(
        conn, period=period, trade_date=td, top_in=top_in, top_out=top_out
    )
    return {
        ...
        "industry_options": industry_options,
        "has_exposure": dashboard_queries.exposure_pipeline_ready(conn),
        "exposure_report_date": exp_rd,
        "period_options": _PERIOD_OPTIONS,
    }
```

- [ ] **Step 5: Run tests — expect PASS**

Run: `pytest tests/test_fund_web_spa_api.py -v`

- [ ] **Step 6: Commit**

```bash
git add src/fund_platform/web_meta_queries.py src/quant_trading/funds/app.py tests/test_fund_web_spa_api.py
git commit -m "feat: add flow meta and sector detail JSON APIs"
```

---

### Task 3: Static files + shell HTML

**Files:**
- Create: `src/quant_trading/funds/templates/shell.html`
- Create: `src/quant_trading/funds/static/fund-app/theme.css`
- Modify: `src/quant_trading/funds/app.py`

- [ ] **Step 1: Mount static in `app.py`**

```python
from fastapi.staticfiles import StaticFiles

_static = Path(__file__).resolve().parent / "static"
if _static.is_dir():
    app.mount("/static", StaticFiles(directory=str(_static)), name="static")
```

- [ ] **Step 2: Create `shell.html`**

Minimal structure (expand in Task 5):

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>行业仪表盘</title>
  <link rel="stylesheet" href="{{ bp }}static/fund-app/theme.css" />
  <script>
    window.__FUND_APP__ = {{ boot_json | safe }};
  </script>
</head>
<body>
  <div class="app-shell">
    <aside class="sidebar" id="sidebar"></aside>
    <div class="app-body">
      <header class="app-header">
        <h1 id="view-title">行业仪表盘</h1>
        <p class="sync-hint" id="sync-hint"></p>
      </header>
      <main id="app-main" class="app-main"></main>
    </div>
  </div>
  <div id="drawer-root" class="drawer-root hidden" aria-hidden="true"></div>
  <script type="module" src="{{ bp }}static/fund-app/main.js"></script>
</body>
</html>
```

Add helper in `app.py`:

```python
def _shell_boot() -> dict[str, str]:
    prefix = config.url_prefix().strip().rstrip("/")
    base = prefix or ""
    return {"base": base, "apiBase": f"{base}/api" if base else "/api"}


def _render_shell(request: Request, title: str = "行业仪表盘"):
    bp = f"{config.url_prefix().strip().rstrip('/')}/"
    if bp == "/":
        bp = "/"
    else:
        bp = f"{bp.strip('/')}/"
    return templates.TemplateResponse(
        request,
        "shell.html",
        {
            "bp": bp,
            "boot_json": json.dumps(_shell_boot()),
            "url_prefix": config.url_prefix(),
        },
    )
```

- [ ] **Step 3: Create `theme.css`**

Include: `.app-shell` grid `220px 1fr`, `.sidebar a.active`, `.drawer-root`, `.drawer-panel` `width:min(480px,92vw)`, `.up`/`.down` colors matching spec (`#f85149` / `#3fb950` dark), `.data-table` with `tabular-nums`, `.banner-error`.

- [ ] **Step 4: Commit**

```bash
git add src/quant_trading/funds/templates/shell.html src/quant_trading/funds/static/fund-app/theme.css src/quant_trading/funds/app.py
git commit -m "feat: add SPA shell template and static mount"
```

---

### Task 4: `api.js` + `router.js`

**Files:**
- Create: `src/quant_trading/funds/static/fund-app/api.js`
- Create: `src/quant_trading/funds/static/fund-app/router.js`

- [ ] **Step 1: Implement `api.js`**

```javascript
const cfg = window.__FUND_APP__ || { base: "", apiBase: "/api" };

export function appBase() {
  return cfg.base || "";
}

export function apiBase() {
  return cfg.apiBase || "/api";
}

export async function apiGet(path, params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") qs.set(k, v);
  });
  const url = `${apiBase()}${path}${qs.toString() ? `?${qs}` : ""}`;
  const r = await fetch(url);
  if (!r.ok) {
    const err = new Error(`${r.status} ${r.statusText}`);
    err.status = r.status;
    try {
      err.body = await r.json();
    } catch (_) {}
    throw err;
  }
  return r.json();
}

export function fmtYi(v) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  return n.toFixed(2);
}

export function fmtPct(v) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (Number.isNaN(n)) return "—";
  return `${n.toFixed(2)}%`;
}

export function pctClass(v) {
  const n = Number(v);
  if (Number.isNaN(n) || n === 0) return "";
  return n > 0 ? "up" : "down";
}
```

- [ ] **Step 2: Implement `router.js`**

Routes (path after stripping `appBase()`):

| Path | View id | Title |
|------|---------|-------|
| `/`, `` | `dashboard` | 行业仪表盘 |
| `/sectors` | `sectors` | 行业资金流向 |
| `/valuation` | `valuation` | 宽基 PE (Phase 2 stub) |
| `/funds` | `funds` | 基金目录 (stub) |
| `/advisor` | `advisor` | 基金 AI 助手 (stub) |
| `/crawler` | `crawler` | 爬虫任务 (stub) |

Export: `initRouter({ routes, onRoute, onDrawerQuery })` using `popstate` + `click` intercept on `a[data-nav]`.

Parse drawer from `URLSearchParams`: `drawer`, `industry`, `code`, `period`, `trade_date`.

`navigate(path, { replace, query })` uses `history.pushState`.

- [ ] **Step 3: Commit**

```bash
git add src/quant_trading/funds/static/fund-app/api.js src/quant_trading/funds/static/fund-app/router.js
git commit -m "feat: add SPA api helper and client router"
```

---

### Task 5: Drawer components

**Files:**
- Create: `src/quant_trading/funds/static/fund-app/components/drawer.js`
- Create: `src/quant_trading/funds/static/fund-app/components/sector-drawer.js`
- Create: `src/quant_trading/funds/static/fund-app/components/fund-drawer.js` (fund: minimal placeholder until Phase 2)

- [ ] **Step 1: `drawer.js`**

API: `openDrawer({ title, renderBody })`, `closeDrawer()`, backdrop click, Esc key, `aria-hidden` toggle.

- [ ] **Step 2: `sector-drawer.js`**

`openSectorDrawer({ industry, period, trade_date })` → `apiGet('/sectors/' + encodeURIComponent(industry), { period, trade_date })` → render summary + constituents table; show `fetch_error` if set; columns: 代码, 名称, 涨跌幅, 流通市值(亿).

- [ ] **Step 3: `fund-drawer.js` (Phase 1 stub)**

Show "基金详情在 Phase 2" or basic `apiGet('/funds/'+code)` name only — enough for dashboard link testing.

- [ ] **Step 4: Commit**

```bash
git add src/quant_trading/funds/static/fund-app/components/
git commit -m "feat: add sector drawer and drawer shell"
```

---

### Task 6: Dashboard view

**Files:**
- Create: `src/quant_trading/funds/static/fund-app/views/dashboard.js`
- Create: `src/quant_trading/funds/static/fund-app/main.js`

- [ ] **Step 1: `dashboard.js`**

On mount `#app-main`:

1. Parallel: `apiGet('/meta/flow')`, `apiGet('/dashboard', { period, trade_date, industry, fund_sort })` from current query state.
2. Toolbar: `<select>` period, trade_date, industry (industry change updates panel **without** drawer), fund_sort.
3. Two tables: top_in / top_out — columns 行业, 净额(亿), 涨跌; **row click** → `openSectorDrawer`.
4. If `summary`: show net/float cap; related funds table — code link → `openFundDrawer` (stub).
5. Banner if `!has_exposure`: exposure pipeline not ready.

Use `fmtYi` for `net_amt`. Submit toolbar → `navigate('/', { query: { period, trade_date, industry, fund_sort } })`.

- [ ] **Step 2: `main.js`**

```javascript
import { initRouter } from "./router.js";
import { apiGet } from "./api.js";
import { mountDashboard } from "./views/dashboard.js";
import { mountSectors } from "./views/sectors.js";
import { openSectorDrawer } from "./components/sector-drawer.js";
import { openFundDrawer } from "./components/fund-drawer.js";
import { closeDrawer } from "./components/drawer.js";

const NAV = [
  { path: "/", label: "行业仪表盘", view: "dashboard" },
  { path: "/sectors", label: "行业资金流向", view: "sectors" },
  { path: "/valuation", label: "宽基 PE", view: "valuation" },
  { path: "/funds", label: "基金目录", view: "funds" },
  { path: "/advisor", label: "基金 AI 助手", view: "advisor" },
  { path: "/crawler", label: "爬虫任务", view: "crawler", muted: true },
];

function renderSidebar(activePath) { /* fill #sidebar with data-nav links */ }

initRouter({
  onRoute({ path, query }) {
    renderSidebar(path);
    if (path === "/" || path === "") mountDashboard(query);
    else if (path === "/sectors") mountSectors(query);
    else document.getElementById("app-main").innerHTML =
      "<p class='muted'>本模块 Phase 2/3 实现</p>";
    handleDrawerQuery(query);
  },
});

function handleDrawerQuery(q) {
  if (q.drawer === "sector" && q.industry)
    openSectorDrawer({ industry: q.industry, period: q.period, trade_date: q.trade_date });
  else if (q.drawer === "fund" && q.code) openFundDrawer({ code: q.code });
  else closeDrawer();
}

apiGet("/sync/status").then((s) => {
  const el = document.getElementById("sync-hint");
  if (el) el.textContent = `基金 ${s.funds_stored} 只 · 同步 ${s.last_job?.finished_at || "—"}`;
}).catch(() => {});
```

- [ ] **Step 3: Commit**

```bash
git add src/quant_trading/funds/static/fund-app/views/dashboard.js src/quant_trading/funds/static/fund-app/main.js
git commit -m "feat: add dashboard SPA view and app bootstrap"
```

---

### Task 7: Sectors view

**Files:**
- Create: `src/quant_trading/funds/static/fund-app/views/sectors.js`

- [ ] **Step 1: Implement `sectors.js`**

- Load `meta/flow` + `apiGet('/sector-fund-flow', { period, trade_date, sort: 'net_desc', limit: 90 })`.
- Full sortable table (client sort on net_amt ok for 90 rows).
- Row click → `openSectorDrawer` + update URL query `drawer=sector&industry=…`.

- [ ] **Step 2: Commit**

```bash
git add src/quant_trading/funds/static/fund-app/views/sectors.js
git commit -m "feat: add sectors SPA view"
```

---

### Task 8: Wire shell routes + legacy redirects

**Files:**
- Modify: `src/quant_trading/funds/app.py`

- [ ] **Step 1: Replace HTML page handlers**

```python
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    return _render_shell(request, title="行业仪表盘")


@app.get("/sectors", response_class=HTMLResponse)
def sectors_spa(request: Request):
    return _render_shell(request, title="行业资金流向")


@app.get("/sectors/{industry:path}")
def sector_detail_redirect(industry: str, period: str = Query(default="即时"), trade_date: str = Query(default="")):
    from fastapi.responses import RedirectResponse
    prefix = config.url_prefix().rstrip("/")
    q = urlencode({"drawer": "sector", "industry": industry, "period": period, "trade_date": trade_date})
    return RedirectResponse(url=f"{prefix}/sectors?{q}", status_code=302)
```

Remove or guard old `TemplateResponse` for `dashboard.html`, `sectors.html`, `sector_detail.html` (delete routes body, keep functions only if tests reference — prefer delete).

- [ ] **Step 2: Manual test Phase 1**

```bash
cd /Users/wanghan/Documents/quant-trading
pip install -e ".[web,dev]"
export DATABASE_URL=...  # local mysql
FUND_WEB_PORT=8010 quant-trading-web
```

Open `http://127.0.0.1:8010/`:

- [ ] Sidebar switches dashboard ↔ sectors without full reload
- [ ] Top10 row opens drawer with constituents
- [ ] `http://127.0.0.1:8010/sectors/证券Ⅱ` redirects to sectors + drawer
- [ ] Refresh on `/?drawer=sector&industry=证券Ⅱ` reopens drawer
- [ ] `net_amt` displays as e.g. `10.91` not `1091267072`

- [ ] **Step 3: Commit**

```bash
git add src/quant_trading/funds/app.py
git commit -m "feat: serve SPA shell for dashboard and sectors routes"
```

---

## Phase 2 — Valuation + funds

### Task 9: Funds meta API

**Files:**
- Modify: `src/quant_trading/funds/app.py`
- Test: `tests/test_fund_web_spa_api.py`

- [ ] **Step 1: Add test**

```python
def test_meta_funds():
    with patch("quant_trading.funds.app.get_conn") as mock_dep:
        mock_dep.return_value = iter([MagicMock()])
        with patch("fund_platform.web_meta_queries.funds_catalog_meta") as m:
            m.return_value = {"category_options": [], "sort_options": [], "industry_options": []}
            r = client.get("/api/meta/funds")
    assert r.status_code == 200
```

- [ ] **Step 2: Add `@app.get("/api/meta/funds")`**

- [ ] **Step 3: pytest + commit**

```bash
git commit -m "feat: add funds catalog meta API"
```

---

### Task 10: Valuation view (port from `valuation.html`)

**Files:**
- Create: `src/quant_trading/funds/static/fund-app/views/valuation.js`
- Modify: `src/quant_trading/funds/static/fund-app/main.js`
- Modify: `src/quant_trading/funds/app.py` — `@app.get("/valuation")` → shell

- [ ] **Step 1: Copy Chart.js load**

In `shell.html` or valuation view only: `<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>` (match version in current template).

- [ ] **Step 2: Implement `valuation.js`**

- Tabs: cn / hk / us index PE via `api/valuation/indices` + row click → `api/valuation/indices/history` chart canvas.
- Second section: industry PE `api/valuation/industry` + history (port `_industry_pe_chart_points` logic from inline script in `valuation.html` lines ~300–400).
- Use `fmtYi` / `pe_num` equivalent for table cells.

- [ ] **Step 3: Wire router + redirect old valuation HTML route**

- [ ] **Step 4: Manual test** `/valuation` tab switching and chart render.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add valuation SPA view"
```

---

### Task 11: Funds view + fund drawer

**Files:**
- Create: `src/quant_trading/funds/static/fund-app/views/funds.js`
- Modify: `src/quant_trading/funds/static/fund-app/components/fund-drawer.js`
- Modify: `src/quant_trading/funds/app.py`

- [ ] **Step 1: `funds.js`**

- Filters from `meta/funds` + `api/funds` pagination.
- Table: code, name, type, nav, daily_pct — row → fund drawer.
- Pagination controls update query `page`, `per_page`.

- [ ] **Step 2: Complete `fund-drawer.js`**

- `apiGet('/funds/'+code)`, optional tabs: 概况 | 净值 (`nav-history?limit=60`) | 排名 (`peer-rank?limit=60`) lazy on click.
- Spinner while loading; `refresh=1` only on explicit refresh button.

- [ ] **Step 3: Redirect `@app.get("/funds/{code}")` → `/funds?drawer=fund&code=`**

- [ ] **Step 4: Replace `@app.get("/funds")` HTML with shell**

- [ ] **Step 5: Commit**

```bash
git commit -m "feat: add funds catalog SPA and fund drawer"
```

---

## Phase 3 — Advisor, crawler, cleanup

### Task 12: Advisor options API + view

**Files:**
- Modify: `src/quant_trading/funds/app.py`
- Create: `src/quant_trading/funds/static/fund-app/views/advisor.js`

- [ ] **Step 1: Add endpoint**

```python
@app.get("/api/advisor/options")
def api_advisor_options():
    return {"tag_options": advisor_prompt.tag_options()}
```

- [ ] **Step 2: `advisor.js`**

Port `advisor.html` behavior: tag checkboxes, `GET /api/advisor/prompt`, copy button, textarea parse → `POST /api/advisor/parse` with `{ text }`, render result cards with fund links calling `openFundDrawer`.

- [ ] **Step 3: Shell route `/advisor`**

- [ ] **Step 4: Commit**

```bash
git commit -m "feat: add advisor SPA view"
```

---

### Task 13: Crawler view

**Files:**
- Create: `src/quant_trading/funds/static/fund-app/views/crawler.js`

- [ ] **Step 1: Implement**

- `api/crawler/tasks` → task cards with schedule, last run status.
- Filter runs: `api/crawler/runs?task_key=&status=&limit=50`.
- Auto-refresh every 60s optional (setInterval, clear on view unmount).

- [ ] **Step 2: Shell route `/crawler`**

- [ ] **Step 3: Commit**

```bash
git commit -m "feat: add crawler SPA view"
```

---

### Task 14: Remove legacy templates + docs

**Files:**
- Delete or archive: `dashboard.html`, `sectors.html`, `sector_detail.html`, `index.html`, `valuation.html`, `advisor.html`, `crawler.html`, `detail.html` (fund detail fully in drawer — confirm no direct `/funds/{code}` HTML needed)
- Modify: `deploy/ecs/README.md`
- Modify: `src/quant_trading/funds/app.py` — remove dead `TemplateResponse` handlers and unused chart helpers only used by deleted templates (move kept helpers next to API if still needed)

- [ ] **Step 1: Grep for `TemplateResponse` — only `shell.html` remains**

Run: `rg "TemplateResponse" src/quant_trading/funds/app.py`

- [ ] **Step 2: Update ECS README**

Document entry: `https://<host>/quant-funds/` SPA only.

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove legacy fund HTML templates"
```

---

### Task 15: Nginx / prefix verification

**Files:**
- Modify: `deploy/ecs/README.md` (if needed)

- [ ] **Step 1: Test with `FUND_URL_PREFIX=/quant-funds`**

Static assets load at `/quant-funds/static/fund-app/main.js`; API at `/quant-funds/api/dashboard`.

- [ ] **Step 2: Fix `bp` in shell if broken** — `boot_json` must match nginx subpath.

- [ ] **Step 3: Commit any fix**

---

## Spec coverage self-review

| Spec requirement | Task |
|------------------|------|
| Left sidebar, 6 items | Task 4–6, 12–13 |
| JSON SPA | All view tasks |
| Drawer sector/fund | Task 5, 7, 11 |
| Path routing | Task 4, 8 |
| Drawer query params | Task 4–5, 8 |
| Legacy redirects | Task 8, 11 |
| API meta/sector/dashboard extend | Task 2 |
| Phase 1/2/3 scope | Phase sections |
| Amounts in 亿 | Task 6 (`fmtYi`) |
| Error/empty states | Task 5–7, 11 |

No TBD placeholders in task steps.

---

## Deploy checklist (after Phase 3)

- [ ] `push-and-setup.sh` or `deploy-remote.sh` to ECS
- [ ] `systemctl --user restart quant-trading-fund-web.service`
- [ ] Smoke: `/quant-funds/`, drawer deep link, `/quant-funds/api/meta/flow`
- [ ] Re-run sector flow backfill if bad 亿 data remains: `sync_sector_fund_flow_daily(date)`

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-26-fund-web-spa-shell.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — one subagent per task, review between tasks  
2. **Inline Execution** — run tasks in this session with executing-plans checkpoints  

Which approach do you want?
