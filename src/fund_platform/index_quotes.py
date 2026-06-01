"""Fetch live tracked-index quotes (akshare + East Money) for the daily brief.

The portfolio is almost all passive index/QDII funds, so a fund's daily move ≈
its tracked index. We fetch those index quotes here and feed them to the model,
instead of asking the model to web-search niche index returns (which it can't).

Network egress works on the ECS host; failures degrade gracefully (the model
then falls back to its own web search for missing indices).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# fund code -> tracked-index spec.
#   scope "cn":     match A-share index spot table by keywords (all must appear in 名称)
#   scope "global": match East Money global/HK spot by display name
_FUND_INDEX: dict[str, dict[str, Any]] = {
    "020899": {"index": "中证全指通信设备指数", "scope": "cn", "keywords": ["通信设备"]},
    "000071": {"index": "恒生指数", "scope": "global", "global_name": "恒生指数"},
    "025490": {"index": "中证卫星产业指数", "scope": "cn", "keywords": ["卫星"]},
    "110026": {"index": "创业板指", "scope": "cn", "keywords": ["创业板指"]},
    "010736": {"index": "沪深300", "scope": "cn", "keywords": ["沪深300"]},
    "019670": {"index": "港股通创新药指数", "scope": "cn", "keywords": ["创新药"]},
    "017641": {"index": "标普500", "scope": "global", "global_name": "标普500"},
    "025832": {"index": "中证电网设备主题指数", "scope": "cn", "keywords": ["电网设备"]},
    "020972": {"index": "中证机器人指数", "scope": "cn", "keywords": ["机器人"]},
    "013810": {"index": "上证科创板50成份指数", "scope": "cn", "keywords": ["科创50"]},
    "007722": {"index": "标普500", "scope": "global", "global_name": "标普500"},
    "018043": {"index": "纳斯达克100", "scope": "global", "global_name": "纳斯达克"},
    "019172": {"index": "纳斯达克100", "scope": "global", "global_name": "纳斯达克"},
    "023828": {"index": "中证半导体材料设备主题指数", "scope": "cn", "keywords": ["半导体材料"]},
    "016532": {"index": "纳斯达克100", "scope": "global", "global_name": "纳斯达克"},
}

_CN_SPOT_CATEGORIES = ("沪深重要指数", "上证系列指数", "中证系列指数")


def _to_float(value: Any) -> Optional[float]:
    try:
        if value in (None, "", "-"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _load_cn_spot() -> list[dict[str, Any]]:
    """All A-share index spot rows from the categories we need."""
    import akshare as ak

    rows: dict[str, dict[str, Any]] = {}
    for cat in _CN_SPOT_CATEGORIES:
        try:
            df = ak.stock_zh_index_spot_em(symbol=cat)
        except Exception as exc:  # noqa: BLE001
            logger.warning("stock_zh_index_spot_em(%s) failed: %s", cat, exc)
            continue
        for rec in df.to_dict("records"):
            name = str(rec.get("名称", "")).strip()
            code = str(rec.get("代码", "")).strip()
            if not name:
                continue
            rows.setdefault(
                code or name,
                {
                    "name": name,
                    "code": code,
                    "price": _to_float(rec.get("最新价")),
                    "pct": _to_float(rec.get("涨跌幅")),
                },
            )
    return list(rows.values())


def _match_cn(spot: list[dict[str, Any]], keywords: list[str]) -> Optional[dict[str, Any]]:
    cands = [r for r in spot if all(k in r["name"] for k in keywords)]
    if not cands:
        return None
    cands.sort(key=lambda r: len(r["name"]))
    return cands[0]


def _load_global() -> dict[str, dict[str, Any]]:
    from fund_platform.market_index import fetch_global_indices_em

    out: dict[str, dict[str, Any]] = {}
    try:
        for r in fetch_global_indices_em():
            name = str(r.get("name", "")).strip()
            if name:
                out[name] = {
                    "name": name,
                    "code": r.get("code"),
                    "price": r.get("last_price"),
                    "pct": r.get("change_pct"),
                }
    except Exception as exc:  # noqa: BLE001
        logger.warning("fetch_global_indices_em failed: %s", exc)
    return out


def fetch_index_quotes(codes: list[str]) -> dict[str, dict[str, Any]]:
    """Return fund_code -> {index, price, pct, matched_name} for known funds."""
    wanted = [c for c in codes if c in _FUND_INDEX]
    if not wanted:
        return {}

    need_cn = any(_FUND_INDEX[c]["scope"] == "cn" for c in wanted)
    need_global = any(_FUND_INDEX[c]["scope"] == "global" for c in wanted)
    cn_spot = _load_cn_spot() if need_cn else []
    global_spot = _load_global() if need_global else {}

    out: dict[str, dict[str, Any]] = {}
    for code in wanted:
        spec = _FUND_INDEX[code]
        if spec["scope"] == "cn":
            hit = _match_cn(cn_spot, spec["keywords"])
        else:
            hit = global_spot.get(spec["global_name"])
        if not hit:
            continue
        out[code] = {
            "index": spec["index"],
            "matched_name": hit.get("name"),
            "index_code": hit.get("code"),
            "price": hit.get("price"),
            "pct": hit.get("pct"),
        }
    return out


def format_index_quotes_block(
    holdings: list[dict[str, Any]],
    quotes: dict[str, dict[str, Any]],
) -> str:
    """Human-readable block: one line per fund with its tracked index quote."""
    if not quotes:
        return ""
    lines: list[str] = []
    for h in holdings:
        code = h["code"]
        q = quotes.get(code)
        if not q:
            continue
        name = h.get("name") or code
        pct = q.get("pct")
        price = q.get("price")
        pct_s = f"{pct:+.2f}%" if isinstance(pct, (int, float)) else "—"
        price_s = f"{price}" if price not in (None, "") else "—"
        idx = q.get("matched_name") or q.get("index") or ""
        lines.append(f"- {name}（{code}）→ {idx}：最新 {price_s}，涨跌 {pct_s}")
    return "\n".join(lines)
