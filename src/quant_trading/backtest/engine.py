from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from quant_trading.strategies.base import Strategy


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100_000.0
    commission_rate: float = 0.0005  # per trade notional
    slippage_bps: float = 1.0  # applied against trade direction


class BacktestEngine:
    """Long-only, fully invested when signal > 0; simplified fills on close."""

    def __init__(self, cfg: BacktestConfig | None = None) -> None:
        self.cfg = cfg or BacktestConfig()

    def run(self, ohlcv: pd.DataFrame, strategy: Strategy) -> pd.DataFrame:
        signal = strategy.generate_signals(ohlcv).reindex(ohlcv.index).fillna(0.0)
        close = ohlcv["close"].astype(float)

        cash = self.cfg.initial_cash
        shares = 0.0
        equity_hist: list[float] = []

        for ts, px in close.items():
            target_long = float(signal.loc[ts]) > 0
            equity_before = cash + shares * px

            # Rebalance to full long or flat at close (demo semantics)
            if target_long:
                slip = self.cfg.slippage_bps / 10_000.0
                eff_buy = px * (1 + slip)
                notional = equity_before
                fee = notional * self.cfg.commission_rate
                shares = (notional - fee) / eff_buy
                cash = 0.0
            else:
                slip = self.cfg.slippage_bps / 10_000.0
                eff_sell = px * (1 - slip)
                if shares > 0:
                    proceeds = shares * eff_sell
                    fee = proceeds * self.cfg.commission_rate
                    cash = proceeds - fee
                    shares = 0.0
                # Already flat: keep cash unchanged (avoid zeroing cash when shares == 0)

            equity = cash + shares * px
            equity_hist.append(equity)

        equity_s = pd.Series(equity_hist, index=close.index, name="equity")
        rets = equity_s.pct_change().fillna(0.0)
        sharpe = _annualized_sharpe(rets)
        dd = _max_drawdown(equity_s)

        start_eq = float(equity_s.iloc[0])
        total_ret = float(equity_s.iloc[-1] / start_eq - 1) if start_eq > 0 else float("nan")
        summary = pd.Series(
            {
                "strategy": strategy.name,
                "final_equity": equity_s.iloc[-1],
                "total_return": total_ret,
                "max_drawdown": dd,
                "sharpe_ann_approx": sharpe,
            }
        )
        out = pd.DataFrame({"equity": equity_s, "signal": signal})
        out.attrs["summary"] = summary
        return out


def _annualized_sharpe(daily_returns: pd.Series, trading_days: int = 252) -> float:
    r = daily_returns.dropna()
    if r.std(ddof=1) == 0 or len(r) < 2:
        return float("nan")
    return float(np.sqrt(trading_days) * r.mean() / r.std(ddof=1))


def _max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = equity / peak - 1.0
    return float(dd.min())

