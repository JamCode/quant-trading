"""Broad index PE sync: CN (Legulegu), HK/US spot (yfinance), US history (Shiller)."""

from __future__ import annotations

import io
import logging
import time
from datetime import date, datetime, timezone
from typing import Any, Optional

from fund_platform import settings as fp_settings
from fund_platform.db import get_engine

logger = logging.getLogger(__name__)

_CN_LG_SYMBOLS: dict[str, str] = {
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "000906.SH": "中证800",
    "000852.SH": "中证1000",
    "000016.SH": "上证50",
    "399673.SZ": "创业板50",
}

_HK_YF: dict[str, str] = {
    "^HSI": "恒生指数",
    "^HSCE": "恒生国企",
    "^HSTECH": "恒生科技",
}

_US_YF: dict[str, str] = {
    "^GSPC": "标普500",
    "^IXIC": "纳斯达克综合",
    "^DJI": "道琼斯",
}

_SHILLER_URL = "http://www.econ.yale.edu/~shiller/data/ie_data.xls"
_SHILLER_CODE = "shiller:SP500"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
        if v != v:
            return None
        return round(v, 4)
    except (TypeError, ValueError):
        return None


def _parse_trade_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s:
        return None
    if " " in s:
        s = s.split(" ", 1)[0]
    s = s.replace("/", "-")
    if len(s) >= 10:
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None


def _cn_legu_name_map() -> dict[str, str]:
    """Legulegu display name -> index_code key."""
    out: dict[str, str] = {}
    for code, name in _CN_LG_SYMBOLS.items():
        out[name] = code
    configured = fp_settings.index_valuation_cn_symbols()
    for item in configured:
        if ":" in item:
            name, code = item.split(":", 1)
            out[name.strip()] = code.strip()
        else:
            name = item.strip()
            for code, n in _CN_LG_SYMBOLS.items():
                if n == name:
                    out[name] = code
                    break
    return out


def _lg_name_to_code() -> dict[str, str]:
    return {
        "上证50": "000016.SH",
        "沪深300": "000300.SH",
        "上证380": "000009.SH",
        "创业板50": "399673.SZ",
        "中证500": "000905.SH",
        "上证180": "000010.SH",
        "深证红利": "399324.SZ",
        "深证100": "399330.SZ",
        "中证1000": "000852.SH",
        "上证红利": "000015.SH",
        "中证100": "000903.SH",
        "中证800": "000906.SH",
    }


def fetch_cn_index_pe_legu() -> tuple[list[dict[str, Any]], list[str]]:
    import akshare as ak

    name_to_code = _lg_name_to_code()
    want_names = list(_cn_legu_name_map().keys())
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    delay = fp_settings.index_valuation_request_delay_sec()
    lookback = fp_settings.index_valuation_cn_lookback_days()
    min_date = date.today().toordinal() - lookback

    for i, lg_name in enumerate(want_names):
        code = name_to_code.get(lg_name)
        if not code:
            errors.append(f"{lg_name}: unknown legulegu code")
            continue
        try:
            df = ak.stock_index_pe_lg(symbol=lg_name)
            if df is None or df.empty:
                errors.append(f"{lg_name}: empty")
                continue
            for rec in df.to_dict("records"):
                td = _parse_trade_date(rec.get("日期"))
                if not td or td.toordinal() < min_date:
                    continue
                rows.append(
                    {
                        "trade_date": td.isoformat(),
                        "region": "cn",
                        "index_code": f"lg:{code}",
                        "index_name": lg_name,
                        "source": "legu",
                        "pe_ttm": _opt_float(rec.get("滚动市盈率")),
                        "pe_static": _opt_float(rec.get("静态市盈率")),
                        "pe_cape": None,
                        "index_close": _opt_float(rec.get("指数")),
                    }
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("CN index PE legulegu failed %s: %s", lg_name, exc)
            errors.append(f"{lg_name}: {exc}")
        if delay > 0 and i + 1 < len(want_names):
            time.sleep(delay)
    return rows, errors


def fetch_yfinance_index_pe(
    mapping: dict[str, str],
    *,
    region: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    import yfinance as yf

    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    td = date.today().isoformat()
    delay = fp_settings.index_valuation_request_delay_sec()

    for i, (sym, name) in enumerate(mapping.items()):
        try:
            info = yf.Ticker(sym).info or {}
            pe = _opt_float(info.get("trailingPE"))
            if pe is None:
                errors.append(f"{sym}: no trailingPE")
                continue
            rows.append(
                {
                    "trade_date": td,
                    "region": region,
                    "index_code": f"yf:{sym}",
                    "index_name": name,
                    "source": "yfinance",
                    "pe_ttm": pe,
                    "pe_static": None,
                    "pe_cape": None,
                    "index_close": _opt_float(info.get("regularMarketPrice") or info.get("previousClose")),
                }
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("yfinance PE failed %s: %s", sym, exc)
            errors.append(f"{sym}: {exc}")
        if delay > 0 and i + 1 < len(mapping):
            time.sleep(delay)
    return rows, errors


def fetch_us_shiller_sp500() -> tuple[list[dict[str, Any]], list[str]]:
    import pandas as pd
    import requests

    errors: list[str] = []
    url = fp_settings.index_valuation_shiller_url()
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        df = pd.read_excel(io.BytesIO(r.content), sheet_name="Data", skiprows=7)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Shiller xls fetch failed: %s", exc)
        return [], [str(exc)]

    df.columns = [str(c).strip() for c in df.columns]
    date_col = df.columns[0]
    price_col = df.columns[1] if len(df.columns) > 1 else None
    earn_col = df.columns[2] if len(df.columns) > 2 else None
    cape_col = "CAPE" if "CAPE" in df.columns else (df.columns[10] if len(df.columns) > 10 else None)

    lookback = max(365, fp_settings.index_valuation_cn_lookback_days())
    min_date = date.today().toordinal() - lookback

    rows: list[dict[str, Any]] = []
    for rec in df.to_dict("records"):
        td = _shiller_row_date(rec.get(date_col))
        if not td or td.toordinal() < min_date:
            continue
        price = _opt_float(rec.get(price_col)) if price_col else None
        earn = _opt_float(rec.get(earn_col)) if earn_col else None
        pe_ttm = None
        if price is not None and earn is not None and earn != 0:
            pe_ttm = round(price / earn, 4)
        pe_cape = _opt_float(rec.get(cape_col)) if cape_col else None
        if pe_ttm is None and pe_cape is None:
            continue
        rows.append(
            {
                "trade_date": td.isoformat(),
                "region": "us",
                "index_code": _SHILLER_CODE,
                "index_name": "标普500",
                "source": "shiller",
                "pe_ttm": pe_ttm,
                "pe_static": None,
                "pe_cape": pe_cape,
                "index_close": price,
            }
        )
    if not rows:
        errors.append("shiller: no rows parsed")
    return rows, errors


def _shiller_row_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    # YYYY.MM e.g. 2024.01
    if "." in s:
        parts = s.split(".")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            y, m = int(parts[0]), int(parts[1])
            if 1 <= m <= 12:
                return date(y, m, 1)
    return _parse_trade_date(s)


def _upsert_rows(rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    now = _utc_now_iso()
    engine = get_engine()
    raw = engine.raw_connection()
    cur = raw.cursor()
    try:
        params = [
            (
                r["trade_date"],
                r["region"],
                r["index_code"],
                r["index_name"],
                r["source"],
                r.get("pe_ttm"),
                r.get("pe_static"),
                r.get("pe_cape"),
                r.get("index_close"),
                now,
            )
            for r in rows
        ]
        cur.executemany(
            """
            INSERT INTO index_valuation_daily (
              trade_date, region, index_code, index_name, source,
              pe_ttm, pe_static, pe_cape, index_close, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
              index_name = VALUES(index_name),
              source = VALUES(source),
              pe_ttm = VALUES(pe_ttm),
              pe_static = VALUES(pe_static),
              pe_cape = VALUES(pe_cape),
              index_close = VALUES(index_close),
              updated_at = VALUES(updated_at)
            """,
            params,
        )
        raw.commit()
        return len(params)
    except Exception:
        raw.rollback()
        raise
    finally:
        cur.close()
        raw.close()


def sync_index_valuation_daily(*, regions: Optional[list[str]] = None) -> dict[str, Any]:
    """Pull broad-index PE for cn / hk / us and upsert MySQL."""
    want = {x.strip().lower() for x in (regions or ["cn", "hk", "us"])}
    parts: dict[str, Any] = {}
    all_rows: list[dict[str, Any]] = []
    errors: list[str] = []

    if "cn" in want:
        cn_rows, cn_err = fetch_cn_index_pe_legu()
        all_rows.extend(cn_rows)
        parts["cn"] = len(cn_rows)
        errors.extend(cn_err)

    if "hk" in want:
        hk_rows, hk_err = fetch_yfinance_index_pe(_HK_YF, region="hk")
        all_rows.extend(hk_rows)
        parts["hk"] = len(hk_rows)
        errors.extend(hk_err)

    if "us" in want:
        us_hist, us_err = fetch_us_shiller_sp500()
        all_rows.extend(us_hist)
        us_spot, us_spot_err = fetch_yfinance_index_pe(_US_YF, region="us")
        all_rows.extend(us_spot)
        parts["us_shiller"] = len(us_hist)
        parts["us_spot"] = len(us_spot)
        errors.extend(us_err)
        errors.extend(us_spot_err)

    if not all_rows:
        err = "; ".join(errors[:8]) if errors else "no valuation rows"
        return {"ok": False, "error": err, "parts": parts}

    count = _upsert_rows(all_rows)
    logger.info("index_valuation_daily ok count=%s parts=%s warnings=%s", count, parts, len(errors))
    out: dict[str, Any] = {"ok": True, "count": count, "parts": parts}
    if errors:
        out["warnings"] = errors[:20]
    return out
