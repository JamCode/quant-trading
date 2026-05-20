from __future__ import annotations

import pandas as pd

from quant_trading.strategies.base import Strategy


class SMACrossoverStrategy(Strategy):
    """Long when fast SMA is above slow SMA; flat otherwise."""

    name = "sma_crossover"

    def __init__(self, fast: int = 10, slow: int = 30) -> None:
        if fast >= slow:
            raise ValueError("fast window must be < slow window")
        self.fast = fast
        self.slow = slow

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"]
        fast_sma = close.rolling(self.fast, min_periods=self.fast).mean()
        slow_sma = close.rolling(self.slow, min_periods=self.slow).mean()
        long_mask = fast_sma > slow_sma
        return long_mask.astype(float)

