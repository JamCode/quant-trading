from __future__ import annotations

import numpy as np
import pandas as pd


def fake_ohlcv_bars(n: int = 500, seed: int = 42) -> pd.DataFrame:
    """Geometric random walk close; derive open/high/low for demos only."""
    rng = np.random.default_rng(seed)
    rets = rng.normal(0.0003, 0.012, size=n)
    close = 100 * np.exp(np.cumsum(rets))
    open_ = np.roll(close, 1)
    open_[0] = close[0]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.003, size=n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.003, size=n))
    idx = pd.date_range("2024-01-01", periods=n, freq="1D")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": rng.integers(1_000, 10_000, n)},
        index=idx,
    )

