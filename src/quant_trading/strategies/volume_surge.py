from __future__ import annotations

import pandas as pd

from quant_trading.strategies.base import Strategy


class VolumeSurgeStrategy(Strategy):
    """量价齐升：放量且收涨时做多，可选趋势过滤（收盘在均线上方）。"""

    name = "volume_surge"

    def __init__(
        self,
        vol_ma: int = 20,
        vol_ratio: float = 1.2,
        trend_ma: int = 0,
    ) -> None:
        if vol_ma < 5:
            raise ValueError("vol_ma must be >= 5")
        if vol_ratio < 1.0:
            raise ValueError("vol_ratio must be >= 1.0")
        if trend_ma < 0:
            raise ValueError("trend_ma must be >= 0")
        self.vol_ma = vol_ma
        self.vol_ratio = vol_ratio
        self.trend_ma = trend_ma

    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        close = ohlcv["close"].astype(float)
        volume = ohlcv["volume"].astype(float).fillna(0.0)

        vol_avg = volume.rolling(self.vol_ma, min_periods=self.vol_ma).mean()
        surge = volume > vol_avg * self.vol_ratio
        price_up = close > close.shift(1)

        long_mask = surge & price_up
        if self.trend_ma > 0:
            trend_line = close.rolling(self.trend_ma, min_periods=self.trend_ma).mean()
            long_mask = long_mask & (close > trend_line)

        return long_mask.fillna(False).astype(float)
