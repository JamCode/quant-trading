"""Money / market-cap unit helpers (DB & UI use 亿元)."""

from __future__ import annotations

from typing import Any, Optional


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    return v


def amount_to_yi(value: Any) -> Optional[float]:
    """元 → 亿 when magnitude looks like raw yuan; values already in 亿 are kept."""
    v = _as_float(value)
    if v is None:
        return None
    av = abs(v)
    if av >= 1_000_000:
        return round(v / 1e8, 2)
    # Legacy rows wrongly divided by 1e4 once (yuan → 1e5–1e6 band instead of 亿).
    if av >= 100_000:
        return round(v / 1e4, 2)
    return round(v, 2)


def cap_wan_to_yi(value: Any) -> Optional[float]:
    """万元 → 亿 (Sina spot nmc/mktcap)."""
    v = _as_float(value)
    if v is None or v <= 0:
        return None
    return round(v / 10000, 2)
