#!/usr/bin/env python3
"""Daily portfolio brief: holdings JSON → DashScope (qwen-max) → DingTalk.

Requires in project root .env:
  DASHSCOPE_API_KEY, DINGTALK_WEBHOOK_URL, DINGTALK_SECRET
Optional:
  DATABASE_URL          enrich NAV/metrics from MySQL
  QWEN_MODEL            default qwen-max
  FUND_ADVISOR_ENABLE_SEARCH=1
  PORTFOLIO_CONFIG      default config/portfolio_holdings.json

Usage:
  PYTHONPATH=src python3 scripts/daily_fund_advisor.py
  PYTHONPATH=src python3 scripts/daily_fund_advisor.py --dry-run   # print only, no API
  PYTHONPATH=src python3 scripts/daily_fund_advisor.py --no-push   # call model, stdout
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fund_platform.dotenv_util import load_dotenv  # noqa: E402
from fund_platform import dingtalk_notify  # noqa: E402
from fund_platform import portfolio_advisor  # noqa: E402


def main() -> None:
    load_dotenv(ROOT / "deploy/ecs/fund-stack.env")
    load_dotenv(ROOT / ".env")

    parser = argparse.ArgumentParser(description="Daily fund portfolio brief → DingTalk")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="Print prompt only")
    parser.add_argument("--no-push", action="store_true", help="Run model but do not DingTalk")
    args = parser.parse_args()
    config_path = args.config or Path(
        os.environ.get("PORTFOLIO_CONFIG", str(ROOT / "config" / "portfolio_holdings.json"))
    )

    holdings = portfolio_advisor.load_holdings_config(config_path)
    if not holdings:
        raise SystemExit(f"No holdings in {config_path}")

    snapshots: dict = {}
    market_block = ""
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if db_url:
        try:
            from fund_platform.db import get_engine

            codes = [h["code"] for h in holdings]
            with get_engine().connect() as conn:
                raw = conn.connection
                snapshots = portfolio_advisor.fetch_snapshots(raw, codes)
                market_block = portfolio_advisor.fetch_market_context_block(raw)
            print(f"Enriched {len(snapshots)}/{len(holdings)} funds from MySQL", file=sys.stderr)
            if market_block:
                print("Loaded market index snapshot block", file=sys.stderr)
        except Exception as exc:
            print(f"MySQL enrich skipped: {exc}", file=sys.stderr)
    else:
        print("DATABASE_URL not set — using holdings names only", file=sys.stderr)

    prompt = portfolio_advisor.build_analysis_prompt(
        holdings, snapshots, market_block=market_block
    )
    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        return

    print("Calling DashScope…", file=sys.stderr)
    analysis, usage = portfolio_advisor.call_qwen_analysis(prompt)
    print("usage:", usage, file=sys.stderr)
    message = portfolio_advisor.format_dingtalk_message(analysis)
    print(message)

    if args.no_push:
        return

    webhook = os.environ.get("DINGTALK_WEBHOOK_URL", "").strip()
    secret = os.environ.get("DINGTALK_SECRET", "").strip()
    if not webhook or not secret:
        raise SystemExit("Missing DINGTALK_WEBHOOK_URL or DINGTALK_SECRET")

    results = dingtalk_notify.send_text_chunks(
        webhook=webhook, secret=secret, content=message
    )
    for i, res in enumerate(results, 1):
        if res.get("errcode") != 0:
            raise SystemExit(f"DingTalk part {i} failed: {res}")
    print(f"Pushed {len(results)} message(s) to DingTalk.", file=sys.stderr)


if __name__ == "__main__":
    main()
