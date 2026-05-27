#!/usr/bin/env python3
"""One-off: convert sector_fund_flow 元 columns to 亿元 in MySQL.

Run on ECS after deploy:
  cd ~/quant-trading && source ~/miniconda3/etc/profile.d/conda.sh && conda activate quant
  set -a && source deploy/ecs/fund-stack.env && set +a
  python examples/fix_sector_flow_amount_units.py
"""

from __future__ import annotations

import os

from sqlalchemy import text

from fund_platform.db import get_engine


def main() -> None:
    engine = get_engine()
    with engine.begin() as conn:
        for col in ("net_amt", "inflow_amt", "outflow_amt", "float_market_cap"):
            r = conn.execute(
                text(
                    f"""
                    UPDATE sector_fund_flow
                    SET {col} = ROUND({col} / 100000000, 2)
                    WHERE {col} IS NOT NULL AND ABS({col}) >= 1000000
                    """
                )
            )
            print(f"{col} yuan→亿 (>=1e6): updated {r.rowcount} rows")
            r2 = conn.execute(
                text(
                    f"""
                    UPDATE sector_fund_flow
                    SET {col} = ROUND({col} / 10000, 2)
                    WHERE {col} IS NOT NULL
                      AND ABS({col}) >= 100000 AND ABS({col}) < 1000000
                    """
                )
            )
            print(f"{col} legacy ÷1e4 fix (1e5–1e6): updated {r2.rowcount} rows")


if __name__ == "__main__":
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("Set DATABASE_URL / fund-stack.env first")
    main()
