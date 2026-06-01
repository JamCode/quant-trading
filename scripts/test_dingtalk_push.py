#!/usr/bin/env python3
"""Send a test message to a DingTalk custom robot (加签).

Add to project root .env (do not commit):
  DINGTALK_WEBHOOK_URL=https://oapi.dingtalk.com/robot/send?access_token=...
  DINGTALK_SECRET=SEC...

Usage:
  python3 scripts/test_dingtalk_push.py
  python3 scripts/test_dingtalk_push.py "自定义测试内容"
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fund_platform.dingtalk_notify import send_text  # noqa: E402
from fund_platform.dotenv_util import load_dotenv  # noqa: E402


def main() -> None:
    load_dotenv(ROOT / ".env")
    webhook = os.environ.get("DINGTALK_WEBHOOK_URL", "").strip()
    secret = os.environ.get("DINGTALK_SECRET", "").strip()
    if not webhook or not secret:
        raise SystemExit(
            "请在项目根目录 .env 中配置 DINGTALK_WEBHOOK_URL 和 DINGTALK_SECRET"
        )

    content = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "【基金日报】钉钉加签测试：若你看到这条，说明推送已配置成功。"
    )
    try:
        result = send_text(webhook=webhook, secret=secret, content=content)
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code}: {err}") from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("errcode") == 0:
        print("OK — 请到钉钉群里查看消息。")
    else:
        raise SystemExit(f"钉钉返回错误: {result}")


if __name__ == "__main__":
    main()
