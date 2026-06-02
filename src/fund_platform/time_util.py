"""Wall-clock helpers for China market ops (Asia/Shanghai)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

_CN_TZ = ZoneInfo("Asia/Shanghai")
_UTC = timezone.utc


def cn_now_iso() -> str:
    """Naive local timestamp string for DB columns (interpreted as Beijing wall time)."""
    return datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")


def format_db_time_cn(value: Any) -> Any:
    """Convert DB naive UTC datetime (or string) to Beijing display string."""
    if value is None or value == "":
        return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    dt: Optional[datetime]
    if isinstance(value, datetime):
        dt = value
    else:
        s = str(value).strip().replace("T", " ")[:19]
        try:
            dt = datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return value
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=_UTC)
    else:
        dt = dt.astimezone(_UTC)
    return dt.astimezone(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
