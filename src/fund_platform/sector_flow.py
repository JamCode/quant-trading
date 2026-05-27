"""Daily A-share industry sector fund flow (East Money JSON API → MySQL)."""

from __future__ import annotations

import logging
import time
import traceback
from datetime import date, datetime, timezone
from typing import Any, Optional

import requests

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine
from fund_platform.units import amount_to_yi

logger = logging.getLogger(__name__)

# ── East Money API 行业板块参数 ──
# 正确 fs 值：m:90+s:4（行业板块），不是 m:90+t:2
_EM_BASE_URLS = (
    "https://29.push2.eastmoney.com/api/qt/clist/get",
    "https://82.push2.eastmoney.com/api/qt/clist/get",
    "https://63.push2.eastmoney.com/api/qt/clist/get",
    "https://48.push2.eastmoney.com/api/qt/clist/get",
    "https://push2.eastmoney.com/api/qt/clist/get",
)

_EM_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://data.eastmoney.com/bkzj/hy.html",
}


# 各周期对应的 API 参数（来自东财网页 JavaScript）
# st（排序字段）：1日→f62, 5日→f164, 3/10日→f174, 20日→f183
_EM_PERIOD_CONFIG = {
    "即时": {
        "fields": "f2,f3,f12,f14,f62,f66,f69,f72,f78,f84,f124,f184,f204,f205",
        "fid": "f62",
        "change_field": "f3",
        "net_field": "f62",
    },
    "3日排行": {
        "fields": "f2,f12,f14,f124,f127,f257,f258,f267,f268,f269,f270,f271,f272,f273,f274,f275,f276",
        "fid": "f174",
        "change_field": "f127",
        "net_field": "f267",
    },
    "5日排行": {
        "fields": "f2,f12,f14,f109,f124,f164,f165,f166,f167,f168,f169,f170,f171,f172,f173,f257,f258",
        "fid": "f164",
        "change_field": "f109",
        "net_field": "f164",
    },
    "10日排行": {
        "fields": "f2,f12,f14,f124,f160,f174,f175,f176,f177,f178,f179,f180,f181,f182,f183,f260,f261",
        "fid": "f174",
        "change_field": "f160",
        "net_field": "f174",
    },
    "20日排行": {
        "fields": "f2,f12,f14,f124,f160,f183,f184,f185,f186,f187,f188,f189,f190,f191,f192,f193,f262,f263",
        "fid": "f183",
        "change_field": "f160",
        "net_field": "f183",
    },
}

_PERIOD_COLUMN_MAP = {
    "即时": {
        "change": "行业-涨跌幅",
        "leader_chg": "领涨股-涨跌幅",
        "leader_price": "当前价",
    },
    "3日排行": {
        "change": "阶段涨跌幅",
        "leader_chg": None,
        "leader_price": None,
    },
    "5日排行": {
        "change": "阶段涨跌幅",
        "leader_chg": None,
        "leader_price": None,
    },
    "10日排行": {
        "change": "阶段涨跌幅",
        "leader_chg": None,
        "leader_price": None,
    },
    "20日排行": {
        "change": "阶段涨跌幅",
        "leader_chg": None,
        "leader_price": None,
    },
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _trade_date_today() -> date:
    return datetime.now().date()


def _parse_amount(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in ("-", "--", "nan"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _em_amount_to_yi(value: Any) -> Optional[float]:
    """East Money push2 fund-flow fields are yuan; DB/UI expect 亿元."""
    return amount_to_yi(_parse_amount(value))


def _parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _normalize_row(period: str, rec: dict[str, Any]) -> Optional[dict[str, Any]]:
    industry = str(rec.get("行业", "")).strip()
    if not industry:
        return None
    cols = _PERIOD_COLUMN_MAP.get(period, _PERIOD_COLUMN_MAP["即时"])
    change_val = rec.get(cols["change"], "")
    leader_chg = ""
    leader_price = ""
    if cols["leader_chg"]:
        leader_chg = str(rec.get(cols["leader_chg"], "") or "").strip()
    if cols["leader_price"]:
        leader_price = str(rec.get(cols["leader_price"], "") or "").strip()
    return {
        "industry": industry,
        "industry_index": str(rec.get("行业指数", "") or "").strip(),
        "change_pct": str(change_val or "").strip(),
        "inflow_amt": amount_to_yi(rec.get("流入资金")),
        "outflow_amt": amount_to_yi(rec.get("流出资金")),
        "net_amt": amount_to_yi(rec.get("净额")),
        "company_count": _parse_int(rec.get("公司家数")),
        "leader_stock": str(rec.get("领涨股", "") or "").strip(),
        "leader_change_pct": leader_chg,
        "leader_price": leader_price,
    }


def _em_json(period: str) -> list[dict[str, Any]]:
    """Fetch industry fund-flow JSON from East Money (multi-host retry)."""
    cfg = _EM_PERIOD_CONFIG.get(period)
    if not cfg:
        logger.warning("unsupported period %r, skipping", period)
        return []

    params = {
        "pn": "1",
        "pz": "500",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": cfg["fid"],
        "fs": "m:90+s:4",
        "fields": cfg["fields"],
    }

    last_exc: Optional[Exception] = None
    for attempt in range(8):
        for url in _EM_BASE_URLS:
            try:
                r = requests.get(url, params=params, headers=_EM_HEADERS, timeout=25)
                data = r.json()
                items = data.get("data", {}).get("diff")
                if items:
                    return items
            except Exception as exc:
                last_exc = exc
        time.sleep(2 * (attempt + 1))

    logger.error("EM API all retries exhausted for period=%s: %s", period, last_exc)
    if last_exc:
        raise last_exc
    return []


def _em_rec_to_dict(period: str, rec: dict[str, Any]) -> dict[str, Any]:
    """Map one East Money record to the legacy AkShare-shaped dict for _normalize_row."""
    cfg = _EM_PERIOD_CONFIG.get(period)
    if not cfg:
        return {}

    net_yi = _em_amount_to_yi(rec.get(cfg["net_field"]))
    change_val = rec.get(cfg["change_field"])
    if change_val is not None:
        change_val = str(round(change_val, 2))

    industry_index = rec.get("f2")
    if industry_index is not None:
        industry_index = str(round(industry_index, 2))

    leader = rec.get("f257", rec.get("f260", rec.get("f262", rec.get("f204", ""))))

    return {
        "行业": str(rec.get("f14", "")).strip(),
        "行业指数": industry_index or "",
        "行业-涨跌幅": str(round(rec.get("f3", 0), 2)) if period == "即时" else "",
        "阶段涨跌幅": change_val or "",
        "净额": net_yi,
        "流入资金": net_yi if net_yi is not None and net_yi > 0 else 0,
        "流出资金": abs(net_yi) if net_yi is not None and net_yi < 0 else 0,
        "领涨股": str(leader).strip(),
        "领涨股-涨跌幅": str(round(rec.get("f69", 0), 2)) if period == "即时" else "",
        "当前价": str(rec.get("f2", "")) if period == "即时" else "",
        "公司家数": None,
    }


def fetch_sector_flow_em(period: str) -> list[dict[str, Any]]:
    """Industry sector fund flow via East Money JSON API."""
    raw_items = _em_json(period)
    if not raw_items:
        return []

    rows: list[dict[str, Any]] = []
    for rec in raw_items:
        mapped = _em_rec_to_dict(period, rec)
        if not mapped.get("行业"):
            continue
        row = _normalize_row(period, mapped)
        if row:
            rows.append(row)
    return rows


def sync_sector_fund_flow_for_period(
    cur,
    trade_date: date,
    period: str,
) -> dict[str, Any]:
    job_id = None
    td = trade_date.isoformat()
    try:
        cur.execute(
            """
            INSERT INTO sector_flow_jobs (trade_date, period, started_at, ok)
            VALUES (%s, %s, %s, 0)
            """,
            (td, period, _utc_now_iso()),
        )
        job_id = cur.lastrowid

        raw_rows = fetch_sector_flow_em(period)
        by_industry: dict[str, dict[str, Any]] = {}
        for row in raw_rows:
            by_industry[row["industry"]] = row
        payload = list(by_industry.values())
        now = _utc_now_iso()
        cur.execute(
            "DELETE FROM sector_fund_flow WHERE trade_date = %s AND period = %s",
            (td, period),
        )
        if payload:
            params = [
                (
                    td,
                    period,
                    r["industry"],
                    r["industry_index"],
                    r["change_pct"],
                    r["inflow_amt"],
                    r["outflow_amt"],
                    r["net_amt"],
                    r["company_count"],
                    r["leader_stock"],
                    r["leader_change_pct"],
                    r["leader_price"],
                    now,
                )
                for r in payload
            ]
            cur.executemany(
                """
                INSERT INTO sector_fund_flow (
                  trade_date, period, industry, industry_index, change_pct,
                  inflow_amt, outflow_amt, net_amt, company_count,
                  leader_stock, leader_change_pct, leader_price, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                params,
            )

        cur.execute(
            """
            UPDATE sector_flow_jobs
            SET finished_at = %s, ok = 1, row_count = %s, error = NULL
            WHERE id = %s
            """,
            (_utc_now_iso(), len(payload), job_id),
        )
        return {"ok": True, "period": period, "count": len(payload), "job_id": job_id}
    except Exception as exc:  # noqa: BLE001
        err = f"{exc}\n{traceback.format_exc()}"
        logger.exception("sector flow failed period=%s", period)
        if job_id is not None:
            cur.execute(
                """
                UPDATE sector_flow_jobs
                SET finished_at = %s, ok = 0, row_count = NULL, error = %s
                WHERE id = %s
                """,
                (_utc_now_iso(), err[:4000], job_id),
            )
        return {"ok": False, "period": period, "error": str(exc), "job_id": job_id}


def sync_sector_fund_flow_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    """Pull all configured periods for ``trade_date`` (default: today)."""
    td = trade_date or _trade_date_today()
    periods = fp_settings.sector_flow_periods()
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    results: list[dict[str, Any]] = []
    try:
        period_delay = fp_settings.sector_flow_period_delay_sec()
        for i, period in enumerate(periods):
            if i > 0 and period_delay > 0:
                time.sleep(period_delay)
            logger.info("Sector fund flow sync %s %s", td, period)
            results.append(sync_sector_fund_flow_for_period(cur, td, period))
        raw.commit()
        ok = all(r.get("ok") for r in results)
        total = sum(int(r.get("count") or 0) for r in results)
        return {
            "ok": ok,
            "trade_date": td.isoformat(),
            "periods": results,
            "total_rows": total,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_sector_fund_flow_daily failed")
        try:
            raw.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(exc), "trade_date": td.isoformat(), "periods": results}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()
