#!/usr/bin/env python3
"""Compare Qwen-Max (DashScope) with and without enable_search.

Usage (do not paste API keys into chat; use local .env):
  echo 'DASHSCOPE_API_KEY=sk-...' >> .env
  python examples/test_qwen_max_enable_search.py

Optional env:
  QWEN_MODEL=qwen-max          # default
  DASHSCOPE_BASE_URL=...       # default: compatible-mode endpoint
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QUESTION = (
    "请只根据你能查到的最新公开信息回答："
    "2026年6月1日当天，A股上证指数（000001.SH）收盘点位是多少？"
    "只给数字和简短说明；若无法联网获取实时行情，请明确写「无法联网获取最新数据」。"
)


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _extract_search_results(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Pull search hits from various DashScope response shapes."""
    hits: list[dict[str, Any]] = []

    search_info = data.get("search_info")
    if isinstance(search_info, dict):
        raw = search_info.get("search_results") or []
        if isinstance(raw, list):
            hits.extend(x for x in raw if isinstance(x, dict))

    output = data.get("output")
    if isinstance(output, dict):
        si = output.get("search_info")
        if isinstance(si, dict):
            raw = si.get("search_results") or []
            if isinstance(raw, list):
                hits.extend(x for x in raw if isinstance(x, dict))

    return hits


def _call(*, enable_search: bool | None) -> dict[str, Any]:
    key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not key:
        raise SystemExit(
            "Missing DASHSCOPE_API_KEY. Set it in the environment or project .env "
            "(see examples/test_qwen_max_enable_search.py header)."
        )

    model = os.environ.get("QWEN_MODEL", "qwen-max").strip() or "qwen-max"
    base = os.environ.get("DASHSCOPE_BASE_URL", DEFAULT_BASE).rstrip("/")
    url = f"{base}/chat/completions"

    body: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": QUESTION}],
        "max_tokens": 800,
        "temperature": 0.2,
    }
    label = "baseline (no enable_search)"
    if enable_search is True:
        body["enable_search"] = True
        # forced_search + agent 在 qwen-max 上可能触发 500；用 max 策略更稳
        body["search_options"] = {
            "enable_source": True,
            "search_strategy": "max",
        }
        label = "enable_search=true (enable_source, search_strategy=max)"

    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{label} HTTP {exc.code}: {err}") from exc

    if data.get("error"):
        raise SystemExit(f"{label} API error: {json.dumps(data['error'], ensure_ascii=False)}")

    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    content = (msg.get("content") or "").strip()
    search_hits = _extract_search_results(data)

    return {
        "label": label,
        "model": data.get("model") or model,
        "finish_reason": choice.get("finish_reason"),
        "content": content,
        "usage": data.get("usage"),
        "search_hit_count": len(search_hits),
        "search_titles": [h.get("title") for h in search_hits[:5] if h.get("title")],
        "top_level_keys": sorted(data.keys()),
    }


def _verdict(baseline: dict[str, Any], with_search: dict[str, Any]) -> str:
    if with_search["search_hit_count"] > 0:
        return (
            f"联网能力已启用：返回了 {with_search['search_hit_count']} 条 search_results "
            "(enable_source 生效)。"
        )

    a, b = baseline["content"], with_search["content"]
    refusal = ("无法联网", "无法获取", "知识截止", "没有实时", "不能联网")
    b_refuses = any(p in b for p in refusal)
    a_refuses = any(p in a for p in refusal)

    if with_search["search_hit_count"] == 0 and "enable_source" in with_search["label"]:
        if b_refuses and not a_refuses:
            return "两次回答不同，且开启搜索后更像在承认无法联网 — 请核对账号是否开通联网搜索。"
        if a == b:
            return (
                "两次回答完全相同，且未返回 search_results。"
                "可能 enable_search 未生效，或当前模型/协议不支持返回来源（可换 qwen3-max 再试）。"
            )
        if abs(len(a) - len(b)) > 80 or a[:120] != b[:120]:
            return (
                "两次回答明显不同，但未返回 search_results。"
                "人工核对开启搜索后的回答是否含具体点位/日期；"
                "若仍不确定，可在百炼控制台对比同一问题。"
            )
    return "请根据上方两次回答内容人工判断。"


def main() -> None:
    _load_dotenv()
    print("Model:", os.environ.get("QWEN_MODEL", "qwen-max"))
    print("Question:\n", QUESTION, "\n", sep="")

    results: list[dict[str, Any]] = []
    for flag in (None, True):
        print(f"--- {('Calling' if flag is None else 'Calling with enable_search')} ---")
        out = _call(enable_search=flag)
        results.append(out)
        print("label:", out["label"])
        print("model:", out["model"])
        print("finish_reason:", out["finish_reason"])
        print("usage:", out["usage"])
        print("search_hit_count:", out["search_hit_count"])
        if out["search_titles"]:
            print("search titles:", out["search_titles"])
        print("response keys:", out["top_level_keys"])
        print("content:\n", out["content"][:1400])
        if len(out["content"]) > 1400:
            print("...[truncated]")
        print()

    print("=== VERDICT ===")
    print(_verdict(results[0], results[1]))


if __name__ == "__main__":
    main()
