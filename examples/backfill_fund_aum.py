#!/usr/bin/env python3
"""Backfill funds.aum_yi from cached fund_details JSON."""

from __future__ import annotations

from fund_platform.db import get_engine
from fund_platform.fund_aum import backfill_aum_from_fund_details


def main() -> None:
    raw = get_engine().raw_connection()
    try:
        stats = backfill_aum_from_fund_details(raw)
        raw.commit()
        print(stats)
    finally:
        raw.close()


if __name__ == "__main__":
    main()
