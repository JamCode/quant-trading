"""Fund holdings from East Money + asset mix from Xueqiu (AkShare)."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _quarter_sort_key(label: str) -> tuple[int, int]:
    m = re.search(r"(\d{4})年(\d)季度", str(label))
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (0, 0)


def _latest_quarter_label(df: pd.DataFrame, col: str = "季度") -> Optional[str]:
    if df is None or df.empty or col not in df.columns:
        return None
    labels = [str(x) for x in df[col].dropna().unique().tolist() if str(x).strip()]
    if not labels:
        return None
    return max(labels, key=_quarter_sort_key)


def _records_clean(df: pd.DataFrame) -> list[dict[str, str]]:
    df = df.fillna("")
    out: list[dict[str, str]] = []
    for rec in df.to_dict("records"):
        row: dict[str, str] = {}
        for k, v in rec.items():
            row[str(k)] = "" if v == "" else str(v).strip()
        out.append(row)
    return out


def fetch_holdings_bundle(symbol: str) -> dict[str, Any]:
    import akshare as ak

    sym = symbol.strip()
    now_y = datetime.now().year

    out: dict[str, Any] = {
        "stock_year_used": None,
        "bond_year_used": None,
        "stock_quarter": None,
        "bond_quarter": None,
        "stocks": [],
        "bonds": [],
        "asset_mix": [],
        "warnings": [],
    }

    try:
        df_mix = ak.fund_individual_detail_hold_xq(symbol=sym)
        if df_mix is not None and not df_mix.empty:
            out["asset_mix"] = _records_clean(df_mix)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Asset mix fetch failed %s: %s", sym, exc)
        out["warnings"].append(f"资产配置:{exc}")

    for y in (now_y, now_y - 1):
        try:
            df_s = ak.fund_portfolio_hold_em(symbol=sym, date=str(y))
            if df_s is None or df_s.empty:
                continue
            q = _latest_quarter_label(df_s)
            if not q:
                continue
            sub = df_s[df_s["季度"].astype(str) == q].copy()
            if sub.empty:
                continue
            out["stock_year_used"] = y
            out["stock_quarter"] = q
            out["stocks"] = _records_clean(sub)
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("Stock holdings %s %s: %s", sym, y, exc)
            out["warnings"].append(f"股票持仓{y}:{exc}")

    for y in (now_y, now_y - 1):
        try:
            df_b = ak.fund_portfolio_bond_hold_em(symbol=sym, date=str(y))
            if df_b is None or df_b.empty:
                continue
            q = _latest_quarter_label(df_b)
            if not q:
                continue
            sub = df_b[df_b["季度"].astype(str) == q].copy()
            if sub.empty:
                continue
            out["bond_year_used"] = y
            out["bond_quarter"] = q
            out["bonds"] = _records_clean(sub)
            break
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bond holdings %s %s: %s", sym, y, exc)
            out["warnings"].append(f"债券持仓{y}:{exc}")

    return out
