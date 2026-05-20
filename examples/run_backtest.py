#!/usr/bin/env python3
"""Run a demo backtest on synthetic OHLCV."""

from __future__ import annotations

from quant_trading.backtest.engine import BacktestEngine, BacktestConfig
from quant_trading.data.synthetic import fake_ohlcv_bars
from quant_trading.strategies.sma_crossover import SMACrossoverStrategy


def main() -> None:
    ohlcv = fake_ohlcv_bars(n=400, seed=7)
    strat = SMACrossoverStrategy(fast=10, slow=40)
    engine = BacktestEngine(BacktestConfig(initial_cash=100_000.0))
    result = engine.run(ohlcv, strat)
    summary = result.attrs["summary"]
    print(summary.to_string())


if __name__ == "__main__":
    main()
