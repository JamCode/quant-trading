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
