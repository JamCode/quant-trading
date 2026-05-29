"""Industry dropdown fallbacks for stock list."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fund_platform import stock_queries


@patch("fund_platform.stock_queries.latest_sector_constituent_date", return_value=None)
@patch("fund_platform.stock_queries.latest_stock_daily_date", return_value="2026-05-28")
def test_list_stock_industry_options_prefers_stock_daily(_ltd, _lscd):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.return_value = [{"industry": "银行"}]
    out = stock_queries.list_stock_industry_options(conn)
    assert out == ["银行"]


@patch("fund_platform.stock_queries.latest_sector_constituent_date", return_value=None)
@patch("fund_platform.stock_queries.latest_stock_daily_date", return_value="2026-05-28")
def test_list_stock_industry_options_falls_back_to_sector_flow(_ltd, _lscd):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.side_effect = [
        [],  # stock_daily
        [],  # stock_ths_industry
        [{"industry": "银行"}, {"industry": "白酒"}],  # sector_fund_flow
    ]
    out = stock_queries.list_stock_industry_options(conn)
    assert out == ["银行", "白酒"]


def test_industry_filter_ready_when_stock_daily_has_industry():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchone.return_value = {"ok": 1}
    assert stock_queries.industry_filter_ready(conn, trade_date="2026-05-28") is True
