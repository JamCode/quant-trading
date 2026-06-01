#!/usr/bin/env python3
"""Daily portfolio brief: holdings JSON → DashScope (web search) → DingTalk.

Requires in project root .env (or ECS fund-stack.env):
  DASHSCOPE_API_KEY, DINGTALK_WEBHOOK_URL, DINGTALK_SECRET

Market/fund data comes only from model web search — no local MySQL injection.

Usage:
  PYTHONPATH=src python3 scripts/daily_fund_advisor.py
  PYTHONPATH=src python3 scripts/daily_fund_advisor.py --dry-run
  PYTHONPATH=src python3 scripts/daily_fund_advisor.py --no-push
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

    index_block = ""
    if os.environ.get("FUND_ADVISOR_FETCH_INDEX", "1").strip().lower() not in ("0", "false", "no"):
        try:
            from fund_platform import index_quotes

            codes = [h["code"] for h in holdings]
            quotes = index_quotes.fetch_index_quotes(codes)
            index_block = index_quotes.format_index_quotes_block(holdings, quotes)
            print(f"Fetched {len(quotes)} tracked-index quotes via akshare", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            print(f"Index quote fetch skipped: {exc}", file=sys.stderr)

    prompt = portfolio_advisor.build_analysis_prompt(holdings, index_quotes_block=index_block)
    if args.dry_run:
        print("=== PROMPT ===")
        print(prompt)
        return

    print("Calling DashScope (web search only, no DB)…", file=sys.stderr)
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
