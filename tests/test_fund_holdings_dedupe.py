from fund_platform.fund_holdings_common import dedupe_holdings_rows


def test_dedupe_holdings_rows_keeps_higher_weight() -> None:
    rows = dedupe_holdings_rows(
        [
            {"stock_code": "600089", "stock_name": "A", "weight_pct": 1.0},
            {"stock_code": "600089", "stock_name": "B", "weight_pct": 3.5},
        ]
    )
    assert len(rows) == 1
    assert rows[0]["weight_pct"] == 3.5
    assert rows[0]["stock_name"] == "B"
