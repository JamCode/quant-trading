from datetime import date
from unittest.mock import MagicMock

from fund_platform.market_index_queries import query_market_index_bars


def test_query_market_index_bars_maps_rows():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value = cur
    cur.fetchall.return_value = [
        {
            "trade_date": date(2024, 1, 2),
            "open_px": 1.0,
            "high_px": 2.0,
            "low_px": 0.5,
            "close_px": 1.5,
            "volume": 100,
        }
    ]
    rows = query_market_index_bars(
        conn, "000300", start_date="2024-01-01", end_date="2024-12-31"
    )
    assert len(rows) == 1
    assert rows[0]["trade_date"] == "2024-01-02"
    assert rows[0]["close"] == 1.5
    sql = cur.execute.call_args[0][0]
    assert "trade_date >=" in sql
