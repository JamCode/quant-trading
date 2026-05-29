"""Tests for per-stock industry sync."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fund_platform import stock_industry_sync


@patch("fund_platform.stock_industry_sync.fetch_stock_industry_em", return_value="银行")
@patch("fund_platform.stock_industry_sync.load_known_industry_names", return_value={"银行"})
@patch("fund_platform.stock_industry_sync.industry_lookup_delay_sec", return_value=0)
@patch("fund_platform.stock_industry_sync.get_engine")
def test_sync_stock_industries_daily_updates_row(mock_engine, _d, _k, _f):
    raw = MagicMock()
    cur = MagicMock()
    mock_engine.return_value.raw_connection.return_value = raw
    raw.cursor.return_value = cur
    cur.fetchall.return_value = [("600000",)]
    cur.rowcount = 1
    cur.fetchone.return_value = (1, 1)

    out = stock_industry_sync.sync_stock_industries_daily(
        max_codes=1,
        only_missing=True,
    )

    assert out["ok"] is True
    assert out["mapped"] == 1
    update_sql = cur.execute.call_args_list[1][0][0]
    assert "UPDATE stock_daily" in update_sql
