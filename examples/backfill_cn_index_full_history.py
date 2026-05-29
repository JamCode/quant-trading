#!/usr/bin/env python3
"""One-shot: backfill A-share index daily history as far as external APIs allow.

Anti-scraping strategy
----------------------
1. **Sequential** — one index at a time (no parallel bursts).
2. **Two phases** — Sina OHLCV first (stable, 1 HTTP call per index), then East Money
   成交额 in a separate pass with longer gaps (EM is stricter on ECS).
3. **Jittered sleeps** — base interval + random 0..jitter seconds between indices.
4. **Retries** — exponential backoff per index; EM phase uses more attempts.
5. **Resume** — state JSON skips completed (code, phase) pairs.
6. **Chunked upsert** — existing ``_upsert_daily_batch`` / ``_patch_daily_amount_batch``.
7. **COALESCE amount** — Sina upsert does not wipe existing 成交额 rows.

Usage (ECS, after ``source deploy/ecs/fund-stack.env``)::

  cd /home/wanghan/quant-trading
  conda activate quant
  python examples/backfill_cn_index_full_history.py
  python examples/backfill_cn_index_full_history.py --dry-run
  python examples/backfill_cn_index_full_history.py --codes 000300,000001 --phase amount
  python examples/backfill_cn_index_full_history.py --gap-em 25 --gap-between-phases 180

Expect ~15–25 minutes for 7 indices (default gaps). Re-run with same state file to resume.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pymysql.cursors

from fund_platform.db import get_engine
from fund_platform.market_index import (
    _patch_daily_amount_batch,
    _upsert_daily_batch,
    cn_watchlist,
    fetch_cn_index_daily_amount_history,
    fetch_cn_index_daily_history_sina,
)

logger = logging.getLogger(__name__)

DEFAULT_STATE = Path(__file__).resolve().parent / ".cn_index_full_backfill_state.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _sleep_jitter(base_sec: float, jitter_sec: float) -> None:
    if base_sec <= 0 and jitter_sec <= 0:
        return
    delay = base_sec + (random.uniform(0, jitter_sec) if jitter_sec > 0 else 0)
    time.sleep(delay)


def _row_span(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"count": 0}
    dates = [str(r["trade_date"]) for r in rows if r.get("trade_date")]
    with_amt = sum(1 for r in rows if r.get("amount") is not None and float(r["amount"]) > 0)
    return {
        "count": len(rows),
        "first_date": min(dates) if dates else None,
        "last_date": max(dates) if dates else None,
        "with_amount": with_amt,
    }


def _load_state(path: Path) -> dict[str, Any]:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"started_at": _utc_now(), "indices": {}, "errors": []}


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utc_now()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _is_done(state: dict[str, Any], code: str, phase: str) -> bool:
    rec = state.get("indices", {}).get(code, {})
    return bool(rec.get(phase, {}).get("ok"))


def _mark_done(state: dict[str, Any], code: str, phase: str, result: dict[str, Any]) -> None:
    state.setdefault("indices", {}).setdefault(code, {})[phase] = {
        "ok": True,
        "at": _utc_now(),
        **result,
    }


def _mark_fail(state: dict[str, Any], code: str, phase: str, err: str) -> None:
    state.setdefault("errors", []).append(
        {"code": code, "phase": phase, "error": err, "at": _utc_now()}
    )
    state.setdefault("indices", {}).setdefault(code, {})[phase] = {
        "ok": False,
        "error": err,
        "at": _utc_now(),
    }


def _fetch_em_with_retry(
    code: str,
    name: str,
    *,
    max_attempts: int,
    backoff_base: float,
    chunked: bool,
) -> list[dict[str, Any]]:
    last_err: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            rows = fetch_cn_index_daily_amount_history(
                code, name, em_chunked=chunked
            )
            if rows:
                return rows
            last_err = RuntimeError("empty amount response")
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            logger.warning(
                "EM %s attempt %s/%s: %s",
                code,
                attempt + 1,
                max_attempts,
                exc,
            )
        if attempt < max_attempts - 1:
            wait = backoff_base * (2**attempt) + random.uniform(0, 3)
            time.sleep(min(wait, 120))
    if last_err:
        raise last_err
    return []


def _clear_amount_state(state: dict[str, Any]) -> None:
    for rec in state.get("indices", {}).values():
        rec.pop("amount", None)


def _db_cn_summary() -> list[dict[str, Any]]:
    cur = get_engine().raw_connection().cursor(pymysql.cursors.DictCursor)
    try:
        cur.execute(
            """
            SELECT code,
                   MIN(trade_date) AS first_date,
                   MAX(trade_date) AS last_date,
                   COUNT(*) AS days,
                   SUM(CASE WHEN amount IS NOT NULL AND amount > 0 THEN 1 ELSE 0 END) AS days_with_amount
            FROM market_index_daily
            WHERE code REGEXP '^[0-9]{6}$'
            GROUP BY code
            ORDER BY code
            """
        )
        return list(cur.fetchall())
    finally:
        cur.close()


def run_backfill(
    *,
    codes: Optional[list[str]],
    phase: str,
    dry_run: bool,
    state_path: Path,
    resume: bool,
    gap_sina: float,
    gap_em: float,
    jitter: float,
    gap_between_phases: float,
    em_attempts: int,
    em_backoff: float,
    em_chunked: bool,
    reset_amount: bool,
) -> dict[str, Any]:
    want = {c.strip().zfill(6) for c in codes} if codes else None
    indices = [
        (c.zfill(6), n) for c, n in cn_watchlist() if not want or c.zfill(6) in want
    ]
    if not indices:
        return {"ok": False, "error": "no indices selected"}

    state = _load_state(state_path) if resume else {"started_at": _utc_now(), "indices": {}, "errors": []}
    if reset_amount:
        _clear_amount_state(state)
    phases = ["sina", "amount"] if phase == "all" else [phase]

    report: dict[str, Any] = {
        "ok": True,
        "dry_run": dry_run,
        "phases": phases,
        "indices": [c for c, _ in indices],
        "before": _db_cn_summary(),
        "results": {},
    }

    for phase_name in phases:
        if phase_name == "amount" and gap_between_phases > 0:
            logger.info("Cooldown %.0fs before EM phase…", gap_between_phases)
            _sleep_jitter(gap_between_phases, jitter / 2)

        gap = gap_sina if phase_name == "sina" else gap_em
        for i, (code, name) in enumerate(indices):
            if resume and _is_done(state, code, phase_name):
                logger.info("skip %s %s (already done)", code, phase_name)
                continue

            logger.info("[%s] %s %s (%s/%s)…", phase_name, code, name, i + 1, len(indices))
            try:
                if phase_name == "sina":
                    rows = fetch_cn_index_daily_history_sina(code, name)
                    span = _row_span(rows)
                    written = 0
                    if not dry_run and rows:
                        written = _upsert_daily_batch(rows)
                    result = {**span, "written": written, "source": "sina"}
                else:
                    rows = _fetch_em_with_retry(
                        code,
                        name,
                        max_attempts=em_attempts,
                        backoff_base=em_backoff,
                        chunked=em_chunked,
                    )
                    if not rows:
                        raise RuntimeError("no amount rows (EM + Tencent)")
                    span = _row_span(rows)
                    written = 0
                    if not dry_run and rows:
                        written = _patch_daily_amount_batch(rows, only_missing=True)
                    result = {**span, "rows_updated": written, "source": "em+tx"}

                report["results"].setdefault(code, {})[phase_name] = result
                if not dry_run:
                    _mark_done(state, code, phase_name, result)
                    _save_state(state_path, state)
                logger.info("ok %s %s: %s", code, phase_name, result)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc)
                report["ok"] = False
                report["results"].setdefault(code, {})[phase_name] = {"ok": False, "error": msg}
                if not dry_run:
                    _mark_fail(state, code, phase_name, msg)
                    _save_state(state_path, state)
                logger.exception("%s %s failed", code, phase_name)

            if i < len(indices) - 1:
                _sleep_jitter(gap, jitter)

    if not dry_run:
        _save_state(state_path, state)

    report["after"] = _db_cn_summary() if not dry_run else report.get("before")
    report["state_file"] = str(state_path)
    report["errors"] = state.get("errors", [])
    return report


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--codes",
        default="",
        help="Comma-separated index codes; default = all CN watchlist",
    )
    parser.add_argument(
        "--phase",
        choices=("all", "sina", "amount"),
        default="all",
        help="sina=OHLCV only; amount=成交额 only; all=both (recommended)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Fetch only, no DB writes")
    parser.add_argument(
        "--state-file",
        type=Path,
        default=DEFAULT_STATE,
        help="Resume checkpoint JSON",
    )
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoint")
    parser.add_argument(
        "--gap-sina",
        type=float,
        default=8.0,
        help="Seconds between Sina fetches (default 8)",
    )
    parser.add_argument(
        "--gap-em",
        type=float,
        default=20.0,
        help="Seconds between East Money fetches (default 20)",
    )
    parser.add_argument(
        "--jitter",
        type=float,
        default=4.0,
        help="Extra random 0..N seconds on each gap (default 4)",
    )
    parser.add_argument(
        "--gap-between-phases",
        type=float,
        default=90.0,
        help="Cooldown between Sina and EM phases (default 90)",
    )
    parser.add_argument("--em-attempts", type=int, default=6, help="EM retries per index")
    parser.add_argument(
        "--em-backoff",
        type=float,
        default=8.0,
        help="EM retry backoff base seconds",
    )
    parser.add_argument(
        "--em-chunked",
        action="store_true",
        default=True,
        help="Fetch EM K-line year-by-year (default on, better on ECS)",
    )
    parser.add_argument(
        "--no-em-chunked",
        action="store_false",
        dest="em_chunked",
        help="Single full EM request per index",
    )
    parser.add_argument(
        "--reset-amount",
        action="store_true",
        help="Ignore prior amount phase checkpoint and retry all",
    )
    args = parser.parse_args()
    codes = [c.strip() for c in args.codes.split(",") if c.strip()] or None

    out = run_backfill(
        codes=codes,
        phase=args.phase,
        dry_run=args.dry_run,
        state_path=args.state_file,
        resume=not args.no_resume,
        gap_sina=args.gap_sina,
        gap_em=args.gap_em,
        jitter=args.jitter,
        gap_between_phases=args.gap_between_phases,
        em_attempts=args.em_attempts,
        em_backoff=args.em_backoff,
        em_chunked=args.em_chunked,
        reset_amount=args.reset_amount,
    )
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
