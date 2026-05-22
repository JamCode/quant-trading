"""Normalize AkShare ``fund_open_fund_daily_em`` columns."""

from __future__ import annotations

import re

import pandas as pd


def normalize_open_fund_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize dynamic-date columns from ``fund_open_fund_daily_em``."""
    df = df.copy()
    df["code"] = df["基金代码"].astype(str).str.strip()
    df = df.drop_duplicates(subset=["code"], keep="first")

    cols = list(df.columns)
    nav_dates: list[tuple[str, str]] = []
    acc_dates: list[tuple[str, str]] = []
    pat_nav = re.compile(r"^(\d{4}-\d{2}-\d{2})-单位净值$")
    pat_acc = re.compile(r"^(\d{4}-\d{2}-\d{2})-累计净值$")
    for c in cols:
        cs = str(c)
        m = pat_nav.match(cs)
        if m:
            nav_dates.append((m.group(1), cs))
        m2 = pat_acc.match(cs)
        if m2:
            acc_dates.append((m2.group(1), cs))
    nav_dates.sort(key=lambda x: x[0], reverse=True)
    acc_dates.sort(key=lambda x: x[0], reverse=True)

    out = pd.DataFrame({"code": df["code"]})
    if nav_dates:
        nav_date, col_nav = nav_dates[0]
        out["nav_date"] = nav_date
        out["nav_unit"] = df[col_nav].fillna("").astype(str).str.strip()
        if len(nav_dates) > 1:
            _, col_prev = nav_dates[1]
            out["prev_nav_unit"] = df[col_prev].fillna("").astype(str).str.strip()
        else:
            out["prev_nav_unit"] = ""
    else:
        out["nav_date"] = ""
        out["nav_unit"] = ""
        out["prev_nav_unit"] = ""

    if acc_dates:
        _, col_a = acc_dates[0]
        out["nav_acc"] = df[col_a].fillna("").astype(str).str.strip()
        if len(acc_dates) > 1:
            _, col_a2 = acc_dates[1]
            out["prev_nav_acc"] = df[col_a2].fillna("").astype(str).str.strip()
        else:
            out["prev_nav_acc"] = ""
    else:
        out["nav_acc"] = ""
        out["prev_nav_acc"] = ""

    stable_map = {
        "daily_change": "日增长值",
        "daily_pct": "日增长率",
        "subscribe_status": "申购状态",
        "redeem_status": "赎回状态",
        "fee_note": "手续费",
    }
    for en, zh in stable_map.items():
        if zh in df.columns:
            out[en] = df[zh].fillna("").astype(str).str.strip()
        else:
            out[en] = ""

    return out
