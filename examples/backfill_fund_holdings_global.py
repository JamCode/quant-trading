#!/usr/bin/env python3
"""Re-sync fund_holdings with global tickers (NVDA, HK codes, etc.)."""

from __future__ import annotations

import argparse

from fund_platform.fund_holdings_sync import sync_fund_holdings


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild fund_holdings for reverse lookup")
    parser.add_argument(
        "--scope",
        choices=("pipeline", "qdii", "all"),
        default="qdii",
        help="pipeline=股票/混合/指数/ETF/QDII; qdii=仅QDII; all=全市场基金",
    )
    parser.add_argument("--max-funds", type=int, default=0, help="0 = no cap")
    args = parser.parse_args()
    cap = None if args.max_funds <= 0 else args.max_funds
    result = sync_fund_holdings(max_funds=cap, scope=args.scope)
    print(result)


if __name__ == "__main__":
    main()
