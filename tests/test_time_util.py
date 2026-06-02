from datetime import datetime, timezone

from fund_platform.time_util import format_db_time_cn


def test_format_db_time_cn_converts_utc_naive_to_beijing():
    # 2026-06-01 09:14:01 UTC -> 17:14:01 Beijing
    assert format_db_time_cn(datetime(2026, 6, 1, 9, 14, 1)) == "2026-06-01 17:14:01"
    assert format_db_time_cn("2026-06-01T09:14:01") == "2026-06-01 17:14:01"


def test_format_db_time_cn_passes_through_aware_utc():
    dt = datetime(2026, 6, 1, 9, 14, 1, tzinfo=timezone.utc)
    assert format_db_time_cn(dt) == "2026-06-01 17:14:01"
