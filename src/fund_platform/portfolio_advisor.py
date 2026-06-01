"""Build portfolio context, call DashScope, format daily fund brief."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pymysql.cursors

from fund_platform import queries

DEFAULT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

_SYSTEM = """你是犀利的公募基金组合分析助手。输出仅供个人研究参考，不构成任何投资建议、承诺收益或具体买卖指令。

写作要求：
- 观点明确、有主次，避免和稀泥；允许偏多/偏空/结构性分化，但须说明主逻辑。
- 所有判断须对应用户持仓、提供的净值/收益快照，或联网检索到的近期公开信息；无依据则写「信息不足」，勿空泛堆砌。
- 禁止：对每只基金都给同样强度的「需关注」；只说「观望」却不写触发条件；用「可能」「或许」「需密切关注」敷衍带过（可保留一处必要的不确定性说明）。

回答须包含「今日市场与要闻」：覆盖 A 股、港股、全球主要股市，并提炼当日或前一交易日重大新闻标题级要点（可联网，勿编造）。

请用简洁中文、分点作答。"""

# (code, display label) for local DB snapshot; model still web-searches for news.
_MARKET_WATCH: list[tuple[str, str]] = [
    ("000001", "A股·上证指数"),
    ("399001", "A股·深证成指"),
    ("399006", "A股·创业板指"),
    ("000300", "A股·沪深300"),
    ("000688", "A股·科创50"),
    ("HSI", "港股·恒生指数"),
    ("SPX", "全球·标普500"),
    ("NDX", "全球·纳斯达克100"),
    ("DJIA", "全球·道琼斯"),
]


def _investor_style() -> str:
    return os.environ.get("FUND_ADVISOR_STYLE", "偏进攻").strip() or "偏进攻"


def _holding_horizon() -> str:
    return os.environ.get("FUND_ADVISOR_HORIZON", "3～12个月").strip() or "3～12个月"


def _theme_hints_for_prompt(
    holdings: list[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
) -> str:
    """Infer theme/industry labels from DB exposure or fund names (no hardcoded list)."""
    themes: list[str] = []
    seen: set[str] = set()

    def _add(label: str) -> None:
        label = label.strip()
        if label and label not in seen:
            seen.add(label)
            themes.append(label)

    for h in holdings:
        snap = snapshots.get(h["code"]) or {}
        for raw in snap.get("top_industries") or []:
            _add(str(raw).split("(")[0].strip())
        name = str(h.get("name") or snap.get("short_name") or "")
        for token in (
            "通信",
            "卫星",
            "电网",
            "机器人",
            "半导体",
            "创新药",
            "恒生",
            "创业板",
            "沪深300",
            "科创50",
            "标普500",
            "纳斯达克",
            "QDII",
            "港股",
            "美股",
            "材料",
            "设备",
        ):
            if token in name:
                _add(token)

    if themes:
        return "、".join(themes[:14])
    return "请根据下方持仓名称与类型自行归纳"


def load_holdings_config(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("holdings") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        code = str(row.get("code", "")).strip()
        name = str(row.get("name", "")).strip()
        if len(code) == 6 and code.isdigit():
            out.append({"code": code, "name": name, **{k: v for k, v in row.items() if k not in ("code", "name")}})
    return out


def _cursor(conn):
    return conn.cursor(pymysql.cursors.DictCursor)


def fetch_snapshots(conn, codes: list[str]) -> dict[str, dict[str, Any]]:
    """Fund catalog row + metrics + top industries per code."""
    if not codes:
        return {}
    cur = _cursor(conn)
    placeholders = ", ".join(["%s"] * len(codes))
    cur.execute(
        f"""
        SELECT
          f.code,
          f.short_name,
          f.fund_type,
          f.nav_date,
          f.nav_unit,
          f.daily_pct,
          m.return_1m,
          m.return_3m,
          m.return_1y,
          m.rank_in_type
        FROM funds f
        LEFT JOIN fund_metrics m ON m.fund_code = f.code
        WHERE f.code IN ({placeholders})
        """,
        codes,
    )
    out: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        code = str(row["code"])
        out[code] = {k: queries._jsonable(v) for k, v in dict(row).items()}

    cur.execute("SELECT MAX(report_date) AS rd FROM fund_industry_exposure")
    rd_row = cur.fetchone()
    report_date = rd_row.get("rd") if rd_row else None
    if report_date:
        cur.execute(
            f"""
            SELECT fund_code, industry, weight_pct
            FROM fund_industry_exposure
            WHERE fund_code IN ({placeholders}) AND report_date = %s
            ORDER BY fund_code, weight_pct DESC
            """,
            [*codes, report_date],
        )
        ind_map: dict[str, list[str]] = {}
        for row in cur.fetchall():
            fc = str(row["fund_code"])
            label = f"{row['industry']}({row['weight_pct']}%)"
            ind_map.setdefault(fc, []).append(label)
        for code, labels in ind_map.items():
            if code in out:
                out[code]["top_industries"] = labels[:3]
    return out


def format_holdings_block(
    holdings: list[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
) -> str:
    lines: list[str] = []
    for i, h in enumerate(holdings, 1):
        code = h["code"]
        name = h.get("name") or code
        snap = snapshots.get(code) or {}
        catalog_name = snap.get("short_name")
        if catalog_name and catalog_name != name:
            name = f"{name}（名录:{catalog_name}）"
        parts = [f"{i}. {name} {code}"]
        if snap.get("fund_type"):
            parts.append(f"类型:{snap['fund_type']}")
        if snap.get("nav_date"):
            nav_bits = [f"净值日:{snap['nav_date']}"]
            if snap.get("nav_unit"):
                nav_bits.append(f"单位净值:{snap['nav_unit']}")
            if snap.get("daily_pct") not in (None, ""):
                nav_bits.append(f"日涨跌:{snap['daily_pct']}%")
            parts.append("，".join(nav_bits))
        rets = []
        for key, label in (("return_1m", "1月"), ("return_3m", "3月"), ("return_1y", "1年")):
            if snap.get(key) not in (None, ""):
                rets.append(f"{label}{snap[key]}%")
        if rets:
            parts.append("收益:" + "/".join(rets))
        if snap.get("rank_in_type"):
            parts.append(f"同类排名:{snap['rank_in_type']}")
        if snap.get("top_industries"):
            parts.append("行业暴露:" + "、".join(snap["top_industries"]))
        if h.get("weight_pct") is not None:
            parts.append(f"持仓占比:{h['weight_pct']}%")
        if h.get("note"):
            parts.append(str(h["note"]))
        lines.append("；".join(parts))
    return "\n".join(lines)


def _format_index_snapshot_line(label: str, snap: dict[str, Any]) -> str:
    td = str(snap.get("trade_date") or "")[:10]
    live = bool(snap.get("live"))
    phase = "盘中" if live else "收盘"
    px = snap.get("close_px") if snap.get("close_px") is not None else snap.get("last_price")
    pct = snap.get("change_pct")
    bits = [f"- {label}："]
    if px is not None:
        bits.append(str(px))
    if pct is not None and pct != "":
        try:
            bits.append(f" ({float(pct):+.2f}%)")
        except (TypeError, ValueError):
            bits.append(f" ({pct}%)")
    if td:
        bits.append(f" [{td} {phase}]")
    return "".join(bits)


def fetch_market_context_block(conn) -> str:
    """Latest index levels from MySQL (intraday when available)."""
    from fund_platform.market_index_queries import query_market_index_snapshot

    lines: list[str] = []
    for code, label in _MARKET_WATCH:
        try:
            snap = query_market_index_snapshot(conn, code, live=True)
        except Exception:
            snap = None
        if snap:
            lines.append(_format_index_snapshot_line(label, snap))
        else:
            lines.append(f"- {label}：库内暂无快照")
    return "\n".join(lines)


def build_analysis_prompt(
    holdings: list[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
    *,
    market_block: str = "",
    as_of: Optional[date] = None,
) -> str:
    today = as_of or date.today()
    block = format_holdings_block(holdings, snapshots)
    style = _investor_style()
    horizon = _holding_horizon()
    theme_hints = _theme_hints_for_prompt(holdings, snapshots)
    market_section = ""
    if market_block.strip():
        market_section = f"""
本地指数快照（供交叉验证；若与联网数据冲突，以联网当日信息为准）：
{market_block.strip()}
"""
    return f"""日期：{today.isoformat()}
投资风格：{style}；持有周期：{horizon}
{market_section}
我的持仓共 {len(holdings)} 只（未提供份额时按等权理解结构，勿编造金额或收益率）：
{block}

请严格按下列结构回答（全文 1300 字以内；须结合联网搜索，体现当日或最近一个交易日行情与新闻）：

【今日市场与要闻】
- A股：用 2～4 句概括主要指数涨跌、量能/风格特征（成长 vs 价值、大小盘等）；
- 港股：1～3 句概括恒生指数及港股整体情绪；
- 全球：1～3 句概括美股（标普/纳指等）、其他重要市场（如日经）要点；
- 重大新闻：列出 2～5 条与股市相关的要闻（政策、宏观数据、行业事件、地缘政治等），每条「标题式一句话」，注明大致日期；不确定的写「信息不足」勿编造。

【总观点】
用 1 句话给出对「当前组合」的整体立场：偏多 / 偏空 / 结构性分化；主驱动因素只写 1 个。

【结构体检】
- 市场暴露：A股 / 港股 / 美股 / QDII 是否失衡？最突出的 1 个问题是什么？
- 主题暴露：结合持仓涉及的方向（{theme_hints}），是否同质过高、哪条链条最拥挤？

【三只关键基金】（必须从上方持仓中选，写明 6 位代码）
- 最看好：1 只 — 看多逻辑 + 最大风险（各 1 句）
- 最担心：1 只 — 看空或回避逻辑 + 出现什么信号应考虑减配（1 句）
- 最该动：1 只 — 建议动作（加仓/减仓/维持）+ 理由（各 1 句）

【调仓建议】
- 板块层面：明确写「加仓___ / 减仓___ / 维持___」（至少各选一类，可合并同类）
- 若建议暂不大动：给出 1 条可量化或半量化的触发条件（例如指数/板块/净值回撤阈值）

【持仓外关注】
- 列出 2～4 个「当前组合未覆盖、但值得现在关注」的方向（行业/主题/市场，如红利、债券、黄金、某国指数等）；
- 每个方向：为什么现在值得关注（1 句）+ 可选的代表性公募基金 6 位代码与全称（须为真实存续产品，勿编造；不确定则只写方向不写代码）；
- 明确标注：以上不在我当前持仓内，仅为观察池，不构成买入建议。

【与风格匹配】
结合「{style}、{horizon}」评价上述建议是否够果断；若仍偏保守，直说原因。"""


def call_qwen_analysis(user_prompt: str) -> tuple[str, dict[str, Any]]:
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Missing DASHSCOPE_API_KEY")

    model = os.environ.get("QWEN_MODEL", "qwen-max").strip() or "qwen-max"
    base = os.environ.get("DASHSCOPE_BASE_URL", DEFAULT_BASE).rstrip("/")
    max_tokens = int(os.environ.get("FUND_ADVISOR_MAX_TOKENS", "1800"))
    temperature = float(os.environ.get("FUND_ADVISOR_TEMPERATURE", "0.5"))
    enable_search = os.environ.get("FUND_ADVISOR_ENABLE_SEARCH", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )

    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if enable_search:
        body["enable_search"] = True
        body["search_options"] = {
            "enable_source": True,
            "search_strategy": os.environ.get("FUND_ADVISOR_SEARCH_STRATEGY", "max"),
        }

    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"DashScope HTTP {exc.code}: {err}") from exc

    if data.get("error"):
        raise RuntimeError(json.dumps(data["error"], ensure_ascii=False))

    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content") or ""
    return content.strip(), data.get("usage") or {}


def format_dingtalk_message(analysis: str, *, as_of: Optional[date] = None) -> str:
    today = as_of or date.today()
    return f"【基金日报 {today.isoformat()}】\n\n{analysis.strip()}\n\n— 仅供参考，不构成投资建议"
