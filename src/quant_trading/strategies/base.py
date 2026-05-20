from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """Strategy receives OHLCV and returns a signal column aligned to the index."""

    name: str = "strategy"

    @abstractmethod
    def generate_signals(self, ohlcv: pd.DataFrame) -> pd.Series:
        """Return numeric signals (e.g. -1/0/+1 for short/flat/long)."""

