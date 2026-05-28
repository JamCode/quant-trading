# Quant Strategy Backtest Platform — Design Spec

**Date:** 2026-05-28  
**Status:** Approved (brainstorming)  
**Approach:** Strategy registry + synchronous API + new fund-app SPA page (方案 1)

## Goal

Add a **personal-use backtest** flow inside the existing fund Web SPA: pick an index, pick a **server-registered** strategy and parameters, run a **synchronous** backtest (≤ ~3 years daily bars, results in seconds), view equity curve and summary metrics. No DB persistence of runs in v1.

## User decisions (locked)

| Topic | Choice |
|-------|--------|
| Audience | Personal use only (no multi-user / sharing) |
| Instruments (v1) | **A-share indices** (`market_index_daily`); stocks in phase 2 |
| Strategy authoring | Local Python `Strategy` subclasses; **registry** exposes id + param schema to Web |
| Execution | **Synchronous** HTTP; target ≤ few seconds for ≤ ~3y daily bars |
| History | **Do not persist** backtest runs; ephemeral results per request |
| UI shell | New route in existing fund-app SPA (same FastAPI service) |

## Out of scope (v1)

- Stock / fund NAV backtests
- In-browser Python or formula editor
- Saved backtest history, comparison gallery, job queue
- Short selling, leverage, partial positions, multi-asset portfolios
- Parameter optimization / grid search
- Replacing or heavily rewriting `BacktestEngine` fill semantics

## Context: existing code

| Piece | Location | Notes |
|-------|----------|--------|
| Backtest engine | `src/quant_trading/backtest/engine.py` | Long-only, rebalance at close, commission + slippage |
| Strategy ABC | `src/quant_trading/strategies/base.py` | `generate_signals(ohlcv) -> Series` |
| Example strategy | `src/quant_trading/strategies/sma_crossover.py` | Register as first built-in |
| Demo entry | `examples/run_backtest.py` | Synthetic data only today |
| Index daily data | `market_index_daily` + `query_market_index_history` | Already used by index detail charts |
| Web app | `src/quant_trading/funds/app.py` + `static/fund-app/` | FastAPI + SPA |

## Architecture

```
fund-app (SPA)                 FastAPI (funds/app.py)
    │                               │
    │  GET  /api/backtest/strategies │
    │  POST /api/backtest/run        │
    └───────────────────────────────┼──► backtest/service.py
                                    │         ├─ StrategyRegistry
                                    │         ├─ IndexBarLoader → MySQL
                                    │         └─ BacktestEngine (existing)
```

### Units

1. **`StrategyRegistry`** — Maps `strategy_id` → class, display name, description, `ParamSpec[]` for Web forms.
2. **`IndexBarLoader`** — `(code, start_date, end_date)` → OHLCV `DataFrame` (DatetimeIndex, columns `open/high/low/close/volume`).
3. **`BacktestService`** — Validates input, loads bars, instantiates strategy with params, runs engine, returns DTO.
4. **API routes** — Thin wrappers; no business logic.
5. **SPA `views/backtest.js`** — Form + results chart/metrics.

## Strategy registration (developer workflow)

1. Implement `Strategy` subclass under `src/quant_trading/strategies/`.
2. Add entry to `src/quant_trading/strategies/registry.py`:

```python
REGISTRY = [
    StrategyEntry(
        id="sma_crossover",
        name="双均线交叉",
        description="快线上穿慢线做多，下穿空仓",
        cls=SMACrossoverStrategy,
        params=[
            ParamSpec("fast", "int", default=10, min=2, max=120),
            ParamSpec("slow", "int", default=40, min=5, max=250),
        ],
    ),
]
```

3. Deploy (`git pull` on ECS). Web lists new strategy via `GET /api/backtest/strategies` without front-end code changes.

**Constraint:** `slow > fast` (and similar) validated in service before run; invalid params → 400 with message.

## Data loading

- **Source:** `market_index_daily` for `code` (6-digit CN index).
- **Query:** Reuse or extend `market_index_queries` with explicit `start_date` / `end_date` filter (ascending).
- **Limits (v1):**
  - Max calendar span: **5 years** (config constant).
  - Max bars: **1500** trading days (reject with 400 if exceeded after load).
  - Require ≥ **30** bars after filter.
- **Missing data:** If no rows in range → 404 / 400 with clear detail.

Phase 2 adds `StockBarLoader` behind the same service interface; API gains `instrument_type` or unified symbol rules (not in v1).

## Backtest execution

- Use existing `BacktestEngine` + `BacktestConfig` (`initial_cash`, `commission_rate`, `slippage_bps`).
- v1: `initial_cash` optional in API (default 100_000); commission/slippage **not** exposed in UI (engine defaults).
- Output serialization:
  - `summary`: `final_equity`, `total_return`, `max_drawdown`, `sharpe_ann_approx`, `strategy`, `bars`
  - `equity`: `[{ trade_date, equity }]` (daily, asc)
  - `meta`: `code`, `index_name`, `start_date`, `end_date`, `strategy_id`

No storage to MySQL.

## API contract

Base: same as fund API (`/api/...`).

### `GET /api/backtest/strategies`

Response:

```json
{
  "strategies": [
    {
      "id": "sma_crossover",
      "name": "双均线交叉",
      "description": "...",
      "params": [
        { "name": "fast", "type": "int", "default": 10, "min": 2, "max": 120, "label": "快线" }
      ]
    }
  ]
}
```

### `POST /api/backtest/run`

Request body:

```json
{
  "code": "000300",
  "strategy_id": "sma_crossover",
  "params": { "fast": 10, "slow": 40 },
  "start_date": "2023-01-01",
  "end_date": "2026-05-27",
  "initial_cash": 100000
}
```

Response `200`:

```json
{
  "summary": { "final_equity": 112345.6, "total_return": 0.123, "max_drawdown": -0.08, "sharpe_ann_approx": 0.95, "bars": 600 },
  "equity": [{ "trade_date": "2023-01-03", "equity": 100000 }],
  "meta": { "code": "000300", "name": "沪深300", "strategy_id": "sma_crossover", "start_date": "...", "end_date": "..." }
}
```

Errors: `400` validation, `404` unknown code/strategy, `422` insufficient data.

## Frontend (fund-app)

### Navigation

- Sidebar item: **回测** → route `/backtest` (under `FUND_URL_PREFIX`).
- Register in `router.js` + `views/backtest.js`.

### Page layout

1. **Config panel**
   - Index: dropdown populated from existing market-indices list API (CN indices).
   - Strategy: dropdown from `GET /api/backtest/strategies`.
   - Dynamic params: render from selected strategy `params` schema (number inputs).
   - Date range: `start_date`, `end_date` (default: end = latest available, start = end − 3 years).
   - Button: **运行回测** (disabled while loading).
   - Hint: 「策略在服务端代码中注册，本页仅选择参数」.

2. **Results panel** (after success)
   - Metric cards: 总收益率、最大回撤、Sharpe（近似）、期末权益、样本交易日数.
   - Equity line chart (reuse ECharts loader from `market-kline-chart.js` or thin wrapper; **no** candlestick / no dataZoom slider).
   - On error: banner with API message.

### UX

- Synchronous: show spinner on button; no job polling.
- No result persistence; refresh page clears results.

## Error handling

| Case | Behavior |
|------|----------|
| Unknown `code` / `strategy_id` | 404 |
| `start_date` > `end_date` | 400 |
| Range > 5y or bars > 1500 | 400 |
| < 30 bars | 400 |
| DB / unexpected | 500, log server-side |

## Testing

- **Unit:** `BacktestService` with small in-memory OHLCV; registry param validation; `slow <= fast` rejected.
- **API:** `tests/test_backtest_api.py` — `GET strategies` shape; `POST run` with test DB or mocked loader (follow `tests/test_fund_web_spa_api.py` patterns).
- **Manual:** ECS/local — 000300, SMA 10/40, 3y range, < 5s response.

## Phasing

| Phase | Deliverable |
|-------|-------------|
| **1 (v1)** | Registry, index loader, API, SPA page, SMA strategy registered |
| **2** | `StockBarLoader`, instrument picker extension, same API surface |

## Files (expected touch list)

| Action | Path |
|--------|------|
| Add | `src/quant_trading/strategies/registry.py` |
| Add | `src/quant_trading/backtest/service.py` |
| Add | `src/quant_trading/backtest/loaders.py` (or `data/index_bars.py`) |
| Modify | `src/quant_trading/funds/app.py` (routes) |
| Add | `src/quant_trading/funds/static/fund-app/views/backtest.js` |
| Modify | `src/quant_trading/funds/static/fund-app/router.js`, shell nav |
| Add | `tests/test_backtest_api.py` |
| Optional | `theme.css` — form layout for backtest panel |

## Security / ops

- Same auth as existing fund Web (none extra in v1; if nginx auth exists, unchanged).
- Backtest is CPU-bound but bounded by bar limit; no unbounded scans.
- No user-supplied code execution.

## Open questions (deferred)

- Expose commission/slippage in UI → later if needed.
- HK/global indices in picker → only if `market_index_daily` has series.
- Async jobs → only if sync limits become painful.
