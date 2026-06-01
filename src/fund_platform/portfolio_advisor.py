"""Build portfolio context, call DashScope (web search), format daily fund brief."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any, Optional

DEFAULT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"

_SYSTEM = """你是一位公募基金与多市场策略分析师（券商研究部/基金投顾月报口径）。输出仅供个人研究参考，不构成任何投资建议或承诺收益。

数据规则：
- 必须先联网检索再写结论：指数行情、行业新闻、基金近期净值/涨跌幅、政策与事件；用户只提供持仓代码与名称，不提供行情数据。
- 查不到的数字或事实写「信息不足」，严禁编造点位、涨跌幅或新闻。

关键认知（务必照做，否则归因会变空话）：
- 用户持有的几乎都是【被动指数基金 / ETF联接 / QDII指数基金】。这类基金的涨跌≈其【跟踪指数】的涨跌（QDII 另有汇率与约1日时滞）。
- 因此「基金为什么涨/跌」= 先确定它【跟踪哪个指数】→ 搜【该指数】近1日/近1周/近1月的涨跌与驱动 → 再映射回基金。不要去搜「某只基金的净值表现」（通常搜不到，会得出"信息不足"）。
- 指数行情、成分行业、近期事件都可联网检索到；若连跟踪指数的近期表现都查不到，再写「信息不足」，但要先尝试用指数名检索。

分析方法论（按此思考，再落笔）：
- 先事实后观点：先给可检索到的硬数据（指数点位/涨跌幅、具体事件+日期）→ 再归因（宏观/行业景气/指数β/主题β/估值/资金面/汇率）→ 风险 → 机会。
- 风险与机会必须挂在【近期发生的具体事件或数据】上（如某政策、某经济数据、某财报、某价格变动），并尽量注明时间。严禁写「5G加速、国产替代、人口老龄化」这类常年成立、与时点无关的套话。
- 回答用户真正关心的：「为什么涨、为什么跌」「有什么风险、什么机会」。
- 时效优先：一切以分析基准日当天或最近一个已收盘交易日为准，优先使用最近 1～7 天的信息，避免引用一两周前的旧叙事当作"最新"。
- 同主题多只跟踪同一/相似指数的基金可合并成一段（须列出全部代码），但每只代码至少出现一次。
- 持仓外机会：说明与现有持仓是「补盲区」还是「替代/轮动」，避免与已重仓主题简单重复。

逻辑与文风：
- 因果链条清楚，前后不矛盾；不说「最该动」却建议维持。
- 语言专业、克制，少形容词堆砌；可用「驱动因素/压制因素/催化/扰动」等研究常用表述。
- 全文中文，分点清晰，适合手机阅读。"""


def _investor_style() -> str:
    return os.environ.get("FUND_ADVISOR_STYLE", "偏进攻").strip() or "偏进攻"


def _holding_horizon() -> str:
    return os.environ.get("FUND_ADVISOR_HORIZON", "3～12个月").strip() or "3～12个月"


def load_holdings_config(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("holdings") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        code = str(row.get("code", "")).strip()
        name = str(row.get("name", "")).strip()
        if len(code) == 6 and code.isdigit():
            out.append(
                {
                    "code": code,
                    "name": name,
                    **{k: v for k, v in row.items() if k not in ("code", "name")},
                }
            )
    return out


def _theme_hints_from_holdings(holdings: list[dict[str, Any]]) -> str:
    themes: list[str] = []
    seen: set[str] = set()
    for h in holdings:
        name = str(h.get("name") or "")
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
            if token in name and token not in seen:
                seen.add(token)
                themes.append(token)
    if themes:
        return "、".join(themes[:14])
    return "请根据下方持仓名称自行归纳"


def format_holdings_block(holdings: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for i, h in enumerate(holdings, 1):
        code = h["code"]
        name = h.get("name") or code
        parts = [f"{i}. {name} {code}"]
        if h.get("weight_pct") is not None:
            parts.append(f"持仓占比:{h['weight_pct']}%")
        if h.get("note"):
            parts.append(str(h["note"]))
        lines.append("；".join(parts))
    return "\n".join(lines)


def build_analysis_prompt(
    holdings: list[dict[str, Any]],
    *,
    as_of: Optional[date] = None,
) -> str:
    today = as_of or date.today()
    block = format_holdings_block(holdings)
    style = _investor_style()
    horizon = _holding_horizon()
    theme_hints = _theme_hints_from_holdings(holdings)
    codes_line = "、".join(h["code"] for h in holdings)
    return f"""分析基准日：{today.isoformat()}（以该日或最近一个已收盘交易日为准）
投资者偏好：{style}，持有周期 {horizon}

=== 我的持仓（仅清单，无行情）共 {len(holdings)} 只 ===
{block}
代码一览：{codes_line}
涉及主题方向（供分组参考）：{theme_hints}

=== 任务（须先联网搜索，再撰写）===

【一、市场环境】（约 200 字）
- A股：主要指数最新涨跌、市场风格（成长/价值、大小盘）。
- 港股：恒生指数及情绪。
- 全球：美股（标普/纳指等）、其他重要市场要点。
- 要闻：3～5 条影响股市的事件（附日期），与下文持仓分析要能挂钩。

【二、持仓涨跌归因】（核心，约 1000 字）
目标：说清楚每只（组）基金「为什么涨、为什么跌、有什么风险、有什么机会」，且必须有具体数据与近期事件支撑。
做法：把基金按跟踪指数/主题分组，建议分组：
   · A股主题（通信设备、卫星、电网设备、机器人、半导体材料设备、科创50、创业板等）
   · A股宽基/增强（沪深300增强等）
   · QDII·美股（标普500、纳斯达克100，多只可合并）
   · QDII·港股（恒生、港股创新药等）
每一只或每一组（须列出全部 6 位代码）按下面五行写：
   · 跟踪指数：写出该基金跟踪的指数名称（尽量含指数代码）；不确定就写最可能的并标注"待核实"。
   · 指数近期表现：联网给出该指数近 1 日/近 1 周（条件允许加近 1 月）的涨跌幅或点位，务必带数字；确实查不到才写「信息不足」。
   · 涨跌原因：结合本周/近期【具体事件或数据】解释指数及基金为何涨/跌，区分「跟随大盘β」还是「主题独立行情」；不要用与时点无关的产业套话。
   · 主要风险：1～2 条，须与近期事件/估值/资金/汇率等当前因素相关，并尽量给可观察的触发信号。
   · 主要机会：1～2 条，须与近期催化或数据相关。
注意：QDII（美股/港股）要点出汇率与跨时区时滞的影响；A股指数基金当日涨跌基本等于其跟踪指数当日涨跌，应据此给出方向。

【三、组合层面】（约 150 字）
- 整体涨跌格局一句话（相对 A股/港股/美股大盘）。
- 组合最大风险（集中度、市场、主题）。
- 组合最大机会。

【四、未持仓机会】（约 250 字，须联网）
- 列出 2～4 个「我还没买、但当前值得研究」的方向（如红利、债、黄金、其他行业/市场）。
- 每个：为什么现在有机会、与我现有持仓（{theme_hints}）的关系、可选公募代码+名称（真实产品，不确定只写方向）。
- 注明：观察池，非买入建议。

【五、小结与跟踪】（约 150 字）
- 3 条以内：接下来 1～2 周最值得盯的信号或数据。
- 若认为需要调整仓位，写清「加/减哪类主题」及逻辑，与第二节归因一致；若整体不动，说明原因。

全文不超过 2000 字；优先把第二节写透，避免空话和重复。"""


def call_qwen_analysis(user_prompt: str) -> tuple[str, dict[str, Any]]:
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Missing DASHSCOPE_API_KEY")

    model = os.environ.get("QWEN_MODEL", "qwen-max").strip() or "qwen-max"
    base = os.environ.get("DASHSCOPE_BASE_URL", DEFAULT_BASE).rstrip("/")
    max_tokens = int(os.environ.get("FUND_ADVISOR_MAX_TOKENS", "3200"))
    temperature = float(os.environ.get("FUND_ADVISOR_TEMPERATURE", "0.45"))
    enable_search = os.environ.get("FUND_ADVISOR_ENABLE_SEARCH", "1").strip().lower() not in (
        "0",
        "false",
        "no",
    )
    forced_search = os.environ.get("FUND_ADVISOR_FORCED_SEARCH", "1").strip().lower() not in (
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
        search_options: dict[str, Any] = {
            "enable_source": True,
            "search_strategy": os.environ.get("FUND_ADVISOR_SEARCH_STRATEGY", "max"),
        }
        if forced_search:
            search_options["forced_search"] = True
        body["enable_search"] = True
        body["search_options"] = search_options

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
