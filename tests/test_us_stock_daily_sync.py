"""Unit tests for US stock daily sync helpers."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock

from fund_platform.us_stock_basic import (
    em_symbol_to_ticker,
    market_from_em_symbol,
    normalize_us_ticker,
    us_basic_row_from_spot,
)
from fund_platform.us_stock_daily import (
    _row_from_em_record,
    trade_date_us_eod,
    us_stock_daily_row_params,
)


class UsStockCodeTest(unittest.TestCase):
    def test_normalize_ticker(self) -> None:
        self.assertEqual(normalize_us_ticker("aapl"), "AAPL")
        self.assertEqual(em_symbol_to_ticker("105.MSFT"), "MSFT")
        self.assertIsNone(normalize_us_ticker(""))

    def test_market_from_em(self) -> None:
        self.assertEqual(market_from_em_symbol("105.AAPL"), "NYSE")

    def test_em_row(self) -> None:
        row = _row_from_em_record(
            {
                "代码": "105.AAPL",
                "名称": "苹果",
                "最新价": 200.0,
                "涨跌幅": 1.0,
                "涨跌额": 2.0,
                "开盘价": 198.0,
                "最高价": 201.0,
                "最低价": 197.0,
                "昨收价": 198.0,
                "成交量": 1000,
                "成交额": 1e10,
                "总市值": 3e12,
                "换手率": 0.5,
                "市盈率": 30.0,
                "振幅": 2.0,
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["code"], "AAPL")
        self.assertEqual(row["em_symbol"], "105.AAPL")

    def test_basic_row_from_spot(self) -> None:
        row = us_basic_row_from_spot(
            {"code": "NVDA", "name": "英伟达", "name_en": "NVIDIA", "em_symbol": "105.NVDA"}
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["code"], "NVDA")


class UsStockDailyHelpersTest(unittest.TestCase):
    def test_row_params_length(self) -> None:
        payload = [
            {
                "code": "AAPL",
                "name": "苹果",
                "price": 200.0,
                "change_pct": 1.0,
                "change_amt": 2.0,
                "open_px": 198.0,
                "high_px": 201.0,
                "low_px": 197.0,
                "prev_close": 198.0,
                "volume": 1000,
                "amount": 10.0,
                "total_market_cap": 300.0,
                "turnover_pct": 0.5,
                "pe_dynamic": 30.0,
                "amplitude_pct": 2.0,
            }
        ]
        rows = us_stock_daily_row_params("2026-05-29", payload, "2026-05-30 00:00:00")
        self.assertEqual(len(rows[0]), 17)

    def test_trade_date_is_date(self) -> None:
        self.assertIsInstance(trade_date_us_eod(), date)


if __name__ == "__main__":
    unittest.main()
