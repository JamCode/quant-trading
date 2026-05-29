"""Unit tests for stock_daily sync helpers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fund_platform.stock_daily import _prune_stock_daily_codes, _stock_daily_row_params


class StockDailySyncHelpersTest(unittest.TestCase):
    def test_row_params_length(self) -> None:
        payload = [{"code": "000001", "name": "平安", "price": 1.0, "change_pct": 0.1,
                    "float_market_cap": 1.0, "total_market_cap": 2.0, "turnover_pct": 0.5,
                    "amount": 3.0, "pe_dynamic": None, "pb": None, "volume_ratio": None,
                    "amplitude_pct": None, "change_5m_pct": None, "speed_pct": None,
                    "change_60d_pct": None, "change_ytd_pct": None}]
        rows = _stock_daily_row_params("2026-05-28", payload, "2026-05-28 10:00:00")
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 18)

    def test_prune_removes_only_orphans(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = [("000001",), ("000002",), ("999999",)]
        removed = _prune_stock_daily_codes(cur, "2026-05-28", {"000001", "000002"})
        self.assertEqual(removed, 1)
        cur.execute.assert_called()
        sql = cur.execute.call_args_list[-1][0][0]
        self.assertIn("DELETE", sql)
        self.assertIn("999999", cur.execute.call_args_list[-1][0][1])


if __name__ == "__main__":
    unittest.main()
