#!/usr/bin/env python3
"""Backfill A-share index 成交额 into market_index_daily (East Money + Tencent fallback)."""

from __future__ import annotations

import json
import sys

from fund_platform.market_index import backfill_cn_index_daily_amount


def main() -> int:
    days: int | None = None
    only_codes: list[str] | None = None
    args = [a for a in sys.argv[1:] if a]
    if args and args[0].isdigit():
        days = int(args[0])
        args = args[1:]
    if args:
        only_codes = [c.strip() for c in args[0].split(",") if c.strip()]
    out = backfill_cn_index_daily_amount(days=days, only_codes=only_codes)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
