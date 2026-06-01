"""Fetch each holding's own NAV snapshot via akshare (East Money fund site).

The portfolio is almost all passive index/QDII funds. Rather than guessing each
fund's tracked-index code (error-prone) or asking the model to web-search niche
index returns (it can't), we pull the fund's REAL net-asset-value series and feed
the latest daily change plus 1-week / 1-month returns to the model. This is exact,
keyed by the fund code we already have, and the fund.eastmoney endpoint works on
the ECS host (where the quote/push2 endpoints are blocked).

Failures degrade gracefully: a fund we can't fetch is simply omitted, and the
model is told it may web-search the rest.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

# QDII funds settle NAV with a longer lag; used only to annotate the brief.
_QDII_HINT = ("QDII", "纳斯达克", "标普", "恒生", "港股", "海外", "美国")


def _to_float(value: Any) -> Optional[float]:
    try:
        if value in (None, "", "-"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _cumulative_return(navs: list[float], lookback: int) -> Optional[float]:
    """Percentage change of the last NAV vs the one `lookback` rows earlier."""
    if len(navs) <= lookback:
        return None
    base = navs[-1 - lookback]
    last = navs[-1]
    if not base:
        return None
    return round((last / base - 1.0) * 100.0, 2)


def fetch_fund_navs(
    codes: list[str],
    *,
    request_delay_sec: float = 0.4,
) -> dict[str, dict[str, Any]]:
    """Return fund_code -> {nav_date, nav, day_pct, ret_1w, ret_1m}."""
    import akshare as ak

    out: dict[str, dict[str, Any]] = {}
    for code in codes:
        try:
            df = ak.fund_open_fund_info_em(symbol=code, indicator="单位净值走势")
        except Exception as exc:  # noqa: BLE001
            logger.warning("fund_open_fund_info_em(%s) failed: %s", code, exc)
            continue
        if df is None or df.empty:
            continue
        recs = df.to_dict("records")
        navs = [v for v in (_to_float(r.get("单位净值")) for r in recs) if v is not None]
        last = recs[-1]
        out[code] = {
            "nav_date": str(last.get("净值日期") or "")[:10],
            "nav": _to_float(last.get("单位净值")),
            "day_pct": _to_float(last.get("日增长率")),
            "ret_1w": _cumulative_return(navs, 5),
            "ret_1m": _cumulative_return(navs, 20),
        }
        if request_delay_sec > 0:
            time.sleep(request_delay_sec)
    return out


def _is_qdii(name: str) -> bool:
    return any(tok in name for tok in _QDII_HINT)


def format_fund_nav_block(
    holdings: list[dict[str, Any]],
    navs: dict[str, dict[str, Any]],
) -> str:
    """One line per fund with its latest NAV move and 1w/1m returns."""
    if not navs:
        return ""
    lines: list[str] = []
    for h in holdings:
        code = h["code"]
        q = navs.get(code)
        if not q:
            continue
        name = h.get("name") or code

        def _pct(key: str) -> str:
            v = q.get(key)
            return f"{v:+.2f}%" if isinstance(v, (int, float)) else "—"

        date = q.get("nav_date") or "—"
        parts = [f"- {name}（{code}）"]
        parts.append(f"截至{date}")
        parts.append(f"当日{_pct('day_pct')}")
        parts.append(f"近1周{_pct('ret_1w')}")
        parts.append(f"近1月{_pct('ret_1m')}")
        if _is_qdii(name):
            parts.append("(QDII，净值有汇率与约1日时滞)")
        lines.append("；".join(parts))
    return "\n".join(lines)
