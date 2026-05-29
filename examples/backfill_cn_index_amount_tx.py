#!/usr/bin/env python3
"""Backfill A-share index 成交额 via Tencent (when East Money is blocked on ECS)."""

from __future__ import annotations

import json
import sys
import time

from fund_platform.db import get_engine
from fund_platform.market_index import (
    _patch_daily_amount_batch,
    cn_watchlist,
    fetch_cn_index_daily_amount_history,
)


def main() -> int:
    only: list[str] | None = None
    args = [a for a in sys.argv[1:] if a.strip()]
    if args:
        only = [c.strip().zfill(6) for c in args[0].split(",") if c.strip()]
    indices = [
        (c, n) for c, n in cn_watchlist() if not only or c.zfill(6) in set(only)
    ]
    report: dict = {"ok": True, "indices": {}}
    for code, name in indices:
        t0 = time.time()
        try:
            rows = fetch_cn_index_daily_amount_history(code, name)
            n = _patch_daily_amount_batch(rows, only_missing=True) if rows else 0
            report["indices"][code] = {
                "rows": len(rows),
                "patched": n,
                "sec": round(time.time() - t0, 1),
                "name": name,
            }
        except Exception as exc:  # noqa: BLE001
            report["ok"] = False
            report["indices"][code] = {"error": str(exc)}
        time.sleep(3)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
