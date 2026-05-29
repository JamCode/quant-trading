"""Tests for intraday live quote helpers."""

from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from fund_platform.market_index import _global_em_row_from_record
from fund_platform.market_index_queries import _REGION_HK, intraday_quote_is_live

_CN = ZoneInfo("Asia/Shanghai")


class GlobalEmRowTest(unittest.TestCase):
    def test_hsi_change_pct_not_multiplied_by_100(self) -> None:
        row = _global_em_row_from_record(
            {
                "代码": "HSI",
                "名称": "恒生指数",
                "最新价": 2_508_634,
                "昨收价": 2_500_616,
                "涨跌幅": 32,
                "涨跌额": 8018,
            }
        )
        assert row is not None
        self.assertAlmostEqual(row["last_price"], 25086.34, places=2)
        self.assertAlmostEqual(row["change_pct"], 0.32, places=1)
        self.assertAlmostEqual(row["change_amt"], 80.18, places=1)


class IntradayLiveTest(unittest.TestCase):
    def test_live_during_session(self) -> None:
        now = datetime(2026, 5, 29, 10, 15, tzinfo=_CN)
        self.assertTrue(
            intraday_quote_is_live("2026-05-29 10:14:00", now=now),
        )

    def test_not_live_wrong_day(self) -> None:
        now = datetime(2026, 5, 29, 10, 15, tzinfo=_CN)
        self.assertFalse(
            intraday_quote_is_live("2026-05-28 10:14:00", now=now),
        )

    def test_live_after_close_same_day(self) -> None:
        now = datetime(2026, 5, 29, 15, 30, tzinfo=_CN)
        self.assertTrue(
            intraday_quote_is_live("2026-05-29 15:00:00", now=now),
        )

    def test_hk_live_during_session(self) -> None:
        now = datetime(2026, 5, 29, 14, 0, tzinfo=_CN)
        self.assertTrue(
            intraday_quote_is_live(
                "2026-05-29 14:00:00",
                region=_REGION_HK,
                now=now,
            ),
        )


if __name__ == "__main__":
    unittest.main()
