"""Parse pasted AI replies for fund codes and link to catalog."""

from __future__ import annotations

import re
from typing import Any

from fund_platform import queries

_CODE_RE = re.compile(r"\b(\d{6})\b")


def extract_fund_codes(text: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for m in _CODE_RE.finditer(text):
        code = m.group(1)
        if code not in seen:
            seen.add(code)
            ordered.append(code)
    return ordered


def parse_items(conn, text: str, *, url_prefix: str = "") -> list[dict[str, Any]]:
    codes = extract_fund_codes(text)
    if not codes:
        return []
    by_code = queries.get_funds_by_codes(conn, codes)
    prefix = (url_prefix or "").strip().rstrip("/")
    items: list[dict[str, Any]] = []
    for code in codes:
        row = by_code.get(code)
        if row:
            name = (row.get("short_name") or row.get("name") or "").strip() or None
            path = f"/funds/{code}"
            detail_url = f"{prefix}{path}" if prefix else path
            items.append(
                {
                    "code": code,
                    "name": name,
                    "in_catalog": True,
                    "detail_url": detail_url,
                }
            )
        else:
            items.append(
                {
                    "code": code,
                    "name": None,
                    "in_catalog": False,
                    "detail_url": None,
                }
            )
    return items
