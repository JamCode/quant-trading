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
    assert out["summary"]["bars"] == 100
    assert len(out["equity"]) == 100
    assert out["meta"]["strategy_id"] == "sma_crossover"
