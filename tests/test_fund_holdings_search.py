from fund_platform.fund_holdings_common import (
    normalize_stock_code,
    row_from_em_record,
    rows_from_holdings_payload,
)
from fund_platform.fund_holdings_queries import _search_tokens


def test_normalize_stock_code_global():
    assert normalize_stock_code("nvda") == "NVDA"
    assert normalize_stock_code("600519") == "600519"
    assert normalize_stock_code("00700") == "00700"
    assert normalize_stock_code("519") == "000519"


def test_row_from_em_record_overseas():
    row = row_from_em_record({"股票代码": "NVDA", "股票名称": "英伟达", "占净值比例": "10.14%"})
    assert row is not None
    assert row["stock_code"] == "NVDA"
    assert row["stock_name"] == "英伟达"


def test_search_tokens_name():
    mode, tokens = _search_tokens("英伟达")
    assert mode == "name"
    assert tokens == ["英伟达"]


def test_rows_from_holdings_payload():
    rows = rows_from_holdings_payload(
        {
            "stock_quarter": "2026年1季度",
            "stocks": [{"股票代码": "TSM", "股票名称": "台积电", "占净值比例": "9.5"}],
        }
    )
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "TSM"
