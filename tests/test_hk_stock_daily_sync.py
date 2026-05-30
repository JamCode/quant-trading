"""Unit tests for HK stock daily sync helpers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fund_platform.hk_stock_basic import hk_basic_row_from_spot, normalize_hk_code
from fund_platform.hk_stock_daily import (
    _prune_hk_stock_daily_codes,
    hk_stock_daily_row_params,
)


class HkStockCodeTest(unittest.TestCase):
    def test_normalize_hk_code(self) -> None:
        self.assertEqual(normalize_hk_code("700"), "00700")
        self.assertEqual(normalize_hk_code("00700"), "00700")
        self.assertIsNone(normalize_hk_code("abc"))

    def test_basic_row_from_spot(self) -> None:
        row = hk_basic_row_from_spot(
            {
                "code": "00700",
                "name": "腾讯控股",
                "name_en": "TENCENT",
                "security_type": "股本",
            }
        )
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["code"], "00700")
        self.assertEqual(row["name_en"], "TENCENT")


class HkStockDailySyncHelpersTest(unittest.TestCase):
    def test_row_params_length(self) -> None:
        payload = [
            {
                "code": "00700",
                "name": "腾讯控股",
                "price": 400.0,
                "change_pct": 1.2,
                "change_amt": 4.8,
                "open_px": 395.0,
                "high_px": 405.0,
                "low_px": 394.0,
                "prev_close": 395.2,
                "volume": 1000,
                "amount": 12.3,
                "turnover_pct": 0.5,
                "pe_dynamic": 20.0,
                "pb": 3.0,
                "amplitude_pct": 2.0,
            }
        ]
        rows = hk_stock_daily_row_params("2026-05-30", payload, "2026-05-30 10:00:00")
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]), 17)

    def test_prune_removes_only_orphans(self) -> None:
        cur = MagicMock()
        cur.fetchall.return_value = [("00700",), ("00005",), ("99999",)]
        removed = _prune_hk_stock_daily_codes(cur, "2026-05-30", {"00700", "00005"})
        self.assertEqual(removed, 1)
        sql = cur.execute.call_args_list[-1][0][0]
        self.assertIn("DELETE", sql)
        self.assertIn("99999", cur.execute.call_args_list[-1][0][1])


if __name__ == "__main__":
    unittest.main()
