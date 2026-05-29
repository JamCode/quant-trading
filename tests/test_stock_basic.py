"""Unit tests for stock_basic helpers."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fund_platform.stock_basic import (
    stock_basic_row_params,
    update_stock_basic_industry,
    upsert_stock_basic,
)


class StockBasicTest(unittest.TestCase):
    def test_row_params_normalizes_code_and_industry(self) -> None:
        payload = [
            {"code": "1", "name": " 平安 ", "industry": "银行"},
            {"code": "000002", "name": "万科", "industry": ""},
            {"code": "", "name": "skip"},
        ]
        rows = stock_basic_row_params(payload, "2026-05-29 00:00:00")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], ("000001", "平安", "银行", "2026-05-29 00:00:00"))
        self.assertEqual(rows[1][2], None)

    def test_upsert_executemany(self) -> None:
        cur = MagicMock()
        payload = [{"code": "000001", "name": "平安", "industry": "银行"}]
        n = upsert_stock_basic(cur, payload, now="2026-05-29 00:00:00", chunk_size=500)
        self.assertEqual(n, 1)
        cur.executemany.assert_called_once()
        sql = cur.executemany.call_args[0][0]
        self.assertIn("stock_basic", sql)

    def test_update_industry_skips_blank(self) -> None:
        cur = MagicMock()
        update_stock_basic_industry(cur, "", "银行", now="t")
        update_stock_basic_industry(cur, "000001", "  ", now="t")
        cur.execute.assert_not_called()

    def test_update_industry_runs(self) -> None:
        cur = MagicMock()
        update_stock_basic_industry(cur, "1", "银行", now="2026-05-29 00:00:00")
        cur.execute.assert_called_once()
        args = cur.execute.call_args[0][1]
        self.assertEqual(args, ("银行", "2026-05-29 00:00:00", "000001"))


if __name__ == "__main__":
    unittest.main()
