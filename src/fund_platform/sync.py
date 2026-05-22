"""Full-catalog ingestion into MySQL (invoked by crawler service)."""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Any

from fund_platform.db import get_engine
from fund_platform.normalize import normalize_open_fund_daily
from fund_platform import settings as fp_settings

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


_SNAPSHOT_COLS = (
    "nav_date",
    "nav_unit",
    "nav_acc",
    "prev_nav_unit",
    "prev_nav_acc",
    "daily_change",
    "daily_pct",
    "subscribe_status",
    "redeem_status",
    "fee_note",
)


def sync_catalog_mysql() -> dict[str, Any]:
    """Pull AkShare EM catalog + optional daily snapshot and refresh ``funds`` table."""
    import akshare as ak

    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    job_id = None
    try:
        cur.execute(
            "INSERT INTO sync_jobs (started_at, ok, row_count) VALUES (%s, 0, NULL)",
            (_utc_now_iso(),),
        )
        job_id = cur.lastrowid
        raw.commit()

        df = ak.fund_name_em()
        if df is None or df.empty:
            raise RuntimeError("fund_name_em returned no rows")

        rename = {
            "基金代码": "code",
            "拼音缩写": "pinyin_abbr",
            "基金简称": "short_name",
            "基金类型": "fund_type",
            "拼音全称": "pinyin_full",
        }
        catalog = df.rename(columns=rename)
        for col in ("code", "short_name"):
            if col not in catalog.columns:
                raise RuntimeError(f"missing column {col}: got {list(catalog.columns)}")

        catalog["code"] = catalog["code"].astype(str).str.strip()
        catalog["short_name"] = catalog["short_name"].astype(str).str.strip()
        catalog["pinyin_abbr"] = catalog.get("pinyin_abbr", "").astype(str)
        catalog["fund_type"] = catalog.get("fund_type", "").astype(str)
        catalog["pinyin_full"] = catalog.get("pinyin_full", "").astype(str)
        catalog = catalog[catalog["code"] != ""]

        merged = catalog.copy()
        if fp_settings.sync_include_daily_snapshot():
            try:
                raw_daily = ak.fund_open_fund_daily_em()
                if raw_daily is not None and not raw_daily.empty:
                    daily_part = normalize_open_fund_daily(raw_daily)
                    merged = catalog.merge(daily_part, on="code", how="left")
                    logger.info("Merged daily snapshot rows=%s", len(daily_part))
                else:
                    logger.warning("fund_open_fund_daily_em returned empty")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping daily snapshot merge: %s", exc)

        for c in _SNAPSHOT_COLS:
            if c not in merged.columns:
                merged[c] = ""
        merged = merged.fillna("")
        for c in _SNAPSHOT_COLS:
            merged[c] = merged[c].astype(str).str.strip()

        now = _utc_now_iso()
        select_cols = [
            "code",
            "pinyin_abbr",
            "short_name",
            "fund_type",
            "pinyin_full",
            *_SNAPSHOT_COLS,
        ]
        merged_rows = merged[select_cols].itertuples(index=False, name=None)
        rows = [tuple(map(str, tup)) + (now,) for tup in merged_rows]

        cur.execute("DELETE FROM funds")
        cur.executemany(
            """
                INSERT INTO funds (
                  code, pinyin_abbr, short_name, fund_type, pinyin_full,
                  nav_date, nav_unit, nav_acc, prev_nav_unit, prev_nav_acc,
                  daily_change, daily_pct, subscribe_status, redeem_status, fee_note,
                  updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            rows,
        )
        cur.execute(
            """
            UPDATE sync_jobs
            SET finished_at = %s, ok = 1, row_count = %s, error = NULL
            WHERE id = %s
            """,
            (_utc_now_iso(), len(rows), job_id),
        )
        raw.commit()
        return {"ok": True, "count": len(rows), "job_id": job_id}
    except Exception as exc:  # noqa: BLE001
        err = f"{exc}\n{traceback.format_exc()}"
        logger.exception("sync_catalog_mysql failed")
        try:
            raw.rollback()
        except Exception:
            pass
        if job_id is not None:
            try:
                cur.execute(
                    """
                    UPDATE sync_jobs
                    SET finished_at = %s, ok = 0, row_count = NULL, error = %s
                    WHERE id = %s
                    """,
                    (_utc_now_iso(), err[:4000], job_id),
                )
                raw.commit()
            except Exception:
                pass
        return {"ok": False, "error": str(exc), "job_id": job_id}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()
