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

_SYSTEM = """你是犀利的公募基金组合分析助手。输出仅供个人研究参考，不构成任何投资建议、承诺收益或具体买卖指令。

数据规则（重要）：
- 行情、指数点位、基金净值/涨跌幅、新闻与时事，一律通过联网搜索获取最新公开信息；用户不会提供本地数据库或行情快照。
- 无可靠检索结果时写「信息不足」，勿凭记忆编造数字或新闻标题。

写作要求：
- 观点明确、有主次，避免和稀泥；允许偏多/偏空/结构性分化，但须说明主逻辑。
- 禁止：对每只基金都给同样强度的「需关注」；只说「观望」却不写触发条件；用「可能」「或许」「需密切关注」敷衍带过（可保留一处必要的不确定性说明）。

逻辑自洽（必须遵守）：
- 各小节角色不同，禁止张冠李戴：说「行动」就不能写「维持」；说「维持」应放在【调仓建议】整体层面。
- 前后不得矛盾：【总观点】偏多则不宜全文皆减仓；【最担心】与【建议减仓】应呼应；同一只基金不能既「首选加仓」又「首选减仓」。
- 三个角色互斥：「最看好」= 中长期逻辑最顺；「最担心」= 短期风险最大；「建议加仓/减仓」= 本周最值得执行的具体动作（二选一各 1 只，或明确写「本周无加仓标的」/「本周无减仓标的」）。
- 若某只基金无需调整，不要把它放进加仓/减仓行；整体「先不动」写在【调仓建议】并给触发条件。

回答须包含「今日市场与要闻」：覆盖 A 股、港股、全球主要股市，并提炼当日或最近一个交易日的重大新闻。

请用简洁中文、分点作答。"""


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
    return f"""日期：{today.isoformat()}（分析请以该日或最近一个交易日的市场为准）
投资风格：{style}；持有周期：{horizon}

说明：下列仅为我的持仓清单（代码+名称），不含任何行情或净值数据。请必须通过联网搜索获取全部市场与基金信息，不要使用假设或过时数据。

我的持仓共 {len(holdings)} 只（未提供份额时按等权理解结构，勿编造持仓金额）：
{block}

请严格按下列结构回答（全文 1300 字以内）：

【今日市场与要闻】（须联网）
- A股：2～4 句，写明上证/深证/创业板/沪深300等最新涨跌与风格（成长 vs 价值、大小盘），尽量带具体点位或涨跌幅；
- 港股：1～3 句，恒生指数及整体情绪，带最新点位或涨跌幅；
- 全球：1～3 句，美股（标普500、纳斯达克、道琼斯等）及日经等主要市场要点，带最新涨跌；
- 重大新闻：2～5 条与股市相关的要闻（政策、宏观数据、行业、地缘等），每条标题式一句话并注明日期；查不到则写「信息不足」。

【总观点】
1 句话：对当前组合整体偏多 / 偏空 / 结构性分化；主驱动 1 个。

【结构体检】
- 市场暴露：A股 / 港股 / 美股 / QDII 是否失衡？最突出的 1 个问题；
- 主题暴露：结合持仓方向（{theme_hints}），是否同质过高、哪条链条最拥挤；
- 可联网核对持仓基金近 1 周表现（无需逐只罗列，只写与结论相关的）。

【关键基金与行动】（均从上方持仓选，写明 6 位代码；四行逻辑递进，勿重复堆砌）
- 最看好：1 只 — 中长期为何仍值得持有或加码 + 最大风险（各 1 句）
- 最担心：1 只 — 短期为何风险最高 + 出现何种信号应减配（1 句）
- 建议加仓：1 只 — 动作只能是「加仓/定投」；写清理由（1～2 句）。若无合适标的，写「无」并说明
- 建议减仓：1 只 — 动作只能是「减仓/止盈」；写清理由（1～2 句）。若无合适标的，写「无」并说明
（禁止在「建议加仓/减仓」行写「维持」「观望」；整体维持写在下一节）

【调仓建议】（须与上一节一致，不得打架）
- 组合层面：明确写「加仓___ / 减仓___ / 整体维持」；若整体维持，解释与「建议加仓/减仓」如何并存（例如仅结构性微调）
- 板块层面：对应加仓/减仓哪些主题
- 触发条件：若本周不大幅调整，给 1 条可量化或半量化条件（什么情况下再动）

【持仓外关注】
- 2～4 个当前未持有、但值得关注的方向；各 1 句理由 + 可选基金代码（真实产品，不确定则只写方向）
- 标注：观察池，不构成买入建议

【与风格匹配】
结合「{style}、{horizon}」评价建议是否够果断；若偏保守请直说。"""


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
