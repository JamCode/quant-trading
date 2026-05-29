from fund_platform.fund_catalog_queries import _category_clause


def test_category_money():
    sql, params = _category_clause("money")
    assert "fund_type" in sql
    assert params == ["%货币%"]
