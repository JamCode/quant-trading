from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from quant_trading.backtest.constants import (
    DEFAULT_INITIAL_CASH,
    MAX_BARS,
    MAX_SPAN_DAYS,
    MIN_BARS,
)
from quant_trading.backtest.engine import BacktestConfig, BacktestEngine
from fund_platform import market_index_queries

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


def _parse_date(value: str) -> date:
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


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
        fast = int((req.params or {}).get("fast", 10))
        slow = int((req.params or {}).get("slow", 40))
        if fast >= slow:
            raise ValueError("slow must be greater than fast")

    engine = BacktestEngine(BacktestConfig(initial_cash=float(req.initial_cash)))
    result = engine.run(ohlcv, strategy)
    summary = result.attrs["summary"]

    equity = [
        {"trade_date": ts.date().isoformat(), "equity": float(result.loc[ts, "equity"])}
        for ts in result.index
    ]

    first_close = float(ohlcv["close"].iloc[0])
    last_close = float(ohlcv["close"].iloc[-1])
    benchmark_return = (
        last_close / first_close - 1.0 if first_close > 0 else float("nan")
    )

    index_name = req.code.strip()
    snap = market_index_queries.query_market_index_snapshot(
        conn, req.code.strip(), trade_date=end.isoformat()
    )
    if snap and snap.get("name"):
        index_name = str(snap["name"])

    return {
        "summary": {
            "final_equity": float(summary["final_equity"]),
            "total_return": float(summary["total_return"]),
            "max_drawdown": float(summary["max_drawdown"]),
            "sharpe_ann_approx": float(summary["sharpe_ann_approx"]),
            "strategy": str(summary["strategy"]),
            "bars": int(len(ohlcv)),
            "benchmark_return": float(benchmark_return),
        },
        "equity": equity,
        "meta": {
            "code": req.code.strip(),
            "index_name": index_name,
            "strategy_id": req.strategy_id,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "benchmark_first_close": first_close,
            "benchmark_last_close": last_close,
        },
    }
