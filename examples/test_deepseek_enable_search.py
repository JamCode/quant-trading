#!/usr/bin/env python3
"""Compare DeepSeek chat/completions with and without enable_search.

Usage (do not commit API keys):
  echo 'DEEPSEEK_API_KEY=sk-...' >> .env   # project root, gitignored
  python examples/test_deepseek_enable_search.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTION = (
    "请只根据你能查到的最新公开信息回答："
    "2026年5月最近一周，A股新能源板块有哪些机构观点或财经报道标题？"
    "列出至少3条，每条必须带可核查的来源标题；若无法联网请明确说无法获取最新网页。"
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


def _call(*, enable_search: bool | None) -> dict:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key:
        raise SystemExit("Missing DEEPSEEK_API_KEY in environment or .env")

    body: dict = {
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-chat"),
        "messages": [{"role": "user", "content": QUESTION}],
        "max_tokens": 800,
        "temperature": 0.3,
    }
    label = "baseline"
    if enable_search is True:
        body["enable_search"] = True
        label = "enable_search=true"
    elif enable_search is False:
        body["enable_search"] = False
        label = "enable_search=false"

    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{label} HTTP {exc.code}: {err}") from exc

    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return {
        "label": label,
        "model": data.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "content": (msg.get("content") or "").strip(),
        "usage": data.get("usage"),
        "raw_keys": sorted(data.keys()),
    }


def main() -> None:
    _load_dotenv()
    print("Question:", QUESTION, "\n", sep="\n")
    results = []
    for flag in (None, True):
        print(f"--- Calling ({'no enable_search' if flag is None else 'enable_search=true'}) ---")
        out = _call(enable_search=flag)
        results.append(out)
        print("model:", out["model"])
        print("finish_reason:", out["finish_reason"])
        print("usage:", out["usage"])
        print("content preview:\n", out["content"][:1200])
        if len(out["content"]) > 1200:
            print("...[truncated]")
        print()

    a, b = results[0]["content"], results[1]["content"]
    if a == b:
        print("VERDICT: 两次回答完全相同 → enable_search 很可能未生效或被忽略")
    elif abs(len(a) - len(b)) < 50 and a[:200] == b[:200]:
        print("VERDICT: 回答高度相似 → enable_search 可能未带来实质联网差异")
    else:
        print("VERDICT: 两次回答明显不同 → 请人工看是否 enable_search 带来了更新/来源")


if __name__ == "__main__":
    main()
