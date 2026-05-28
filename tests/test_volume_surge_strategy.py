import pandas as pd

from quant_trading.strategies.volume_surge import VolumeSurgeStrategy


def test_volume_surge_signals_on_spike_day():
    idx = pd.bdate_range("2024-01-01", periods=25)
    close = pd.Series([100.0] * 24 + [102.0], index=idx)
    volume = pd.Series([1000.0] * 24 + [3000.0], index=idx)
    ohlcv = pd.DataFrame({"close": close, "volume": volume})
    strat = VolumeSurgeStrategy(vol_ma=5, vol_ratio=1.5, trend_ma=0)
    sig = strat.generate_signals(ohlcv)
    assert float(sig.iloc[-1]) == 1.0
    assert float(sig.iloc[-2]) == 0.0


def test_volume_surge_rejects_low_ratio():
    try:
        VolumeSurgeStrategy(vol_ratio=0.9)
    except ValueError as exc:
        assert "vol_ratio" in str(exc)
    else:
        raise AssertionError("expected ValueError")
