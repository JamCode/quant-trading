#!/usr/bin/env python3
"""One-off backfill: CNINFO 国证行业 PE from 2023-01-01."""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fund_platform.industry_pe import backfill_industry_pe_cninfo  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill industry_pe_daily (CNINFO 国证)")
    parser.add_argument("--start", default="2023-01-01", help="YYYY-MM-DD")
    parser.add_argument("--end", default="", help="YYYY-MM-DD (default: today)")
    parser.add_argument("--delay", type=float, default=None, help="seconds between requests")
    args = parser.parse_args()
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end) if args.end else datetime.now().date()
    result = backfill_industry_pe_cninfo(
        start_date=start,
        end_date=end,
        delay_sec=args.delay,
    )
    print(result)


if __name__ == "__main__":
    main()
