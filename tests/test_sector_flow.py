"""Sector fund flow normalization (THS / AkShare shape)."""

from __future__ import annotations

from unittest.mock import patch

import pandas as pd

from fund_platform.sector_flow import _normalize_row, fetch_sector_flow_ths


def test_normalize_row_instant_period():
    row = _normalize_row(
        "即时",
        {
            "行业": "白酒",
            "行业指数": 2263.65,
            "行业-涨跌幅": 4.17,
            "流入资金": 102.54,
            "流出资金": 73.9,
            "净额": 28.64,
            "公司家数": 20,
            "领涨股": "酒鬼酒",
            "领涨股-涨跌幅": 10.01,
            "当前价": 45.74,
        },
    )
    assert row is not None
    assert row["industry"] == "白酒"
    assert row["net_amt"] == 28.64
    assert row["inflow_amt"] == 102.54
    assert row["leader_stock"] == "酒鬼酒"


def test_normalize_row_rank_period():
    row = _normalize_row(
        "5日排行",
        {
            "行业": "元件",
            "公司家数": 62,
            "行业指数": 25648.3,
            "阶段涨跌幅": "12.55%",
            "流入资金": 720.26,
            "流出资金": 546.04,
            "净额": 174.22,
        },
    )
    assert row is not None
    assert row["change_pct"] == "12.55%"
    assert row["net_amt"] == 174.22
    assert row["leader_stock"] == ""


@patch("akshare.stock_fund_flow_industry")
def test_fetch_sector_flow_ths_maps_dataframe(mock_ak):
    mock_ak.return_value = pd.DataFrame(
        [
            {
                "序号": 1,
                "行业": "白酒",
                "行业指数": 2263.65,
                "行业-涨跌幅": 4.17,
                "流入资金": 102.54,
                "流出资金": 73.9,
                "净额": 28.64,
                "公司家数": 20,
                "领涨股": "酒鬼酒",
                "领涨股-涨跌幅": 10.01,
                "当前价": 45.74,
            }
        ]
    )
    with patch("fund_platform.sector_flow.fp_settings.ths_request_delay_sec", return_value=0):
        with patch("fund_platform.sector_flow.fp_settings.ths_retries", return_value=1):
            rows = fetch_sector_flow_ths("即时")
    assert len(rows) == 1
    assert rows[0]["industry"] == "白酒"
    mock_ak.assert_called_once_with(symbol="即时")
