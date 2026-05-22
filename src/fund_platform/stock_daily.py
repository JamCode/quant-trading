"""Daily A-share snapshot (East Money spot) for constituent lookups."""

from __future__ import annotations

import logging
import time
import traceback
from datetime import date, datetime, timezone
from typing import Any, Optional

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine

logger = logging.getLogger(__name__)

_MIN_ROWS_OK = 3000


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _trade_date_today() -> date:
    return datetime.now().date()


def _cap_to_yi(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v:  # NaN
        return None
    if v <= 0:
        return None
    if v >= 1e6:
        return round(v / 1e8, 2)
    return round(v, 2)


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in ("-", "--", "nan", "NaN", "—"):
        return None
    try:
        v = float(s)
        if v != v:  # NaN
            return None
        return v
    except ValueError:
        return None


def _amount_to_yi(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v != v or v <= 0:
        return None
    if v >= 1e6:
        return round(v / 1e8, 2)
    return round(v, 2)


def _fetch_spot_em_dataframe() -> "pd.DataFrame":
    """East Money A-share spot with slower pagination (ECS-friendly)."""
    import math

    import pandas as pd
    import requests

    urls = (
        "https://82.push2.eastmoney.com/api/qt/clist/get",
        "https://63.push2.eastmoney.com/api/qt/clist/get",
        "https://push2.eastmoney.com/api/qt/clist/get",
    )
    params = {
        "pn": "1",
        "pz": "50",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "fid": "f12",
        "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,"
        "f20,f21,f23,f24,f25,f22,f11,f62,f128,f136,f115,f152",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://quote.eastmoney.com/center/gridlist.html",
    }

    def _page_json(pn: int) -> dict:
        p = {**params, "pn": str(pn)}
        last: Optional[Exception] = None
        for attempt in range(6):
            for url in urls:
                try:
                    r = requests.get(url, params=p, headers=headers, timeout=30)
                    r.raise_for_status()
                    return r.json()
                except Exception as exc:  # noqa: BLE001
                    last = exc
            time.sleep(fp_settings.stock_daily_retry_sleep_sec() * (attempt + 1))
        if last:
            raise last
        return {}

    page_delay = fp_settings.stock_daily_page_delay_sec()
    data1 = _page_json(1)
    first = pd.DataFrame(data1.get("data", {}).get("diff") or [])
    if first.empty:
        return first
    per_page = max(1, len(first))
    total_n = int(data1.get("data", {}).get("total") or 0)
    total_pages = max(1, math.ceil(total_n / per_page))
    frames = [first]
    try:
        for pn in range(2, total_pages + 1):
            if page_delay > 0:
                time.sleep(page_delay)
            frames.append(pd.DataFrame(_page_json(pn).get("data", {}).get("diff") or []))
    except Exception as exc:  # noqa: BLE001
        partial = sum(len(f) for f in frames)
        if partial < _MIN_ROWS_OK:
            raise exc
        logger.warning("em spot partial pages ok rows=%s: %s", partial, exc)
    df = pd.concat(frames, ignore_index=True)
    em_names = [
        "index",
        "_",
        "最新价",
        "涨跌幅",
        "涨跌额",
        "成交量",
        "成交额",
        "振幅",
        "换手率",
        "市盈率-动态",
        "量比",
        "5分钟涨跌",
        "代码",
        "_",
        "名称",
        "最高",
        "最低",
        "今开",
        "昨收",
        "总市值",
        "流通市值",
        "涨速",
        "市净率",
        "60日涨跌幅",
        "年初至今涨跌幅",
        "-",
        "-",
        "-",
        "-",
        "-",
        "-",
        "-",
    ]
    ncol = len(df.columns)
    if ncol != len(em_names):
        logger.warning("em spot columns %s (expected %s), padding names", ncol, len(em_names))
        if ncol > len(em_names):
            em_names = em_names + [f"_x{i}" for i in range(ncol - len(em_names))]
        else:
            em_names = em_names[:ncol]
    df.columns = em_names
    wanted = [
        "代码",
        "名称",
        "最新价",
        "涨跌幅",
        "换手率",
        "成交额",
        "振幅",
        "市盈率-动态",
        "量比",
        "5分钟涨跌",
        "总市值",
        "流通市值",
        "涨速",
        "市净率",
        "60日涨跌幅",
        "年初至今涨跌幅",
    ]
    present = [c for c in wanted if c in df.columns]
    if "代码" not in present:
        raise ValueError(f"em spot missing 代码 column; got {list(df.columns)}")
    return df[present]


def fetch_a_share_spot_em(*, max_attempts: int = 3) -> list[dict[str, Any]]:
    df = None
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        try:
            df = _fetch_spot_em_dataframe()
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning("em spot fetch attempt %s failed: %s", attempt + 1, exc)
            time.sleep(fp_settings.stock_daily_retry_sleep_sec() * (attempt + 1))
    if df is None:
        if last_exc:
            raise last_exc
        return []
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        code = str(rec.get("代码", "")).strip()
        if not code.isdigit():
            continue
        code = code.zfill(6)
        rows.append(
            {
                "code": code,
                "name": str(rec.get("名称", "")).strip(),
                "price": _opt_float(rec.get("最新价")),
                "change_pct": _opt_float(rec.get("涨跌幅")),
                "float_market_cap": _cap_to_yi(rec.get("流通市值")),
                "total_market_cap": _cap_to_yi(rec.get("总市值")),
                "turnover_pct": _opt_float(rec.get("换手率")),
                "amount": _amount_to_yi(rec.get("成交额")),
                "pe_dynamic": _opt_float(rec.get("市盈率-动态")),
                "pb": _opt_float(rec.get("市净率")),
                "volume_ratio": _opt_float(rec.get("量比")),
                "amplitude_pct": _opt_float(rec.get("振幅")),
                "change_5m_pct": _opt_float(rec.get("5分钟涨跌")),
                "speed_pct": _opt_float(rec.get("涨速")),
                "change_60d_pct": _opt_float(rec.get("60日涨跌幅")),
                "change_ytd_pct": _opt_float(rec.get("年初至今涨跌幅")),
            }
        )
    return rows


def count_stock_daily(conn, trade_date: date) -> int:
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM stock_daily WHERE trade_date = %s",
        (trade_date.isoformat(),),
    )
    row = cur.fetchone()
    return int(row[0] if row else 0)


def sync_stock_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    td = trade_date or _trade_date_today()
    td_s = td.isoformat()
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    job_id = None
    try:
        cur.execute(
            """
            INSERT INTO stock_daily_jobs (trade_date, started_at, ok)
            VALUES (%s, %s, 0)
            """,
            (td_s, _utc_now_iso()),
        )
        job_id = cur.lastrowid

        payload = fetch_a_share_spot_em()
        if len(payload) < _MIN_ROWS_OK:
            raise RuntimeError(f"stock spot rows too few: {len(payload)}")

        now = _utc_now_iso()
        cur.execute("DELETE FROM stock_daily WHERE trade_date = %s", (td_s,))
        params = [
            (
                td_s,
                r["code"],
                r["name"],
                r["price"],
                r["change_pct"],
                r["float_market_cap"],
                r["total_market_cap"],
                r["turnover_pct"],
                r["amount"],
                r["pe_dynamic"],
                r["pb"],
                r["volume_ratio"],
                r["amplitude_pct"],
                r["change_5m_pct"],
                r["speed_pct"],
                r["change_60d_pct"],
                r["change_ytd_pct"],
                now,
            )
            for r in payload
        ]
        cur.executemany(
            """
            INSERT INTO stock_daily (
              trade_date, code, name, price, change_pct,
              float_market_cap, total_market_cap, turnover_pct, amount,
              pe_dynamic, pb, volume_ratio, amplitude_pct,
              change_5m_pct, speed_pct, change_60d_pct, change_ytd_pct,
              updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            params,
        )
        cur.execute(
            """
            UPDATE stock_daily_jobs
            SET finished_at = %s, ok = 1, row_count = %s, error = NULL
            WHERE id = %s
            """,
            (_utc_now_iso(), len(payload), job_id),
        )
        raw.commit()
        logger.info("stock_daily sync OK %s rows=%s", td_s, len(payload))
        return {"ok": True, "trade_date": td_s, "count": len(payload), "job_id": job_id}
    except Exception as exc:  # noqa: BLE001
        err = f"{exc}\n{traceback.format_exc()}"
        logger.exception("sync_stock_daily failed")
        if job_id is not None:
            cur.execute(
                """
                UPDATE stock_daily_jobs
                SET finished_at = %s, ok = 0, error = %s
                WHERE id = %s
                """,
                (_utc_now_iso(), err[:4000], job_id),
            )
        try:
            raw.commit()
        except Exception:
            raw.rollback()
        return {"ok": False, "trade_date": td_s, "error": str(exc), "job_id": job_id}
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()


def ensure_stock_daily(trade_date: Optional[date] = None) -> dict[str, Any]:
    """Sync spot table for ``trade_date`` if missing or too few rows."""
    td = trade_date or _trade_date_today()
    engine = get_engine()
    raw = engine.raw_connection()
    try:
        n = count_stock_daily(raw, td)
        if n >= _MIN_ROWS_OK:
            return {"ok": True, "trade_date": td.isoformat(), "count": n, "skipped": True}
    finally:
        raw.close()
    return sync_stock_daily(td)
