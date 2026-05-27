# A-Share Stocks Browser — Design Spec

**Date:** 2026-05-27  
**Status:** Approved (brainstorming)  
**Approach:** SPA list + detail with lazy K-line cache (方案 ①)

## Goal

Add first-class **stock browsing** to the fund web app: full A-share list with search/sort (A), and per-stock detail with daily snapshot plus price history chart (B). Reuse existing `stock_daily` crawler data; add on-demand AkShare history cached in MySQL (same pattern as `fund_nav_history`).

## User decisions (locked)

| Topic | Choice |
|-------|--------|
| Scope | A (market list) + B (stock detail) |
| K-line | Option 2: snapshot + lazy fetch/cache (`stock_price_daily`) |
| UI shell | fund-app SPA (not separate Jinja pages for stocks) |
| Chart | Chart.js via CDN (same as `/valuation`) |
| Adjust | Front-adjusted `qfq` only in v1; no UI toggle |
| Pre-crawl | None (no batch warmup job in v1) |

## Existing data (no new crawler for snapshots)

| Asset | Role |
|-------|------|
| `stock_daily` | ~5000+ rows/day: price, change%, caps, turnover, amount, PE/PB, 60d/YTD%, etc. |
| `stock_daily_sync` | Cron default 17:00 (`sync_stock_daily`) |
| `stock_ths_industry` | `code` → THS industry name(s) for a `trade_date` |
| `sector_industry_constituent` | Industry constituents (already JOIN `stock_daily` in UI) |

**Not in DB today:** per-stock OHLCV time series. `stock_daily` is a **cross-section per trade_date**, not historical K-line per symbol.

## Architecture overview

```
┌─────────────────┐     stock_daily_sync (cron)      ┌──────────────┐
│ Sina spot API   │ ───────────────────────────────► │ stock_daily  │
└─────────────────┘                                  └──────┬───────┘
                                                            │
┌─────────────────┐     ensure on API request               │ JOIN / lookup
│ AkShare EM hist │ ───────────────────────────────► │ stock_price_daily │
└─────────────────┘                                  └──────┬───────┘
                                                            │
                     ┌──────────────────────────────────────┘
                     ▼
              FastAPI /api/stocks*
                     ▼
              fund-app: /stocks, /stocks/{code}
```

## Backend

### New DDL: `schema/mysql/017_stock_price_daily.sql`

```sql
CREATE TABLE IF NOT EXISTS stock_price_daily (
  code VARCHAR(6) NOT NULL,
  trade_date DATE NOT NULL,
  open DECIMAL(14, 4) DEFAULT NULL,
  high DECIMAL(14, 4) DEFAULT NULL,
  low DECIMAL(14, 4) DEFAULT NULL,
  close DECIMAL(14, 4) DEFAULT NULL,
  volume BIGINT DEFAULT NULL COMMENT '成交量(股)',
  amount DECIMAL(18, 2) DEFAULT NULL COMMENT '成交额',
  change_pct DECIMAL(12, 4) DEFAULT NULL COMMENT '涨跌幅%',
  PRIMARY KEY (code, trade_date),
  KEY idx_stock_price_code_date (code, trade_date DESC)
) ENGINE=InnoDB ...;
```

v1 stores **qfq** rows only (no `adjust` column until a future HFQ/none UI exists).

### New module: `src/fund_platform/stock_price_history.py`

Mirror `nav_history.py`:

| Function | Behavior |
|----------|----------|
| `fetch_stock_price_daily_em(code)` | `ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")` → normalize columns to row dicts |
| `replace_stock_price_daily(conn, code, rows)` | `DELETE` + batch `INSERT` for that code |
| `query_stock_price_daily(conn, code, limit, offset, order)` | Paginated read |
| `ensure_stock_price_daily(conn, code, force=False)` | If no rows or `force`, fetch and replace; return `{ source, total }` |

### Extend: `src/fund_platform/stock_queries.py`

| Function | Behavior |
|----------|----------|
| `latest_stock_daily_date(conn)` | Already exists |
| `list_stock_daily_dates(conn, limit)` | Optional: recent trade dates for date picker |
| `query_stock_list(conn, trade_date, q, sort, order, limit, offset)` | Paginated list from `stock_daily`; `q` matches `code` or `name`; whitelist `sort` keys |
| `query_stock_snapshot(conn, code, trade_date?)` | Single row from `stock_daily` |
| `query_stock_industries(conn, code, trade_date?)` | From `stock_ths_industry` |

Serialization: continue `amount_to_yi` for `float_market_cap`, `total_market_cap`, `amount` via existing `_STOCK_YI_KEYS`.

### API endpoints (`src/quant_trading/funds/app.py`)

| Method | Path | Notes |
|--------|------|-------|
| GET | `/api/meta/stocks` | `latest_trade_date`, `trade_dates[]` (optional), `sort_options` |
| GET | `/api/stocks` | Query: `trade_date`, `q`, `sort`, `order`, `limit`, `offset` → `{ items, total, trade_date }` |
| GET | `/api/stocks/{code}` | Snapshot + `industries[]`; 404 if code invalid or no row for date |
| GET | `/api/stocks/{code}/price-history` | Query: `limit` (default 250), `order` (`asc` for chart), `refresh` (0/1) → `ensure_*` then `{ items, total, source }` |

**HTML shell routes:**

| GET | Handler |
|-----|---------|
| `/stocks` | `_render_shell(page_title="A 股行情")` |
| `/stocks/{code}` | Same shell (client mounts detail view) |

**Errors:**

- Invalid code (not 6 digits): `404`
- AkShare failure after ensure: `502` with message
- Empty `stock_daily` for site: list returns `total: 0` + meta hint

### Default list behavior

- `trade_date`: latest `MAX(stock_daily.trade_date)` when omitted
- `sort`: `change_pct`, `order`: `desc`
- `limit`: 50, `offset` for pagination (`page` computed in API or client)

## Frontend (fund-app)

### Navigation

Add to `main.js` `NAV` (after 基金目录):

```js
{ path: "/stocks", label: "A 股行情", title: "A 股行情" }
```

### Routing

Extend `onRoute` in `main.js`:

- `normalized === "/stocks"` → `mountStocks(query)`
- `normalized.match(/^\/stocks\/([0-9]{6})$/)` → `mountStockDetail(code, query)`

`router.js` sidebar clicks stay exact-path; list rows use `navigate("/stocks/" + code)`.

### `views/stocks.js` (list)

- Toolbar: data date (`trade_date`), search `q`, sort select, order toggle, submit
- Table columns: 代码, 名称, 现价, 涨跌幅%, 流通市值(亿), 换手率%, 成交额(亿), PE, PB, 60日%, 年初至今%
- Row click → `/stocks/{code}`
- Pagination via `page` query + prev/next buttons (pattern from `funds.js`)
- Empty state: link to `/crawler` when no snapshot data

### `views/stock-detail.js` (detail)

- Breadcrumb back to `/stocks`
- Snapshot card from `GET /api/stocks/{code}`
- Industry chips → `navigate("/sectors", { industry, period, trade_date })` or sector drawer
- Chart: reuse `loadChartJs()` from valuation pattern; `GET .../price-history?limit=250&order=asc`
- Button: refresh history (`refresh=1`)
- Load: snapshot first, then chart (show loading on chart area)

### Cross-links (v1)

| File | Change |
|------|--------|
| `templates/sector_detail.html` | Stock `code` → `{{ bp }}stocks/{{ s.code }}` |
| `components/sector-drawer.js` | If constituent table exists, link codes to `/stocks/{code}` |

**Deferred:** parsing `leader_stock` text into links; fund holdings stock links (optional follow-up).

## Out of scope (v1)

- Intraday / weekly K-line
- Adjust type UI (hfq / none)
- Batch pre-crawl of all symbols
- Stock detail in right drawer
- Standalone mobile layout
- New `stock_daily` crawler fields

## Testing

1. **API:** `curl` meta, list (`limit=5`), snapshot (`600519`), price-history (`limit=10`, then `refresh=1`)
2. **UI:** list sort/search/pagination; open detail; chart renders; refresh history; navigate from sector constituent link
3. **Regression:** existing sector/fund/crawler routes unchanged

## Implementation notes

- Register DDL `017` after `016` in deploy/README checklist
- AkShare calls only inside `stock_price_history` (lazy), not on list endpoint
- Consider rate limit: one ensure per code per request; no parallel duplicate ensures in v1
- `README.md` HTTP table: add `/stocks`, new API paths

## Phasing (single implementation plan)

One plan covers DDL + backend modules + APIs + both views + sector links. No multi-phase rollout required unless review splits PR.
