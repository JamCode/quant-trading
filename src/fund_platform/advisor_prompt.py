"""Build Chinese prompts for external AI (DeepSeek web + search)."""

from __future__ import annotations

from typing import Iterable, Optional

INDUSTRIES = ("新能源", "医药", "科技", "消费", "红利", "军工", "半导体")
FUND_TYPES = ("股票型", "混合型", "指数型", "债券型", "QDII")
STYLES = ("偏进攻", "偏稳健")
OBSERVATIONS = ("短期热点", "中长期配置")

_BASE = """你是一位公募基金研究助手。以下回答仅供研究参考，不构成任何投资建议。

请结合近期权威公开分析（券商观点、财经深度报道、基金季报公开摘要等），完成下列任务：
1. 先用 2～4 句话说明当前值得关注的板块或市场逻辑；
2. 再推荐 3～5 只值得关注的公募基金；
3. 每只基金须包含：6 位基金代码、基金全称、关注逻辑、主要风险（各一句）；
4. 文末列出你参考的公开来源标题（勿编造链接或虚构研报）。

默认任务：结合近期权威公开分析，推荐 3～5 只值得关注的公募基金，并说明推荐逻辑。"""


def tag_options() -> dict[str, tuple[str, ...]]:
    return {
        "industries": INDUSTRIES,
        "fund_types": FUND_TYPES,
        "styles": STYLES,
        "observations": OBSERVATIONS,
    }


def _join(values: Iterable[str]) -> str:
    parts = [v.strip() for v in values if v and str(v).strip()]
    return "、".join(parts)


def build_prompt(
    *,
    industries: Optional[Iterable[str]] = None,
    fund_types: Optional[Iterable[str]] = None,
    style: str = "",
    observation: str = "",
) -> str:
    lines = [_BASE.strip(), ""]
    ind = _join(industries or ())
    if ind:
        lines.append(f"重点关注行业/主题：{ind}")
    ft = _join(fund_types or ())
    if ft:
        lines.append(f"基金类型偏好：{ft}")
    st = (style or "").strip()
    if st:
        lines.append(f"风险风格：{st}")
    obs = (observation or "").strip()
    if obs:
        lines.append(f"观察周期倾向：{obs}")
    return "\n".join(lines).strip()
