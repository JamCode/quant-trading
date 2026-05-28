from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from quant_trading.funds.app import app, get_conn

client = TestClient(app)


def test_list_backtest_strategies():
    response = client.get("/api/backtest/strategies")
    assert response.status_code == 200
    body = response.json()
    assert "strategies" in body
    assert any(s["id"] == "sma_crossover" for s in body["strategies"])


def test_run_backtest_mocked():
    fake_out = {
        "summary": {
            "final_equity": 110000.0,
            "total_return": 0.1,
            "max_drawdown": -0.05,
            "sharpe_ann_approx": 1.0,
            "strategy": "sma_crossover",
            "bars": 100,
            "benchmark_return": 0.08,
        },
        "equity": [{"trade_date": "2024-01-02", "equity": 100000.0}],
        "meta": {
            "code": "000300",
            "strategy_id": "sma_crossover",
            "start_date": "2024-01-01",
            "end_date": "2024-06-01",
        },
    }
    conn = MagicMock()

    def _gen():
        yield conn

    app.dependency_overrides[get_conn] = _gen
    try:
        with patch("quant_trading.funds.app.run_backtest", return_value=fake_out):
            response = client.post(
                "/api/backtest/run",
                json={
                    "code": "000300",
                    "strategy_id": "sma_crossover",
                    "params": {"fast": 10, "slow": 40},
                    "start_date": "2024-01-01",
                    "end_date": "2024-06-01",
                },
            )
        assert response.status_code == 200
        assert response.json()["summary"]["bars"] == 100
    finally:
        app.dependency_overrides.clear()
