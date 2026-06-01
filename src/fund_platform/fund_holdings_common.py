"""Shared parsing for fund stock holdings rows (A-share + global)."""

from __future__ import annotations

from typing import Any, Optional


def parse_weight_pct(value: Any) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip().replace(",", "").replace("%", "")
    if not s or s in ("-", "--", "nan"):
        return None
    try:
        return round(float(s), 4)
    except ValueError:
        return None


def normalize_stock_code(value: Any) -> str:
    s = str(value or "").strip().upper()
    if not s:
        return ""
    if s.isdigit():
        # A-share 6-digit; 5-digit HK (00700) must not zfill to 007000
        if len(s) >= 5:
            return s
        return s.zfill(6)
    return s


def normalize_stock_name(value: Any) -> str:
    return str(value or "").strip()


def dedupe_holdings_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per stock_code; keep the row with the highest weight_pct when duplicated."""
    by_code: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("stock_code") or "").strip()
        if not code:
            continue
        prev = by_code.get(code)
        if prev is None:
            by_code[code] = row
            continue
        w_new = row.get("weight_pct")
        w_old = prev.get("weight_pct")
        if w_new is None and w_old is None:
            by_code[code] = row
        elif w_old is None:
            by_code[code] = row
        elif w_new is None:
            pass
        elif float(w_new) >= float(w_old):
            by_code[code] = row
    return list(by_code.values())


def row_from_em_record(rec: dict[str, Any]) -> Optional[dict[str, Any]]:
    code = normalize_stock_code(rec.get("股票代码", rec.get("代码", "")))
    name = normalize_stock_name(rec.get("股票名称", rec.get("名称", "")))
    if not code and not name:
        return None
    if not code:
        code = name[:32]
    w = parse_weight_pct(
        rec.get("占净值比例") or rec.get("持仓占比") or rec.get("占净值比例(%)")
    )
    return {"stock_code": code, "stock_name": name, "weight_pct": w}


def rows_from_holdings_payload(holdings: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows from fund_details / fetch_holdings_bundle JSON."""
    out: list[dict[str, Any]] = []
    for rec in holdings.get("stocks") or []:
        if not isinstance(rec, dict):
            continue
        code = normalize_stock_code(rec.get("股票代码", rec.get("代码", "")))
        name = normalize_stock_name(rec.get("股票名称", rec.get("名称", "")))
        if not code and not name:
            continue
        if not code:
            code = name[:32]
        w = parse_weight_pct(rec.get("占净值比例") or rec.get("持仓占比"))
        out.append({"stock_code": code, "stock_name": name, "weight_pct": w})
    return out


def report_date_from_holdings(holdings: dict[str, Any]) -> str:
    q = str(holdings.get("stock_quarter") or "").strip()
    if q:
        return q
    y = holdings.get("stock_year_used")
    if y:
        return f"{y}年"
    return "unknown"
