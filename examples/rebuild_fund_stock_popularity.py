#!/usr/bin/env python3
"""Rebuild fund_stock_popularity from fund_holdings."""

from __future__ import annotations

from fund_platform.db import get_engine
from fund_platform.fund_stock_popularity import sync_fund_stock_popularity


def main() -> None:
    print(sync_fund_stock_popularity())


if __name__ == "__main__":
    main()
