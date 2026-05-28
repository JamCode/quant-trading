#!/usr/bin/env python3
"""Backfill A-share index 成交额 (East Money) into market_index_daily."""

from __future__ import annotations

import json
import sys

from fund_platform.market_index import backfill_cn_index_daily_amount


def main() -> int:
    days = int(sys.argv[1]) if len(sys.argv) > 1 else None
    out = backfill_cn_index_daily_amount(days=days)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
