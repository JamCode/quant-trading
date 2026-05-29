from fund_platform.fund_stock_popularity import _LATEST_HOLDINGS_SQL


def test_latest_holdings_sql_fragment():
    assert "MAX(report_date)" in _LATEST_HOLDINGS_SQL
    assert "fund_code" in _LATEST_HOLDINGS_SQL
