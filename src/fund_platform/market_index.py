"""Major A-share index quotes: intraday snapshots + daily close."""

from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, time as dt_time, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine

logger = logging.getLogger(__name__)

_CN_TZ = ZoneInfo("Asia/Shanghai")

# (code, display name) — 东财「沪深重要指数」子集
_DEFAULT_INDEX_CODES: list[tuple[str, str]] = [
    ("000001", "上证指数"),
    ("399001", "深证成指"),
    ("399006", "创业板指"),
    ("000300", "沪深300"),
    ("000016", "上证50"),
    ("000688", "科创50"),
    ("000905", "中证500"),
]

# 东财全球指数名称（代码 HSI/SPX/NDX 等；NDX=纳斯达克100）
_DEFAULT_GLOBAL_NAMES: list[str] = [
    "恒生指数",
    "标普500",
    "纳斯达克",
    "道琼斯",
    "日经225",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _now_cn() -> datetime:
    return datetime.now(_CN_TZ)


def cn_watchlist() -> list[tuple[str, str]]:
    raw = fp_settings.market_index_codes()
    if not raw:
        return list(_DEFAULT_INDEX_CODES)
    out: list[tuple[str, str]] = []
    for item in raw:
        if ":" in item:
            code, name = item.split(":", 1)
            out.append((code.strip().zfill(6), name.strip()))
        else:
            code = item.strip().zfill(6)
            out.append((code, code))
    return out


def global_watchlist() -> list[str]:
    """East Money 全球指数中文名（美股等，不含港股；港股见 hk_watchlist）。"""
    names = fp_settings.market_index_global_names()
    base = names if names else list(_DEFAULT_GLOBAL_NAMES)
    hk = set(hk_watchlist())
    return [n for n in base if n not in hk]


def hk_watchlist() -> list[str]:
    names = fp_settings.market_index_hk_names()
    return names if names else ["恒生指数"]


def watchlist() -> list[tuple[str, str]]:
    """Backward-compatible alias for A-share watchlist."""
    return cn_watchlist()


def is_global_index_poll_day(now: Optional[datetime] = None) -> bool:
    """Mon–Fri poll global indices (US/EU trade during CN nights)."""
    t = now or _now_cn()
    if t.tzinfo is None:
        t = t.replace(tzinfo=_CN_TZ)
    else:
        t = t.astimezone(_CN_TZ)
    return t.weekday() < 5


def code_to_sina_symbol(code: str) -> str:
    c = code.strip().zfill(6)
    if c.startswith(("399", "159", "16")):
        return f"sz{c}"
    return f"sh{c}"


def code_to_em_symbol(code: str) -> str:
    """East Money daily K-line symbol prefix (sh000300 / sz399001)."""
    return code_to_sina_symbol(code)


_EM_CN_KLINE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/center/hszs.html",
}

_EM_CN_KLINE_URLS = (
    "https://push2his.eastmoney.com/api/qt/stock/kline/get",
    "https://48.push2his.eastmoney.com/api/qt/stock/kline/get",
)


def is_cn_equity_trading_session(now: Optional[datetime] = None) -> bool:
    """Mon–Fri 09:30–11:30, 13:00–15:00 Asia/Shanghai."""
    t = now or _now_cn()
    if t.tzinfo is None:
        t = t.replace(tzinfo=_CN_TZ)
    else:
        t = t.astimezone(_CN_TZ)
    if t.weekday() >= 5:
        return False
    cur = t.time()
    return (dt_time(9, 30) <= cur <= dt_time(11, 30)) or (
        dt_time(13, 0) <= cur <= dt_time(15, 0)
    )


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "")
    if not s or s in ("-", "--", "nan", "NaN"):
        return None
    try:
        v = float(s)
        return v if v == v else None
    except ValueError:
        return None


def _opt_int(value: Any) -> Optional[int]:
    f = _opt_float(value)
    if f is None:
        return None
    return int(f)


def fetch_main_indices_em(*, max_attempts: int = 4) -> list[dict[str, Any]]:
    """East Money 沪深重要指数 spot (single page)."""
    import pandas as pd
    import requests

    url = "https://33.push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": "1",
        "pz": "200",
        "po": "1",
        "np": "1",
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": "2",
        "invt": "2",
        "dect": "1",
        "wbp2u": "|0|0|0|web",
        "fid": "",
        "fs": "b:MK0010",
        "fields": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f13,f14,f15,f16,f17,f18,f20,f21,"
        "f23,f24,f25,f26,f22,f11,f62,f128,f136,f115,f152",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://quote.eastmoney.com/center/hszs.html",
    }
    urls = (
        url,
        "https://48.push2.eastmoney.com/api/qt/clist/get",
        "https://push2.eastmoney.com/api/qt/clist/get",
    )
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        for base in urls:
            try:
                r = requests.get(base, params=params, headers=headers, timeout=25)
                r.raise_for_status()
                data = r.json().get("data", {}).get("diff") or []
                if not data:
                    continue
                df = pd.DataFrame(data)
                df.rename(
                    columns={
                        "f2": "最新价",
                        "f3": "涨跌幅",
                        "f4": "涨跌额",
                        "f5": "成交量",
                        "f6": "成交额",
                        "f7": "振幅",
                        "f12": "代码",
                        "f14": "名称",
                        "f15": "最高",
                        "f16": "最低",
                        "f17": "今开",
                        "f18": "昨收",
                    },
                    inplace=True,
                )
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
                            "last_price": _opt_float(rec.get("最新价")),
                            "change_pct": _opt_float(rec.get("涨跌幅")),
                            "change_amt": _opt_float(rec.get("涨跌额")),
                            "open_px": _opt_float(rec.get("今开")),
                            "high_px": _opt_float(rec.get("最高")),
                            "low_px": _opt_float(rec.get("最低")),
                            "prev_close": _opt_float(rec.get("昨收")),
                            "volume": _opt_int(rec.get("成交量")),
                            "amount": _opt_float(rec.get("成交额")),
                            "amplitude_pct": _opt_float(rec.get("振幅")),
                        }
                    )
                delay = fp_settings.market_index_request_delay_sec()
                if delay > 0:
                    time.sleep(delay)
                return rows
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        time.sleep(fp_settings.market_index_retry_sleep_sec() * (attempt + 1))
    if last_exc:
        raise last_exc
    return []


def fetch_global_indices_em(*, max_attempts: int = 4) -> list[dict[str, Any]]:
    """East Money 全球指数 spot（含标普500、纳斯达克、道琼斯、恒生等）。"""
    import pandas as pd
    import requests

    params = {
        "np": "2",
        "fltt": "1",
        "invt": "2",
        "fs": "i:1.000001,i:0.399001,i:0.399005,i:0.399006,i:1.000300,i:100.HSI,i:100.HSCEI,i:124.HSCCI,"
        "i:100.TWII,i:100.N225,i:100.KOSPI200,i:100.KS11,i:100.STI,i:100.SENSEX,i:100.KLSE,i:100.SET,"
        "i:100.PSI,i:100.KSE100,i:100.VNINDEX,i:100.JKSE,i:100.CSEALL,i:100.SX5E,i:100.FTSE,i:100.MCX,"
        "i:100.AXX,i:100.FCHI,i:100.GDAXI,i:100.RTS,i:100.IBEX,i:100.PSI20,i:100.OMXC20,i:100.BFX,"
        "i:100.AEX,i:100.WIG,i:100.OMXSPI,i:100.SSMI,i:100.HEX,i:100.OSEBX,i:100.ATX,i:100.MIB,"
        "i:100.ASE,i:100.ICEXI,i:100.PX,i:100.ISEQ,i:100.DJIA,i:100.SPX,i:100.NDX,i:100.TSX,"
        "i:100.BVSP,i:100.MXX,i:100.AS51,i:100.AORD,i:100.NZ50,i:100.UDI,i:100.BDI,i:100.CRB",
        "fields": "f12,f13,f14,f292,f1,f2,f4,f3,f152,f17,f18,f15,f16,f7,f124",
        "fid": "f3",
        "pn": "1",
        "pz": "200",
        "po": "1",
        "dect": "1",
        "wbp2u": "|0|0|0|web",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://quote.eastmoney.com/center/gridlist.html",
    }
    urls = (
        "https://push2.eastmoney.com/api/qt/clist/get",
        "https://48.push2.eastmoney.com/api/qt/clist/get",
    )
    last_exc: Optional[Exception] = None
    for attempt in range(max_attempts):
        for url in urls:
            try:
                r = requests.get(url, params=params, headers=headers, timeout=25)
                r.raise_for_status()
                data = r.json().get("data", {}).get("diff") or []
                if not data:
                    continue
                if isinstance(data, dict):
                    df = pd.DataFrame(data).T
                else:
                    df = pd.DataFrame(data)
                if "f12" in df.columns:
                    df.rename(
                        columns={
                            "f12": "代码",
                            "f14": "名称",
                            "f2": "最新价",
                            "f3": "涨跌幅",
                            "f4": "涨跌额",
                            "f17": "开盘价",
                            "f15": "最高价",
                            "f16": "最低价",
                            "f18": "昨收价",
                            "f7": "振幅",
                        },
                        inplace=True,
                    )
                rows: list[dict[str, Any]] = []
                for rec in df.to_dict("records"):
                    code = str(rec.get("代码", "")).strip().upper()
                    name = str(rec.get("名称", "")).strip()
                    if not code or not name:
                        continue
                    last_price = _opt_float(rec.get("最新价"))
                    if last_price is not None and last_price > 10000:
                        last_price = round(last_price / 100, 4)
                    change_pct = _opt_float(rec.get("涨跌幅"))
                    if change_pct is not None and abs(change_pct) > 100:
                        change_pct = round(change_pct / 100, 4)
                    change_amt = _opt_float(rec.get("涨跌额"))
                    if change_amt is not None and abs(change_amt) > 1000:
                        change_amt = round(change_amt / 100, 4)
                    def _px(v: Any) -> Optional[float]:
                        x = _opt_float(v)
                        if x is not None and x > 10000:
                            return round(x / 100, 4)
                        return x

                    rows.append(
                        {
                            "code": code,
                            "name": name,
                            "last_price": last_price,
                            "change_pct": change_pct,
                            "change_amt": change_amt,
                            "open_px": _px(rec.get("开盘价")),
                            "high_px": _px(rec.get("最高价")),
                            "low_px": _px(rec.get("最低价")),
                            "prev_close": _px(rec.get("昨收价")),
                            "volume": None,
                            "amount": None,
                            "amplitude_pct": _opt_float(rec.get("振幅")),
                        }
                    )
                delay = fp_settings.market_index_request_delay_sec()
                if delay > 0:
                    time.sleep(delay)
                return rows
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        time.sleep(fp_settings.market_index_retry_sleep_sec() * (attempt + 1))
    if last_exc:
        raise last_exc
    return []


def _filter_cn_watchlist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    want = {c for c, _ in cn_watchlist()}
    names = {c: n for c, n in cn_watchlist()}
    out: list[dict[str, Any]] = []
    for r in rows:
        code = str(r.get("code", "")).zfill(6)
        if code in want:
            if not r.get("name"):
                r["name"] = names.get(code, code)
            out.append(r)
    return out


def _filter_by_names(
    rows: list[dict[str, Any]], names: list[str]
) -> list[dict[str, Any]]:
    want_names = set(names)
    want_codes = {w.upper() for w in names if w.isascii() and len(w) <= 8}
    out: list[dict[str, Any]] = []
    for r in rows:
        name = str(r.get("name", "")).strip()
        code = str(r.get("code", "")).strip().upper()
        if name in want_names or code in want_codes:
            out.append(r)
    return out


def _filter_global_watchlist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _filter_by_names(rows, global_watchlist())


def _filter_hk_watchlist(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return _filter_by_names(rows, hk_watchlist())


def _insert_intraday_rows(rows: list[dict[str, Any]], quote_time: str) -> None:
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        params = [
            (
                quote_time,
                r["code"],
                r.get("name") or "",
                r.get("last_price"),
                r.get("change_pct"),
                r.get("change_amt"),
                r.get("open_px"),
                r.get("high_px"),
                r.get("low_px"),
                r.get("prev_close"),
                r.get("volume"),
                r.get("amount"),
                r.get("amplitude_pct"),
            )
            for r in rows
        ]
        cur.executemany(
            """
            INSERT INTO market_index_intraday (
              quote_time, code, name, last_price, change_pct, change_amt,
              open_px, high_px, low_px, prev_close, volume, amount, amplitude_pct
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            params,
        )
        raw.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()


def _upsert_daily_batch(rows: list[dict[str, Any]], *, chunk: int = 400) -> int:
    if not rows:
        return 0
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    now = _utc_now_iso()
    sql = """
        INSERT INTO market_index_daily (
          trade_date, code, name, open_px, high_px, low_px, close_px,
          prev_close, change_pct, change_amt, volume, amount, updated_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
          name=VALUES(name), open_px=VALUES(open_px), high_px=VALUES(high_px),
          low_px=VALUES(low_px), close_px=VALUES(close_px),
          prev_close=VALUES(prev_close), change_pct=VALUES(change_pct),
          change_amt=VALUES(change_amt), volume=VALUES(volume),
          amount=COALESCE(VALUES(amount), amount), updated_at=VALUES(updated_at)
    """
    written = 0
    try:
        for i in range(0, len(rows), chunk):
            part = rows[i : i + chunk]
            params = [
                (
                    r["trade_date"],
                    r["code"],
                    r.get("name") or "",
                    r.get("open_px"),
                    r.get("high_px"),
                    r.get("low_px"),
                    r.get("close_px"),
                    r.get("prev_close"),
                    r.get("change_pct"),
                    r.get("change_amt"),
                    r.get("volume"),
                    r.get("amount"),
                    now,
                )
                for r in part
            ]
            cur.executemany(sql, params)
            written += len(part)
        raw.commit()
        return written
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()


def _upsert_daily_rows(rows: list[dict[str, Any]], trade_date: str) -> None:
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    now = _utc_now_iso()
    try:
        for r in rows:
            cur.execute(
                """
                INSERT INTO market_index_daily (
                  trade_date, code, name, open_px, high_px, low_px, close_px,
                  prev_close, change_pct, change_amt, volume, amount, updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON DUPLICATE KEY UPDATE
                  name=VALUES(name), open_px=VALUES(open_px), high_px=VALUES(high_px),
                  low_px=VALUES(low_px), close_px=VALUES(close_px),
                  prev_close=VALUES(prev_close), change_pct=VALUES(change_pct),
                  change_amt=VALUES(change_amt), volume=VALUES(volume),
                  amount=COALESCE(VALUES(amount), amount), updated_at=VALUES(updated_at)
                """,
                (
                    trade_date,
                    r["code"],
                    r.get("name") or "",
                    r.get("open_px"),
                    r.get("high_px"),
                    r.get("low_px"),
                    r.get("last_price"),
                    r.get("prev_close"),
                    r.get("change_pct"),
                    r.get("change_amt"),
                    r.get("volume"),
                    r.get("amount"),
                    now,
                ),
            )
        raw.commit()
    finally:
        try:
            cur.close()
        except Exception:
            pass
        raw.close()


def sync_market_index_intraday(*, force: bool = False) -> dict[str, Any]:
    """A股盘中 + 全球指数工作日快照。"""
    now = _now_cn()
    quote_time = now.strftime("%Y-%m-%d %H:%M:%S")
    rows: list[dict[str, Any]] = []
    parts: dict[str, Any] = {}

    if force or is_cn_equity_trading_session(now):
        try:
            cn_rows = _filter_cn_watchlist(fetch_main_indices_em())
            rows.extend(cn_rows)
            parts["cn"] = len(cn_rows)
        except Exception as exc:  # noqa: BLE001
            logger.exception("market index CN intraday failed")
            parts["cn_error"] = str(exc)
    else:
        parts["cn"] = "skipped"

    if force or is_global_index_poll_day(now):
        try:
            raw_global = fetch_global_indices_em()
            if global_watchlist():
                g_rows = _filter_global_watchlist(raw_global)
                rows.extend(g_rows)
                parts["global"] = len(g_rows)
            else:
                parts["global"] = 0
            if hk_watchlist() and (force or is_cn_equity_trading_session(now)):
                hk_rows = _filter_hk_watchlist(raw_global)
                rows.extend(hk_rows)
                parts["hk"] = len(hk_rows)
            else:
                parts["hk"] = "skipped"
        except Exception as exc:  # noqa: BLE001
            logger.exception("market index global intraday failed")
            parts["global_error"] = str(exc)
    else:
        parts["global"] = "skipped"
        parts["hk"] = "skipped"

    if not rows:
        return {"ok": True, "skipped": True, "reason": "no_rows", "parts": parts}

    try:
        _insert_intraday_rows(rows, quote_time)
        logger.info("market_index_intraday ok time=%s %s", quote_time, parts)
        return {"ok": True, "quote_time": quote_time, "count": len(rows), "parts": parts}
    except Exception as exc:  # noqa: BLE001
        logger.exception("market_index_intraday insert failed")
        return {"ok": False, "error": str(exc), "parts": parts}


def sync_market_index_daily_close(
    trade_date: Optional[date] = None,
    *,
    scope: str = "all",
) -> dict[str, Any]:
    """Persist EOD: scope=cn | global | hk | all.

    Overseas indices use per-symbol daily K-line (+ Sina fallback), not the bulk
    East Money spot list API (unstable from cloud hosts).
    """
    td = trade_date or _now_cn().date()
    td_s = td.isoformat()
    daily_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    if scope in ("cn", "all"):
        cn_rows, cn_err = _fetch_cn_daily_eod(td)
        daily_rows.extend(cn_rows)
        errors.extend(cn_err)

    overseas_names: list[str] = []
    if scope in ("global", "all"):
        overseas_names.extend(global_watchlist())
    if scope in ("hk", "all"):
        for name in hk_watchlist():
            if name not in overseas_names:
                overseas_names.append(name)
    if overseas_names:
        g_rows, g_err = _fetch_overseas_daily_eod(overseas_names, as_of=td)
        daily_rows.extend(g_rows)
        errors.extend(g_err)

    if not daily_rows:
        err = "; ".join(errors[:8]) if errors else "no index rows"
        return {"ok": False, "error": err, "trade_date": td_s, "scope": scope}

    try:
        count = _upsert_daily_batch(daily_rows)
        logger.info(
            "market_index_daily ok date=%s scope=%s count=%s warnings=%s",
            td_s,
            scope,
            count,
            len(errors),
        )
        out: dict[str, Any] = {
            "ok": True,
            "trade_date": td_s,
            "count": count,
            "scope": scope,
        }
        if errors:
            out["warnings"] = errors
        return out
    except Exception as exc:  # noqa: BLE001
        logger.exception("market_index_daily insert failed")
        return {"ok": False, "error": str(exc), "trade_date": td_s, "scope": scope}


def _parse_trade_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if " " in s:
        s = s.split(" ", 1)[0]
    s = s.replace("/", "-")
    if len(s) >= 10:
        return s[:10]
    return None


def _filter_since(rows: list[dict[str, Any]], start: Optional[date]) -> list[dict[str, Any]]:
    if start is None:
        return rows
    start_s = start.isoformat()
    return [r for r in rows if str(r.get("trade_date", "")) >= start_s]


def _merge_cn_amount_from_em(
    base_rows: list[dict[str, Any]],
    em_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Overlay East Money 成交额 onto Sina OHLC rows (matched by trade_date)."""
    amount_by_date = {
        str(r["trade_date"]): r.get("amount")
        for r in em_rows
        if r.get("trade_date") and r.get("amount") is not None
    }
    if not amount_by_date:
        return base_rows
    out: list[dict[str, Any]] = []
    for row in base_rows:
        merged = dict(row)
        amt = amount_by_date.get(str(row.get("trade_date", "")))
        if amt is not None:
            merged["amount"] = amt
        out.append(merged)
    return out


def fetch_cn_index_daily_history_em(code: str, name: str) -> list[dict[str, Any]]:
    """East Money index daily K (成交额); browser headers for ECS."""
    import requests

    sym = code_to_em_symbol(code)
    c = code.strip().zfill(6)
    if sym.startswith("sz"):
        secid = f"0.{c}"
    else:
        secid = f"1.{c}"

    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58",
        "klt": "101",
        "fqt": "0",
        "beg": "19900101",
        "end": "20500101",
    }
    last_exc: Optional[Exception] = None
    for attempt in range(4):
        for url in _EM_CN_KLINE_URLS:
            try:
                r = requests.get(
                    url,
                    params=params,
                    headers=_EM_CN_KLINE_HEADERS,
                    timeout=30,
                )
                r.raise_for_status()
                klines = (r.json().get("data") or {}).get("klines") or []
                if not klines:
                    continue
                rows: list[dict[str, Any]] = []
                for line in klines:
                    parts = str(line).split(",")
                    if len(parts) < 7:
                        continue
                    td = _parse_trade_date(parts[0])
                    if not td:
                        continue
                    rows.append(
                        {
                            "trade_date": td,
                            "code": c,
                            "name": name,
                            "open_px": _opt_float(parts[1]),
                            "close_px": _opt_float(parts[2]),
                            "high_px": _opt_float(parts[3]),
                            "low_px": _opt_float(parts[4]),
                            "volume": _opt_int(parts[5]),
                            "amount": _opt_float(parts[6]),
                            "prev_close": None,
                            "change_pct": None,
                            "change_amt": None,
                        }
                    )
                if rows:
                    delay = fp_settings.market_index_request_delay_sec()
                    if delay > 0:
                        time.sleep(delay)
                    return _attach_daily_returns(rows)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        time.sleep(fp_settings.market_index_retry_sleep_sec() * (attempt + 1))
    if last_exc:
        raise last_exc
    return []


def fetch_cn_index_daily_history_sina(code: str, name: str) -> list[dict[str, Any]]:
    """Sina full daily OHLCV for one A-share index (no 成交额)."""
    import akshare as ak

    sina = code_to_sina_symbol(code)
    last_exc: Optional[Exception] = None
    for attempt in range(4):
        try:
            df = ak.stock_zh_index_daily(symbol=sina)
            rows: list[dict[str, Any]] = []
            prev_close: Optional[float] = None
            for rec in df.to_dict("records"):
                td = _parse_trade_date(rec.get("date"))
                if not td:
                    continue
                close = _opt_float(rec.get("close"))
                open_px = _opt_float(rec.get("open"))
                high_px = _opt_float(rec.get("high"))
                low_px = _opt_float(rec.get("low"))
                change_pct = None
                change_amt = None
                if prev_close is not None and close is not None and prev_close != 0:
                    change_amt = round(close - prev_close, 4)
                    change_pct = round(change_amt / prev_close * 100, 4)
                rows.append(
                    {
                        "trade_date": td,
                        "code": code.zfill(6),
                        "name": name,
                        "open_px": open_px,
                        "high_px": high_px,
                        "low_px": low_px,
                        "close_px": close,
                        "prev_close": prev_close,
                        "change_pct": change_pct,
                        "change_amt": change_amt,
                        "volume": _opt_int(rec.get("volume")),
                        "amount": None,
                    }
                )
                if close is not None:
                    prev_close = close
            delay = fp_settings.market_index_request_delay_sec()
            if delay > 0:
                time.sleep(delay)
            return rows
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(fp_settings.market_index_retry_sleep_sec() * (attempt + 1))
    if last_exc:
        raise last_exc
    return []


def fetch_cn_index_daily_history(code: str, name: str) -> list[dict[str, Any]]:
    """Sina OHLCV + East Money 成交额 overlay (EM optional on failure)."""
    rows = fetch_cn_index_daily_history_sina(code, name)
    if not rows:
        return rows
    em_err: Optional[str] = None
    for attempt in range(3):
        try:
            em_rows = fetch_cn_index_daily_history_em(code, name)
            if em_rows:
                merged = _merge_cn_amount_from_em(rows, em_rows)
                with_amt = sum(1 for r in merged if r.get("amount") is not None)
                logger.info(
                    "cn index %s amount overlay: %s/%s days from EM",
                    code,
                    with_amt,
                    len(merged),
                )
                return merged
        except Exception as exc:  # noqa: BLE001
            em_err = str(exc)
            logger.warning(
                "cn index %s EM amount fetch attempt %s: %s",
                code,
                attempt + 1,
                exc,
            )
            time.sleep(fp_settings.market_index_retry_sleep_sec() * (attempt + 1))
    if em_err:
        logger.warning("cn index %s proceeding without EM amount: %s", code, em_err)
    return rows


def _global_em_secid(em_name: str) -> str:
    from akshare.index.cons import index_global_em_symbol_map

    meta = index_global_em_symbol_map[em_name]
    return f"{meta['market']}.{meta['code']}"


# 东财 K 线历史在 ECS/高频场景易 403；新浪备用（与 EM 代码对齐）
_SINA_US_INDEX: dict[str, tuple[str, str, str]] = {
    "纳斯达克": (".NDX", "NDX", "纳斯达克"),
    "道琼斯": (".DJI", "DJI", "道琼斯"),
    "标普500": (".INX", "SPX", "标普500"),
}


def fetch_global_index_daily_history_sina(
    em_name: str, *, min_date: Optional[date] = None
) -> list[dict[str, Any]]:
    """Sina / akshare fallback for global + HK daily history."""
    import akshare as ak

    min_s = min_date.isoformat() if min_date else None
    if em_name == "恒生指数":
        df = ak.stock_hk_index_daily_sina(symbol="HSI")
        code, disp_name = "HSI", "恒生指数"
    elif em_name == "日经225":
        df = ak.index_global_hist_sina(symbol="日经225指数")
        code, disp_name = "N225", "日经225"
    elif em_name in _SINA_US_INDEX:
        sina_sym, code, disp_name = _SINA_US_INDEX[em_name]
        df = ak.index_us_stock_sina(symbol=sina_sym)
    else:
        raise ValueError(f"no sina mapping for global index: {em_name}")

    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        td = _parse_trade_date(rec.get("date"))
        if not td or (min_s and td < min_s):
            continue
        rows.append(
            {
                "trade_date": td,
                "code": code,
                "name": disp_name,
                "open_px": _opt_float(rec.get("open")),
                "high_px": _opt_float(rec.get("high")),
                "low_px": _opt_float(rec.get("low")),
                "close_px": _opt_float(rec.get("close")),
                "prev_close": None,
                "change_pct": None,
                "change_amt": None,
                "volume": _opt_int(rec.get("volume")),
                "amount": _opt_float(rec.get("amount")),
            }
        )
    delay = fp_settings.market_index_request_delay_sec()
    if delay > 0:
        time.sleep(delay)
    return _attach_daily_returns(rows)


def _kline_page_to_rows(
    klines: list[Any],
    *,
    code: str,
    disp_name: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in klines:
        parts = str(line).split(",")
        if len(parts) < 5:
            continue
        td = _parse_trade_date(parts[0])
        if not td:
            continue
        rows.append(
            {
                "trade_date": td,
                "code": code,
                "name": disp_name,
                "open_px": _opt_float(parts[1]),
                "close_px": _opt_float(parts[2]),
                "high_px": _opt_float(parts[3]),
                "low_px": _opt_float(parts[4]),
                "prev_close": None,
                "change_pct": None,
                "change_amt": None,
                "volume": None,
                "amount": None,
            }
        )
    return rows


def _attach_daily_returns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_rows = sorted(rows, key=lambda r: str(r.get("trade_date", "")))
    prev_close: Optional[float] = None
    out: list[dict[str, Any]] = []
    for r in sorted_rows:
        close = _opt_float(r.get("close_px"))
        change_pct = None
        change_amt = None
        if prev_close is not None and close is not None and prev_close != 0:
            change_amt = round(close - prev_close, 4)
            change_pct = round(change_amt / prev_close * 100, 4)
        out.append({**r, "prev_close": prev_close, "change_pct": change_pct, "change_amt": change_amt})
        if close is not None:
            prev_close = close
    return out


def _pick_latest_bar_on_or_before(
    rows: list[dict[str, Any]], as_of: date
) -> Optional[dict[str, Any]]:
    as_of_s = as_of.isoformat()
    candidates = [r for r in rows if str(r.get("trade_date", "")) <= as_of_s]
    if not candidates:
        return None
    return max(candidates, key=lambda r: str(r["trade_date"]))


def fetch_global_index_recent_bars(
    em_name: str,
    *,
    min_date: date,
    page_size: int = 40,
) -> list[dict[str, Any]]:
    """Recent daily bars for one global/HK index (EOD sync; not full backfill).

    Prefer Sina/AkShare (stable from cloud hosts); East Money kline is fallback only.
    """
    min_s = min_date.isoformat()
    try:
        rows = fetch_global_index_daily_history_sina(em_name, min_date=min_date)
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        logger.warning("sina recent bars failed for %s: %s — try EM kline", em_name, exc)
    try:
        secid = _global_em_secid(em_name)
    except (KeyError, ImportError, ValueError):
        return []
    try:
        klines, code, name = _fetch_global_kline_page(
            secid, end_token="20500000", page_size=page_size, max_attempts=1
        )
        if not klines:
            return []
        page_rows = _kline_page_to_rows(klines, code=code, disp_name=name or em_name)
        rows = _attach_daily_returns(page_rows)
        return [r for r in rows if str(r.get("trade_date", "")) >= min_s]
    except Exception as exc:  # noqa: BLE001
        logger.warning("EM recent bars failed for %s: %s", em_name, exc)
        return []


def _fetch_overseas_daily_eod(
    names: list[str],
    *,
    as_of: date,
    lookback_days: int = 12,
) -> tuple[list[dict[str, Any]], list[str]]:
    min_date = as_of - timedelta(days=lookback_days)
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    seen: set[str] = set()
    for em_name in names:
        if em_name in seen:
            continue
        seen.add(em_name)
        try:
            bars = fetch_global_index_recent_bars(em_name, min_date=min_date)
            bar = _pick_latest_bar_on_or_before(bars, as_of)
            if bar:
                rows.append(bar)
            else:
                errors.append(f"{em_name}: no bar on/before {as_of.isoformat()}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("overseas EOD fetch failed %s: %s", em_name, exc)
            errors.append(f"{em_name}: {exc}")
        delay = fp_settings.market_index_request_delay_sec()
        if delay > 0:
            time.sleep(delay)
    return rows, errors


def _cn_spot_to_daily_rows(spot_rows: list[dict[str, Any]], trade_date: str) -> list[dict[str, Any]]:
    return [
        {
            "trade_date": trade_date,
            "code": r["code"],
            "name": r.get("name") or "",
            "open_px": r.get("open_px"),
            "high_px": r.get("high_px"),
            "low_px": r.get("low_px"),
            "close_px": r.get("last_price"),
            "prev_close": r.get("prev_close"),
            "change_pct": r.get("change_pct"),
            "change_amt": r.get("change_amt"),
            "volume": r.get("volume"),
            "amount": r.get("amount"),
        }
        for r in spot_rows
    ]


def _fetch_cn_daily_eod(as_of: date) -> tuple[list[dict[str, Any]], list[str]]:
    """Per-index Sina OHLCV + East Money 成交额 overlay."""
    td_s = as_of.isoformat()
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    for code, name in cn_watchlist():
        try:
            hist = fetch_cn_index_daily_history(code, name)
            bar = _pick_latest_bar_on_or_before(hist, as_of)
            if bar:
                rows.append(bar)
            else:
                errors.append(f"{code}: no bar on/before {td_s}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("CN index EOD fetch failed %s: %s", code, exc)
            errors.append(f"{code}: {exc}")
    return rows, errors


def _fetch_global_kline_page(
    secid: str,
    *,
    end_token: str,
    page_size: int,
    max_attempts: int = 5,
) -> tuple[list[Any], str, str]:
    import requests

    page_size = max(40, min(int(page_size), 200))
    params = {
        "secid": secid,
        "klt": "101",
        "fqt": "1",
        "lmt": str(page_size),
        "end": end_token,
        "iscca": "1",
        "fields1": "f1,f2,f3,f4,f5,f6,f7,f8",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64",
        "ut": "f057cbcbce2a86e2866ab8877db1d059",
        "forcect": "1",
    }
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://quote.eastmoney.com/center/gridlist.html",
    }
    urls = (
        "https://48.push2his.eastmoney.com/api/qt/stock/kline/get",
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
    )
    last_exc: Optional[Exception] = None
    for attempt in range(max(1, max_attempts)):
        for url in urls:
            try:
                r = requests.get(url, params=params, headers=headers, timeout=30)
                r.raise_for_status()
                payload = r.json().get("data") or {}
                klines = payload.get("klines") or []
                code = str(payload.get("code", "")).strip().upper()
                name = str(payload.get("name", "")).strip()
                return klines, code, name
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
        time.sleep(fp_settings.market_index_retry_sleep_sec() * (attempt + 1))
    if last_exc:
        raise last_exc
    return [], "", ""


def fetch_global_index_daily_history(
    em_name: str,
    *,
    min_date: Optional[date] = None,
    page_size: int = 120,
) -> list[dict[str, Any]]:
    """East Money global index daily K-line (paginated; avoids huge ``lmt``)."""
    secid = _global_em_secid(em_name)
    min_s = min_date.isoformat() if min_date else None
    end_token = "20500000"
    by_date: dict[str, dict[str, Any]] = {}
    code = ""
    disp_name = em_name
    max_pages = 64

    try:
        klines, code, name = _fetch_global_kline_page(
            secid, end_token=end_token, page_size=page_size
        )
        if name:
            disp_name = name
        if klines:
            page_rows = _kline_page_to_rows(klines, code=code, disp_name=disp_name)
            for row in page_rows:
                by_date[str(row["trade_date"])] = row
    except Exception as exc:  # noqa: BLE001
        logger.warning("EM global kline failed for %s: %s — sina fallback", em_name, exc)
        return fetch_global_index_daily_history_sina(em_name, min_date=min_date)

    for _ in range(max_pages - 1):
        if not by_date:
            break
        oldest = min(by_date.keys())
        if min_s and oldest <= min_s:
            break
        oldest_dt = date.fromisoformat(oldest)
        end_token = (oldest_dt - timedelta(days=1)).strftime("%Y%m%d")
        delay = fp_settings.market_index_request_delay_sec()
        if delay > 0:
            time.sleep(delay)
        try:
            klines, code, name = _fetch_global_kline_page(
                secid, end_token=end_token, page_size=page_size
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("EM global kline page failed for %s: %s", em_name, exc)
            break
        if not klines:
            break
        page_rows = _kline_page_to_rows(klines, code=code or disp_name, disp_name=disp_name)
        for row in page_rows:
            by_date[str(row["trade_date"])] = row
        if len(klines) < page_size:
            break

    rows = _attach_daily_returns(list(by_date.values()))
    if min_s:
        rows = [r for r in rows if str(r.get("trade_date", "")) >= min_s]
    if rows:
        return rows
    return fetch_global_index_daily_history_sina(em_name, min_date=min_date)


def backfill_cn_index_daily_amount(*, days: Optional[int] = None) -> dict[str, Any]:
    """Backfill A-share index 成交额 from East Money onto existing daily rows."""
    day_limit = fp_settings.market_index_backfill_days() if days is None else max(0, days)
    start: Optional[date] = None
    if day_limit > 0:
        start = _now_cn().date() - timedelta(days=day_limit)

    summary: dict[str, Any] = {
        "ok": True,
        "days": day_limit,
        "start_date": start.isoformat() if start else None,
        "cn": {},
        "errors": [],
    }
    total_written = 0
    for code, name in cn_watchlist():
        key = code
        try:
            rows = fetch_cn_index_daily_history(code, name)
            rows = _filter_since(rows, start)
            with_amt = sum(1 for r in rows if r.get("amount") is not None)
            n = _upsert_daily_batch(rows)
            total_written += n
            summary["cn"][key] = {"rows": n, "with_amount": with_amt, "name": name}
            logger.info(
                "cn index amount backfill %s rows=%s with_amount=%s",
                key,
                n,
                with_amt,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("cn index amount backfill %s failed", key)
            summary["errors"].append({"scope": "cn", "code": key, "error": str(exc)})
            summary["ok"] = False
    summary["written"] = total_written
    return summary


def backfill_market_index_daily(
    *,
    days: Optional[int] = None,
    only_global_names: Optional[list[str]] = None,
    skip_cn: bool = False,
) -> dict[str, Any]:
    """
    One-shot init: load historical daily bars for CN + global/HK watchlists
    into ``market_index_daily``.

    ``only_global_names``: retry subset, e.g. ["纳斯达克", "恒生指数"].
    """
    day_limit = fp_settings.market_index_backfill_days() if days is None else max(0, days)
    start: Optional[date] = None
    if day_limit > 0:
        start = _now_cn().date() - timedelta(days=day_limit)

    summary: dict[str, Any] = {
        "ok": True,
        "days": day_limit,
        "start_date": start.isoformat() if start else None,
        "cn": {},
        "global": {},
        "errors": [],
    }
    total_written = 0

    if not skip_cn and not only_global_names:
        cn_list = cn_watchlist()
    else:
        cn_list = []

    for code, name in cn_list:
        key = code
        try:
            rows = fetch_cn_index_daily_history(code, name)
            rows = _filter_since(rows, start)
            n = _upsert_daily_batch(rows)
            total_written += n
            summary["cn"][key] = {"rows": n, "name": name}
            logger.info("market_index backfill CN %s rows=%s", key, n)
        except Exception as exc:  # noqa: BLE001
            logger.exception("market_index backfill CN %s failed", key)
            summary["errors"].append({"scope": "cn", "code": key, "error": str(exc)})
            summary["cn"][key] = {"error": str(exc)}

    seen_global: set[str] = set()
    if only_global_names:
        global_names = [n.strip() for n in only_global_names if n and n.strip()]
    else:
        global_names = list(global_watchlist()) + list(hk_watchlist())
    for em_name in global_names:
        if em_name in seen_global:
            continue
        seen_global.add(em_name)
        time.sleep(max(3.0, fp_settings.market_index_request_delay_sec() * 2))
        try:
            rows = fetch_global_index_daily_history(em_name, min_date=start)
            n = _upsert_daily_batch(rows)
            total_written += n
            summary["global"][em_name] = {"rows": n}
            logger.info("market_index backfill global %s rows=%s", em_name, n)
        except Exception as exc:  # noqa: BLE001
            logger.exception("market_index backfill global %s failed", em_name)
            summary["errors"].append({"scope": "global", "name": em_name, "error": str(exc)})
            summary["global"][em_name] = {"error": str(exc)}

    summary["total_written"] = total_written
    summary["ok"] = not summary["errors"] or total_written > 0
    logger.info(
        "market_index backfill done days=%s written=%s errors=%s",
        day_limit,
        total_written,
        len(summary["errors"]),
    )
    return summary


def query_index_daily_closes(
    conn,
    code: str,
    *,
    min_date: Optional[str] = None,
    max_date: Optional[str] = None,
) -> dict[str, float]:
    """``trade_date`` (YYYY-MM-DD) → ``close_px`` for index daily K."""
    import pymysql.cursors

    sym = code.strip().zfill(6)
    cur = conn.cursor(pymysql.cursors.DictCursor)
    clauses = ["code = %s", "close_px IS NOT NULL"]
    params: list[Any] = [sym]
    if min_date:
        clauses.append("trade_date >= %s")
        params.append(str(min_date)[:10])
    if max_date:
        clauses.append("trade_date <= %s")
        params.append(str(max_date)[:10])
    cur.execute(
        f"""
        SELECT trade_date, close_px
        FROM market_index_daily
        WHERE {' AND '.join(clauses)}
        ORDER BY trade_date ASC
        """,
        params,
    )
    out: dict[str, float] = {}
    for row in cur.fetchall():
        td = row["trade_date"]
        ds = td.isoformat() if hasattr(td, "isoformat") else str(td)[:10]
        out[ds] = float(row["close_px"])
    return out


def align_index_closes_to_dates(
    dates: list[str], index_map: dict[str, float]
) -> list[Optional[float]]:
    """Forward-fill index close onto each calendar date (last close on or before date)."""
    if not index_map or not dates:
        return [None] * len(dates)
    sorted_dates = sorted(index_map.keys())
    last: Optional[float] = None
    j = 0
    out: list[Optional[float]] = []
    for d in dates:
        while j < len(sorted_dates) and sorted_dates[j] <= d:
            last = index_map[sorted_dates[j]]
            j += 1
        out.append(last)
    return out
