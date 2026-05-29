"""Lazy-fetch THS industry constituents (same taxonomy as sector fund flow)."""

from __future__ import annotations

import logging
import re
import time
from io import StringIO
from typing import Any, Optional

import pandas as pd
import py_mini_racer
import requests
from akshare.datasets import get_ths_js

from fund_platform import settings as fp_settings

logger = logging.getLogger(__name__)

_CACHE_TTL_SEC = 3600
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _ths_headers() -> dict[str, str]:
    js_code = py_mini_racer.MiniRacer()
    js_code.eval(open(get_ths_js("ths.js"), encoding="utf-8").read())
    v_code = js_code.call("v")
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Cookie": f"v={v_code}",
        "hexin-v": v_code,
    }


_industry_map_cache: Optional[dict[str, str]] = None

# Fund-flow labels may append II/Ⅱ; THS thshy board list uses the base name.
_INDUSTRY_SUFFIXES = ("II", "Ⅱ", "2")


def normalize_industry_name(name: str) -> str:
    s = (name or "").strip()
    for suffix in _INDUSTRY_SUFFIXES:
        if s.endswith(suffix) and len(s) > len(suffix):
            return s[: -len(suffix)]
    return s


def resolve_ths_industry_name(name: str) -> tuple[str, Optional[str]]:
    """Map fund-flow industry label to THS thshy board name when possible."""
    raw = (name or "").strip()
    if not raw:
        return raw, None
    code_map = _industry_code_map()
    if raw in code_map:
        return raw, None
    normalized = normalize_industry_name(raw)
    if normalized != raw and normalized in code_map:
        return normalized, f"{raw} → {normalized}"
    return raw, None


def _fetch_industry_code_map_ths_web() -> dict[str, str]:
    html = _get_ths_html("http://q.10jqka.com.cn/thshy/")
    pairs = re.findall(
        r'href="http://q\.10jqka\.com\.cn/thshy/detail/code/(\d+)/"[^>]*>([^<]+)</a>',
        html,
    )
    out: dict[str, str] = {}
    for board_code, name in pairs:
        name = name.strip()
        if name and name not in out:
            out[name] = board_code
    if not out:
        raise RuntimeError("THS industry list parse returned empty")
    logger.info("THS industry map from web: %s entries", len(out))
    return out


def _industry_code_map() -> dict[str, str]:
    global _industry_map_cache
    if _industry_map_cache:
        return _industry_map_cache
    try:
        from akshare.stock_feature.stock_board_industry_ths import (
            _get_stock_board_industry_name_ths,
        )

        m = dict(_get_stock_board_industry_name_ths())
        if m:
            _industry_map_cache = m
            return m
    except Exception as exc:  # noqa: BLE001
        logger.warning("akshare THS industry list failed, using web scrape: %s", exc)
    _industry_map_cache = _fetch_industry_code_map_ths_web()
    return _industry_map_cache


def _parse_cap_yi(value: Any) -> Optional[float]:
    """Parse THS 流通市值 text to 亿元 (e.g. 27.64亿, 3521万)."""
    s = str(value or "").strip().replace(",", "")
    if not s or s in ("-", "--", "nan"):
        return None
    mult = 1.0
    if s.endswith("亿"):
        s = s[:-1].strip()
    elif s.endswith("万"):
        s = s[:-1].strip()
        mult = 1e-4
    elif s.endswith("元"):
        s = s[:-1].strip()
        mult = 1e-8
    try:
        return round(float(s) * mult, 4)
    except ValueError:
        return None


def _parse_page_count(html: str) -> int:
    m = re.search(r'class="page_info"[^>]*>(\d+)\s*/\s*(\d+)', html)
    if not m:
        return 1
    try:
        return max(1, int(m.group(2)))
    except ValueError:
        return 1


def _normalize_stock_row(rec: dict[str, Any]) -> dict[str, Any]:
    code = str(rec.get("代码", "")).strip()
    if code and code.isdigit():
        code = code.zfill(6)
    change = rec.get("涨跌幅(%)", rec.get("涨跌幅", ""))
    try:
        change_pct = float(change) if change not in ("", None) else None
    except (TypeError, ValueError):
        change_pct = None
    try:
        price = float(rec.get("现价", "")) if rec.get("现价") not in ("", None) else None
    except (TypeError, ValueError):
        price = None
    float_cap = _parse_cap_yi(rec.get("流通市值"))

    def _opt(val: Any) -> Optional[float]:
        if val is None:
            return None
        s = str(val).strip().replace(",", "")
        if not s or s in ("-", "--"):
            return None
        try:
            return float(s)
        except ValueError:
            return None

    return {
        "code": code,
        "name": str(rec.get("名称", "")).strip(),
        "price": price,
        "change_pct": change_pct,
        "turnover_pct": _opt(rec.get("换手率(%)", rec.get("换手率"))),
        "amount": _opt(rec.get("成交额")),
        "float_market_cap": float_cap,
        "pe_dynamic": _opt(rec.get("市盈率-动态", rec.get("市盈率"))),
        "pb": _opt(rec.get("市净率")),
        "volume_ratio": _opt(rec.get("量比")),
        "amplitude_pct": _opt(rec.get("振幅(%)", rec.get("振幅"))),
    }


def _ths_backoff_sec(attempt: int) -> float:
    return fp_settings.ths_retry_sleep_sec() * (attempt + 1)


def _get_ths_html(url: str, *, retries: Optional[int] = None) -> str:
    max_tries = retries if retries is not None else fp_settings.ths_retries()
    pace = fp_settings.ths_request_delay_sec()
    last_exc: Optional[Exception] = None
    for attempt in range(max_tries):
        try:
            r = requests.get(url, headers=_ths_headers(), timeout=25)
            if r.status_code in (401, 403, 429):
                logger.warning(
                    "THS HTTP %s %s (attempt %s/%s), backing off",
                    r.status_code,
                    url,
                    attempt + 1,
                    max_tries,
                )
                time.sleep(_ths_backoff_sec(attempt))
                continue
            r.raise_for_status()
            if pace > 0:
                time.sleep(pace)
            return r.text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("THS request error %s (attempt %s/%s): %s", url, attempt + 1, max_tries, exc)
            time.sleep(_ths_backoff_sec(attempt))
    if last_exc:
        raise last_exc
    raise RuntimeError(f"THS request failed: {url}")


def fetch_industry_constituent_codes(industry: str) -> list[str]:
    """Constituent codes for sync (THS; use stock_ths_industry holdings fallback if blocked)."""
    return fetch_industry_constituent_codes_ths(industry)


def fetch_industry_constituent_codes_ths(industry: str) -> list[str]:
    """Constituent stock codes only (for DB + stock_daily join)."""
    name = industry.strip()
    code_map = _industry_code_map()
    if name not in code_map:
        raise ValueError(f"未知行业：{name}")
    board_code = code_map[name]
    base = f"http://q.10jqka.com.cn/thshy/detail/code/{board_code}/"
    codes: list[str] = []
    seen: set[str] = set()

    html0 = _get_ths_html(base)
    pages = _parse_page_count(html0)
    page_htmls = [html0]
    page_delay = fp_settings.ths_page_delay_sec()
    for p in range(2, pages + 1):
        if page_delay > 0:
            time.sleep(page_delay)
        page_htmls.append(_get_ths_html(f"{base}page/{p}/"))

    for html in page_htmls:
        try:
            tables = pd.read_html(StringIO(html))
        except ValueError:
            continue
        if not tables:
            continue
        for rec in tables[0].to_dict("records"):
            raw = str(rec.get("代码", "")).strip()
            if not raw.isdigit():
                continue
            code = raw.zfill(6)
            if len(code) != 6:
                continue
            if code not in seen:
                seen.add(code)
                codes.append(code)
    return codes


def fetch_industry_constituents_ths(industry: str) -> dict[str, Any]:
    """Return constituent stocks for a THS industry name."""
    name = industry.strip()
    resolved, alias_note = resolve_ths_industry_name(name)
    code_map = _industry_code_map()
    if resolved not in code_map:
        raise ValueError(f"未知行业：{name}")

    now = time.time()
    cache_key = resolved
    cached = _cache.get(cache_key)
    if (
        cached
        and now - cached[0] < _CACHE_TTL_SEC
        and "float_market_cap_sum" in cached[1]
    ):
        payload = dict(cached[1])
        if alias_note:
            payload["alias_note"] = alias_note
            payload["industry_query"] = name
        return payload

    board_code = code_map[resolved]
    base = f"http://q.10jqka.com.cn/thshy/detail/code/{board_code}/"
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    html0 = _get_ths_html(base)
    pages = _parse_page_count(html0)
    page_htmls = [html0]
    page_delay = fp_settings.ths_page_delay_sec()
    for p in range(2, pages + 1):
        if page_delay > 0:
            time.sleep(page_delay)
        page_htmls.append(_get_ths_html(f"{base}page/{p}/"))

    for html in page_htmls:
        try:
            tables = pd.read_html(StringIO(html))
        except ValueError:
            continue
        if not tables:
            continue
        df = tables[0]
        for rec in df.to_dict("records"):
            row = _normalize_stock_row(rec)
            if not row["code"] or row["code"] in seen:
                continue
            seen.add(row["code"])
            items.append(row)

    caps = [x["float_market_cap"] for x in items if x.get("float_market_cap") is not None]
    cap_sum = round(sum(caps), 2) if caps else None
    missing = len(items) - len(caps)
    payload = {
        "industry": resolved,
        "board_code": board_code,
        "count": len(items),
        "items": items,
        "float_market_cap_sum": cap_sum,
        "float_market_cap_missing": missing,
        "source": "ths",
    }
    if alias_note:
        payload["alias_note"] = alias_note
        payload["industry_query"] = name
    _cache[cache_key] = (now, payload)
    logger.info("Fetched %s constituents for %s (resolved=%s)", len(items), name, resolved)
    return payload


def get_cached_constituents(industry: str) -> Optional[dict[str, Any]]:
    name = industry.strip()
    cached = _cache.get(name)
    if not cached:
        return None
    if time.time() - cached[0] >= _CACHE_TTL_SEC:
        return None
    return cached[1]
