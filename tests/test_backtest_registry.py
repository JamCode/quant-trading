from quant_trading.strategies.registry import get_strategy_entry, list_strategies_for_api


def test_list_strategies_includes_sma():
    items = list_strategies_for_api()
    ids = [s["id"] for s in items]
    assert "sma_crossover" in ids


def test_get_strategy_entry_unknown():
    assert get_strategy_entry("nope") is None


def test_instantiate_sma_params():
    entry = get_strategy_entry("sma_crossover")
    assert entry is not None
    strat = entry.instantiate({"fast": 5, "slow": 20})
    assert strat.fast == 5
    assert strat.slow == 20
