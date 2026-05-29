"""Tests for intraday live quote helpers."""

from __future__ import annotations

import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from fund_platform.market_index_queries import intraday_quote_is_live

_CN = ZoneInfo("Asia/Shanghai")


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


if __name__ == "__main__":
    unittest.main()
