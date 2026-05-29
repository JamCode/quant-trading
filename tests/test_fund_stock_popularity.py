from fund_platform.fund_stock_popularity import _LATEST_HOLDINGS_SQL, _market_clause


def test_latest_holdings_sql_fragment():
    assert "MAX(report_date)" in _LATEST_HOLDINGS_SQL
    assert "fund_code" in _LATEST_HOLDINGS_SQL


def test_market_clause():
    cn_sql, cn = _market_clause("cn")
    assert cn == "cn"
    assert "6}" in cn_sql or "6$" in cn_sql
    g_sql, g = _market_clause("global")
    assert g == "global"
    assert "A-Za-z" in g_sql
