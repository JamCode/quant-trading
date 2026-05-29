"""Contract tests for fund web SPA JSON endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from quant_trading.funds.app import app, get_conn

client = TestClient(app)


@pytest.fixture(autouse=True)
def _override_db_conn():
    conn = MagicMock()

    def _gen():
        yield conn

    app.dependency_overrides[get_conn] = _gen
    yield conn
    app.dependency_overrides.clear()


def test_meta_flow_shape():
    with patch("fund_platform.web_meta_queries.flow_meta") as fm:
        fm.return_value = {
            "period_options": ["即时"],
            "date_options": ["2026-05-25"],
            "default_period": "即时",
        }
        response = client.get("/api/meta/flow")
    assert response.status_code == 200
    body = response.json()
    assert body["period_options"] == ["即时"]
    assert body["date_options"] == ["2026-05-25"]


def test_api_dashboard_includes_meta_fields():
    with patch("quant_trading.funds.app.dashboard_queries") as dq:
        dq.sector_flow_top.side_effect = [([], "2026-05-25"), ([], "2026-05-25")]
        dq.default_focus_industry.return_value = "银行"
        dq.exposure_pipeline_ready.return_value = True
        dq.industry_options_from_flow.return_value = ["银行"]
        dq.sector_industry_summary.return_value = (None, None)
        dq.funds_for_industry.return_value = ([], "", True)
        response = client.get("/api/dashboard")
    assert response.status_code == 200
    body = response.json()
    assert body["industry_options"] == ["银行"]
    assert body["has_exposure"] is True
    assert "period_options" in body


def test_shell_home_returns_html():
    response = client.get("/")
    assert response.status_code == 200
    assert "fund-app/main.js" in response.text
    assert "app-shell" in response.text


def test_shell_backtest_returns_html():
    response = client.get("/backtest")
    assert response.status_code == 200
    assert "fund-app/main.js" in response.text


def test_meta_stocks_includes_board_and_industry_options():
    with patch("fund_platform.web_meta_queries.stocks_catalog_meta") as sm:
        sm.return_value = {
            "latest_trade_date": "2026-05-28",
            "trade_dates": ["2026-05-28"],
            "sort_options": [{"id": "change_pct", "label": "涨跌幅"}],
            "board_options": [{"id": "sh", "label": "沪市"}],
            "industry_options": ["半导体"],
        }
        response = client.get("/api/meta/stocks")
    assert response.status_code == 200
    body = response.json()
    assert body["board_options"][0]["id"] == "sh"
    assert body["industry_options"] == ["半导体"]


def test_api_stocks_passes_board_and_industry_filters():
    with patch("fund_platform.stock_queries.latest_stock_daily_date", return_value="2026-05-28"), patch(
        "fund_platform.stock_queries.query_stock_list", return_value=([], 0)
    ) as qsl:
        response = client.get(
            "/api/stocks",
            params={"board": "cyb", "industry": "半导体", "q": "300"},
        )
    assert response.status_code == 200
    qsl.assert_called_once()
    kwargs = qsl.call_args.kwargs
    assert kwargs["board"] == "cyb"
    assert kwargs["industry"] == "半导体"
    assert kwargs["q"] == "300"
