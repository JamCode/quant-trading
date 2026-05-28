# Backtest Platform (Index v1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a personal-use index backtest page to the fund SPA: pick index + registered strategy params → synchronous run → equity curve and metrics (no DB persistence).

**Architecture:** `StrategyRegistry` lists server-side strategies; `IndexBarLoader` reads `market_index_daily` by date range; `BacktestService` validates, runs existing `BacktestEngine`, returns JSON; fund-app `/backtest` view calls two new API routes.

**Tech Stack:** Python 3.12, pandas, FastAPI, Pydantic request models, vanilla ES modules, ECharts 5 (CDN, reuse loader), pytest + `TestClient`, MySQL via existing `get_conn`.

**Spec:** `docs/superpowers/specs/2026-05-28-backtest-platform-design.md`

---

## File map

| Path | Role |
|------|------|
| `src/quant_trading/strategies/registry.py` | **Create** — `ParamSpec`, `StrategyEntry`, `list_strategies()`, `instantiate()` |
| `src/fund_platform/market_index_queries.py` | **Modify** — `query_market_index_bars(conn, code, start, end)` |
| `src/quant_trading/backtest/loaders.py` | **Create** — `load_index_ohlcv(conn, code, start, end) -> DataFrame` |
| `src/quant_trading/backtest/service.py` | **Create** — validation + run + serialize |
| `src/quant_trading/backtest/constants.py` | **Create** — `MAX_BARS=1500`, `MAX_SPAN_DAYS=1826`, `MIN_BARS=30` |
| `src/quant_trading/funds/app.py` | **Modify** — `GET/POST /api/backtest/*` |
| `tests/test_backtest_registry.py` | **Create** — registry + service unit tests |
| `tests/test_backtest_api.py` | **Create** — API contract tests (mocked DB) |
| `src/quant_trading/funds/static/fund-app/components/equity-chart.js` | **Create** — simple equity line chart (no dataZoom) |
| `src/quant_trading/funds/static/fund-app/views/backtest.js` | **Create** — form + results |
| `src/quant_trading/funds/static/fund-app/main.js` | **Modify** — nav + route |
| `src/quant_trading/funds/static/fund-app/theme.css` | **Modify** — `.backtest-form`, `.metric-cards` |

**Deferred (phase 2):** `StockBarLoader`, stock picker — not in this plan.

---

## Task 1: Strategy registry

**Files:**
- Create: `src/quant_trading/strategies/registry.py`
- Test: `tests/test_backtest_registry.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_backtest_registry.py
from quant_trading.strategies.registry import get_strategy_entry, list_strategies_for_api


def test_list_strategies_includes_sma():
    items = list_strategies_for_api()
    ids = [s["id"] for s in items]
    assert "sma_crossover" in ids


def test_get_strategy_entry_unknown():
    assert get_strategy_entry("nope") is None


def test_instantiate_sma_params():
    entry = get_strategy_entry("sma_crossover")
    assert entry is not None
    strat = entry.instantiate({"fast": 5, "slow": 20})
    assert strat.fast == 5
    assert strat.slow == 20
```

- [ ] **Step 2: Run tests (expect fail)**

```bash
cd /Users/wanghan/Documents/quant-trading
PYTHONPATH=src pytest tests/test_backtest_registry.py -v
```

Expected: `ModuleNotFoundError` or import error for `registry`.

- [ ] **Step 3: Implement registry**

```python
# src/quant_trading/strategies/registry.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

from quant_trading.strategies.sma_crossover import SMACrossoverStrategy
from quant_trading.strategies.base import Strategy

ParamType = Literal["int", "float"]


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: ParamType
    default: int | float
    min: int | float | None = None
    max: int | float | None = None
    label: str = ""

    def to_api(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "default": self.default,
            "min": self.min,
            "max": self.max,
            "label": self.label or self.name,
        }


@dataclass(frozen=True)
class StrategyEntry:
    id: str
    name: str
    description: str
    factory: Callable[..., Strategy]
    params: tuple[ParamSpec, ...]

    def instantiate(self, raw: dict[str, Any]) -> Strategy:
        kwargs: dict[str, Any] = {}
        for spec in self.params:
            val = raw.get(spec.name, spec.default)
            if spec.type == "int":
                val = int(val)
            else:
                val = float(val)
            if spec.min is not None and val < spec.min:
                raise ValueError(f"{spec.name} must be >= {spec.min}")
            if spec.max is not None and val > spec.max:
                raise ValueError(f"{spec.name} must be <= {spec.max}")
            kwargs[spec.name] = val
        return self.factory(**kwargs)

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "params": [p.to_api() for p in self.params],
        }


_REGISTRY: tuple[StrategyEntry, ...] = (
    StrategyEntry(
        id="sma_crossover",
        name="双均线交叉",
        description="快线在慢线上方做多，否则空仓",
        factory=SMACrossoverStrategy,
        params=(
            ParamSpec("fast", "int", default=10, min=2, max=120, label="快线"),
            ParamSpec("slow", "int", default=40, min=5, max=250, label="慢线"),
        ),
    ),
)


def list_strategies_for_api() -> list[dict[str, Any]]:
    return [e.to_api() for e in _REGISTRY]


def get_strategy_entry(strategy_id: str) -> StrategyEntry | None:
    for e in _REGISTRY:
        if e.id == strategy_id:
            return e
    return None
```

- [ ] **Step 4: Run tests**

```bash
PYTHONPATH=src pytest tests/test_backtest_registry.py -v
```

Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/quant_trading/strategies/registry.py tests/test_backtest_registry.py
git commit -m "feat(backtest): add strategy registry with SMA crossover"
```

---

## Task 2: Index bars query (MySQL)

**Files:**
- Modify: `src/fund_platform/market_index_queries.py`
- Test: `tests/test_backtest_registry.py` (append) or new `tests/test_market_index_bars_query.py`

- [ ] **Step 1: Write failing test (mock conn)**

Add to `tests/test_backtest_registry.py` or create `tests/test_market_index_bars_query.py`:

```python
from datetime import date
from unittest.mock import MagicMock

from fund_platform.market_index_queries import query_market_index_bars


def test_query_market_index_bars_maps_rows():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.return_value = [
        {
            "trade_date": date(2024, 1, 2),
            "open_px": 1.0,
            "high_px": 2.0,
            "low_px": 0.5,
            "close_px": 1.5,
            "volume": 100,
        }
    ]
    rows = query_market_index_bars(conn, "000300", start_date="2024-01-01", end_date="2024-12-31")
    assert len(rows) == 1
    assert rows[0]["trade_date"] == "2024-01-02"
    assert rows[0]["close"] == 1.5
    cur.execute.assert_called_once()
    sql = cur.execute.call_args[0][0]
    assert "trade_date >=" in sql
```

- [ ] **Step 2: Run test — expect FAIL** (`query_market_index_bars` not defined)

- [ ] **Step 3: Implement query** (append to `market_index_queries.py`):

```python
def query_market_index_bars(
    conn,
    code: str,
    *,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    sym = code.strip()
    if not sym:
        return []
    cur = _cursor(conn)
    cur.execute(
        """
        SELECT trade_date, open_px, high_px, low_px, close_px, volume
        FROM market_index_daily
        WHERE code = %s
          AND close_px IS NOT NULL
          AND trade_date >= %s
          AND trade_date <= %s
        ORDER BY trade_date ASC
        """,
        (sym, start_date[:10], end_date[:10]),
    )
    items: list[dict[str, Any]] = []
    for row in cur.fetchall():
        td = row["trade_date"]
        if isinstance(td, date):
            td = td.isoformat()
        td_s = str(td)[:10]
        close = row.get("close_px")
        items.append(
            {
                "trade_date": td_s,
                "open": float(row["open_px"]) if row.get("open_px") is not None else None,
                "high": float(row["high_px"]) if row.get("high_px") is not None else None,
                "low": float(row["low_px"]) if row.get("low_px") is not None else None,
                "close": float(close) if close is not None else None,
                "volume": row.get("volume"),
            }
        )
    return items
```

- [ ] **Step 4: Run test — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/fund_platform/market_index_queries.py tests/test_market_index_bars_query.py
git commit -m "feat: query market index OHLCV by date range for backtest"
```

---

## Task 3: Index OHLCV loader + constants

**Files:**
- Create: `src/quant_trading/backtest/constants.py`
- Create: `src/quant_trading/backtest/loaders.py`
- Test: extend `tests/test_backtest_registry.py` → rename to `tests/test_backtest_service.py` in Task 4

- [ ] **Step 1: Create constants**

```python
# src/quant_trading/backtest/constants.py
MAX_BARS = 1500
MIN_BARS = 30
MAX_SPAN_DAYS = 365 * 5  # 5 years
DEFAULT_INITIAL_CASH = 100_000.0
```

- [ ] **Step 2: Create loader**

```python
# src/quant_trading/backtest/loaders.py
from __future__ import annotations

import pandas as pd

from fund_platform import market_index_queries


def load_index_ohlcv(conn, code: str, *, start_date: str, end_date: str) -> pd.DataFrame:
    rows = market_index_queries.query_market_index_bars(
        conn, code, start_date=start_date, end_date=end_date
    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.set_index("trade_date").sort_index()
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
    else:
        df["volume"] = 0.0
    return df[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
```

- [ ] **Step 3: Commit**

```bash
git add src/quant_trading/backtest/constants.py src/quant_trading/backtest/loaders.py
git commit -m "feat(backtest): index OHLCV loader from MySQL"
```

---

## Task 4: BacktestService

**Files:**
- Create: `src/quant_trading/backtest/service.py`
- Create: `tests/test_backtest_service.py`

- [ ] **Step 1: Write failing service tests**

```python
# tests/test_backtest_service.py
from datetime import date, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest

from quant_trading.backtest.service import BacktestRunRequest, run_backtest


def _fake_ohlcv(n: int = 80) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=n)
    close = pd.Series(range(100, 100 + n), index=idx, dtype=float)
    return pd.DataFrame(
        {"open": close, "high": close + 1, "low": close - 1, "close": close, "volume": 1.0},
        index=idx,
    )


def test_run_backtest_rejects_fast_ge_slow(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(
        "quant_trading.backtest.service.load_index_ohlcv", lambda *a, **k: _fake_ohlcv()
    )
    req = BacktestRunRequest(
        code="000300",
        strategy_id="sma_crossover",
        params={"fast": 40, "slow": 10},
        start_date="2024-01-01",
        end_date="2024-06-01",
    )
    with pytest.raises(ValueError, match="slow"):
        run_backtest(conn, req)


def test_run_backtest_success(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(
        "quant_trading.backtest.service.load_index_ohlcv", lambda *a, **k: _fake_ohlcv(100)
    )
    req = BacktestRunRequest(
        code="000300",
        strategy_id="sma_crossover",
        params={"fast": 5, "slow": 20},
        start_date="2024-01-01",
        end_date="2024-06-01",
        initial_cash=100_000,
    )
    out = run_backtest(conn, req)
    assert "summary" in out
    assert out["summary"]["bars"] == 100
    assert len(out["equity"]) == 100
    assert out["meta"]["strategy_id"] == "sma_crossover"
```

- [ ] **Step 2: Run — expect FAIL**

```bash
PYTHONPATH=src pytest tests/test_backtest_service.py -v
```

- [ ] **Step 3: Implement service**

```python
# src/quant_trading/backtest/service.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from quant_trading.backtest.constants import (
    DEFAULT_INITIAL_CASH,
    MAX_BARS,
    MAX_SPAN_DAYS,
    MIN_BARS,
)
from quant_trading.backtest.engine import BacktestConfig, BacktestEngine
from quant_trading.backtest.loaders import load_index_ohlcv
from quant_trading.strategies.registry import get_strategy_entry


@dataclass
class BacktestRunRequest:
    code: str
    strategy_id: str
    params: dict[str, Any]
    start_date: str
    end_date: str
    initial_cash: float = DEFAULT_INITIAL_CASH


def _parse_date(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def run_backtest(conn, req: BacktestRunRequest) -> dict[str, Any]:
    entry = get_strategy_entry(req.strategy_id)
    if not entry:
        raise LookupError(f"unknown strategy_id: {req.strategy_id}")

    start = _parse_date(req.start_date)
    end = _parse_date(req.end_date)
    if start > end:
        raise ValueError("start_date must be <= end_date")
    if (end - start).days > MAX_SPAN_DAYS:
        raise ValueError(f"date range exceeds {MAX_SPAN_DAYS} calendar days")

    ohlcv = load_index_ohlcv(
        conn, req.code.strip(), start_date=start.isoformat(), end_date=end.isoformat()
    )
    if ohlcv.empty:
        raise ValueError("no bars in date range for this index code")
    if len(ohlcv) > MAX_BARS:
        raise ValueError(f"too many bars ({len(ohlcv)}), max {MAX_BARS}")
    if len(ohlcv) < MIN_BARS:
        raise ValueError(f"too few bars ({len(ohlcv)}), need at least {MIN_BARS}")

    try:
        strategy = entry.instantiate(req.params or {})
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    if req.strategy_id == "sma_crossover":
        fast = int(req.params.get("fast", 10))
        slow = int(req.params.get("slow", 40))
        if fast >= slow:
            raise ValueError("slow must be greater than fast")

    engine = BacktestEngine(BacktestConfig(initial_cash=float(req.initial_cash)))
    result = engine.run(ohlcv, strategy)
    summary = result.attrs["summary"]

    equity = [
        {"trade_date": ts.date().isoformat(), "equity": float(result.loc[ts, "equity"])}
        for ts in result.index
    ]

    return {
        "summary": {
            "final_equity": float(summary["final_equity"]),
            "total_return": float(summary["total_return"]),
            "max_drawdown": float(summary["max_drawdown"]),
            "sharpe_ann_approx": float(summary["sharpe_ann_approx"]),
            "strategy": str(summary["strategy"]),
            "bars": int(len(ohlcv)),
        },
        "equity": equity,
        "meta": {
            "code": req.code.strip(),
            "strategy_id": req.strategy_id,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    }
```

- [ ] **Step 4: Run tests — PASS**

- [ ] **Step 5: Commit**

```bash
git add src/quant_trading/backtest/service.py tests/test_backtest_service.py
git commit -m "feat(backtest): BacktestService with validation and serialization"
```

---

## Task 5: FastAPI routes

**Files:**
- Modify: `src/quant_trading/funds/app.py`
- Create: `tests/test_backtest_api.py`

- [ ] **Step 1: Write failing API tests**

```python
# tests/test_backtest_api.py
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from quant_trading.funds.app import app, get_conn

client = TestClient(app)


def test_list_backtest_strategies():
    response = client.get("/api/backtest/strategies")
    assert response.status_code == 200
    body = response.json()
    assert "strategies" in body
    assert any(s["id"] == "sma_crossover" for s in body["strategies"])


def test_run_backtest_mocked():
    fake_out = {
        "summary": {
            "final_equity": 110000.0,
            "total_return": 0.1,
            "max_drawdown": -0.05,
            "sharpe_ann_approx": 1.0,
            "strategy": "sma_crossover",
            "bars": 100,
        },
        "equity": [{"trade_date": "2024-01-02", "equity": 100000.0}],
        "meta": {
            "code": "000300",
            "strategy_id": "sma_crossover",
            "start_date": "2024-01-01",
            "end_date": "2024-06-01",
        },
    }
    conn = MagicMock()

    def _gen():
        yield conn

    app.dependency_overrides[get_conn] = _gen
    try:
        with patch("quant_trading.funds.app.run_backtest", return_value=fake_out):
            response = client.post(
                "/api/backtest/run",
                json={
                    "code": "000300",
                    "strategy_id": "sma_crossover",
                    "params": {"fast": 10, "slow": 40},
                    "start_date": "2024-01-01",
                    "end_date": "2024-06-01",
                },
            )
        assert response.status_code == 200
        assert response.json()["summary"]["bars"] == 100
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run — expect FAIL** (404 on routes)

- [ ] **Step 3: Add routes to `app.py`** (near other `/api` routes; add imports at top):

```python
from pydantic import BaseModel, Field

from quant_trading.backtest.service import BacktestRunRequest, run_backtest
from quant_trading.strategies.registry import list_strategies_for_api


class BacktestRunBody(BaseModel):
    code: str
    strategy_id: str
    params: dict = Field(default_factory=dict)
    start_date: str
    end_date: str
    initial_cash: float | None = None


@app.get("/api/backtest/strategies")
def api_backtest_strategies():
    return {"strategies": list_strategies_for_api()}


@app.post("/api/backtest/run")
def api_backtest_run(body: BacktestRunBody, conn=Depends(get_conn)):
    req = BacktestRunRequest(
        code=body.code,
        strategy_id=body.strategy_id,
        params=body.params,
        start_date=body.start_date,
        end_date=body.end_date,
        initial_cash=body.initial_cash or 100_000.0,
    )
    try:
        return run_backtest(conn, req)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 4: Run API tests — PASS**

```bash
PYTHONPATH=src pytest tests/test_backtest_api.py tests/test_backtest_service.py tests/test_backtest_registry.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/quant_trading/funds/app.py tests/test_backtest_api.py
git commit -m "feat(api): backtest strategies list and sync run endpoints"
```

---

## Task 6: Equity chart component

**Files:**
- Create: `src/quant_trading/funds/static/fund-app/components/equity-chart.js`

- [ ] **Step 1: Add component** (reuse `loadEcharts` from `market-kline-chart.js`):

```javascript
// components/equity-chart.js
import { loadEcharts } from "./market-kline-chart.js";

export async function mountEquityChart(el, points) {
  if (!el || !points?.length) {
    return () => {};
  }
  const echarts = await loadEcharts();
  const chart = echarts.init(el, null, { renderer: "canvas" });
  const dates = points.map((p) => p.trade_date);
  const values = points.map((p) => p.equity);
  chart.setOption({
    animation: false,
    backgroundColor: "transparent",
    grid: { left: 56, right: 16, top: 24, bottom: 32 },
    tooltip: {
      trigger: "axis",
      backgroundColor: "rgba(22,27,34,0.95)",
      borderColor: "#30363d",
      textStyle: { color: "#e6edf3" },
    },
    xAxis: {
      type: "category",
      data: dates,
      boundaryGap: false,
      axisLabel: { color: "#8b949e", fontSize: 11 },
      axisLine: { lineStyle: { color: "#30363d" } },
    },
    yAxis: {
      scale: true,
      axisLabel: { color: "#8b949e" },
      splitLine: { lineStyle: { color: "#21262d" } },
    },
    series: [
      {
        type: "line",
        data: values,
        showSymbol: false,
        lineStyle: { width: 2, color: "#4da3ff" },
        areaStyle: {
          color: "rgba(77,163,255,0.12)",
        },
      },
    ],
  });
  const onResize = () => chart.resize();
  window.addEventListener("resize", onResize);
  return () => {
    window.removeEventListener("resize", onResize);
    chart.dispose();
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add src/quant_trading/funds/static/fund-app/components/equity-chart.js
git commit -m "feat(ui): equity line chart component for backtest results"
```

---

## Task 7: Backtest SPA view

**Files:**
- Create: `src/quant_trading/funds/static/fund-app/views/backtest.js`
- Modify: `src/quant_trading/funds/static/fund-app/theme.css`

- [ ] **Step 1: Add CSS**

```css
/* theme.css — append */
.backtest-layout {
  display: grid;
  gap: 1rem;
}
.backtest-form {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(10rem, 1fr));
  gap: 0.75rem 1rem;
  align-items: end;
}
.backtest-form label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.85rem;
  color: var(--muted);
}
.backtest-form input,
.backtest-form select {
  padding: 0.35rem 0.5rem;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--row-alt);
  color: var(--text);
}
.metric-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(8rem, 1fr));
  gap: 0.75rem;
}
.metric-card {
  padding: 0.6rem 0.75rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--row-alt);
}
.metric-card dt {
  margin: 0;
  font-size: 0.75rem;
  color: var(--muted);
}
.metric-card dd {
  margin: 0.2rem 0 0;
  font-size: 1.05rem;
  font-weight: 600;
}
.equity-chart-wrap {
  height: 320px;
  min-height: 280px;
}
.equity-chart {
  width: 100%;
  height: 100%;
}
```

- [ ] **Step 2: Implement `views/backtest.js`**

Key behaviors:
- On mount: `GET /api/backtest/strategies`, `GET /api/market-indices?region=cn` (or filter 6-digit codes from `region=all`).
- Default dates: `end_date` = today ISO; `start_date` = end − 3 years (use JS `Date`).
- Strategy change → re-render param inputs from schema.
- Submit: `POST /api/backtest/run` with JSON body; show loading on button.
- Success: metric cards (`total_return` as %, `max_drawdown` as %, sharpe, `final_equity`, `bars`); `mountEquityChart` on `.equity-chart`.
- Error: `err.body?.detail` in `.banner-error`.
- Hint paragraph per spec.

Export: `export async function mountBacktest()`.

- [ ] **Step 3: Manual smoke (local)**

```bash
export DATABASE_URL='mysql+pymysql://...'
pip install -e ".[web]"
python examples/run_web.py
# open /backtest under FUND_URL_PREFIX
```

- [ ] **Step 4: Commit**

```bash
git add src/quant_trading/funds/static/fund-app/views/backtest.js src/quant_trading/funds/static/fund-app/theme.css
git commit -m "feat(ui): backtest page with form and equity results"
```

---

## Task 8: Wire router and navigation

**Files:**
- Modify: `src/quant_trading/funds/static/fund-app/main.js`

- [ ] **Step 1: Update `main.js`**

Add to `NAV` (after `/indices`):

```javascript
{ path: "/backtest", label: "策略回测", title: "策略回测" },
```

Import and route:

```javascript
import { mountBacktest } from "./views/backtest.js";
// in onRoute:
} else if (normalized === "/backtest") {
  await mountBacktest(query);
```

Update `renderSidebar` active check if needed (exact path match only).

- [ ] **Step 2: Verify** — sidebar shows「策略回测」, page loads.

- [ ] **Step 3: Commit**

```bash
git add src/quant_trading/funds/static/fund-app/main.js
git commit -m "feat(ui): add /backtest route to fund SPA shell"
```

---

## Task 9: Integration verification

- [ ] **Step 1: Run full test suite for backtest**

```bash
PYTHONPATH=src pytest tests/test_backtest_registry.py tests/test_backtest_service.py tests/test_backtest_api.py tests/test_fund_web_spa_api.py -v
```

Expected: all PASS.

- [ ] **Step 2: Manual ECS/local check**

- Index `000300`, SMA 10/40, ~3y range.
- Response < 5s; equity chart renders; no console errors.
- `GET /api/backtest/strategies` returns `sma_crossover`.

- [ ] **Step 3: Update deploy note (optional one line in `deploy/ecs/README.md`)**

Mention `/backtest` page and that new strategies require registry edit + deploy.

- [ ] **Step 4: Commit if README touched**

```bash
git add deploy/ecs/README.md
git commit -m "docs(ecs): note backtest SPA route"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Strategy registry + SMA | Task 1 |
| Index bars by date range | Task 2–3 |
| Bar limits / validation | Task 4 (`constants.py`) |
| Sync API GET/POST | Task 5 |
| SPA form + metrics + chart | Task 6–8 |
| No DB persistence | (no task — omitted by design) |
| Phase 2 stocks | Out of plan |

---

## Plan self-review

- No TBD/TODO placeholders in task steps.
- `BacktestRunRequest` / `BacktestRunBody` / `run_backtest` naming consistent.
- Reuses existing `BacktestEngine` without modification.
