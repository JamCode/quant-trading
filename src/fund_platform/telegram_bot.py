"""Telegram long-polling bot for lightweight ECS operations."""

from __future__ import annotations

import argparse
import logging
import os
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


LOG = logging.getLogger("fund_platform.telegram_bot")
REPO_ROOT = Path(os.environ.get("TELEGRAM_BOT_REPO", Path.cwd())).resolve()
MAX_REPLY_CHARS = 3500


@dataclass(frozen=True)
class Config:
    token: str
    allowed_chat_ids: set[str]
    allow_shell: bool
    poll_timeout: int
    command_timeout: int


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_config() -> Config:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
    raw_ids = os.environ.get("TELEGRAM_ALLOWED_CHAT_IDS", "").strip()
    allowed = {item.strip() for item in raw_ids.split(",") if item.strip()}
    return Config(
        token=token,
        allowed_chat_ids=allowed,
        allow_shell=_truthy(os.environ.get("TELEGRAM_ALLOW_SHELL", "0")),
        poll_timeout=max(5, int(os.environ.get("TELEGRAM_POLL_TIMEOUT", "50"))),
        command_timeout=max(5, int(os.environ.get("TELEGRAM_COMMAND_TIMEOUT", "180"))),
    )


class TelegramBot:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.api = f"https://api.telegram.org/bot{config.token}"
        self.session = requests.Session()

    def request(self, method: str, **payload: Any) -> dict[str, Any]:
        resp = self.session.post(f"{self.api}/{method}", json=payload, timeout=70)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(f"Telegram API {method} failed: {data}")
        return data

    def send_message(self, chat_id: str, text: str) -> None:
        text = text.strip() or "(empty)"
        for start in range(0, len(text), MAX_REPLY_CHARS):
            self.request(
                "sendMessage",
                chat_id=chat_id,
                text=text[start : start + MAX_REPLY_CHARS],
                disable_web_page_preview=True,
            )

    def get_updates(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {
            "timeout": self.config.poll_timeout,
            "allowed_updates": ["message"],
        }
        if offset is not None:
            payload["offset"] = offset
        return self.request("getUpdates", **payload).get("result", [])


def run_command(args: list[str], timeout: int) -> str:
    LOG.info("running command: %s", shlex.join(args))
    proc = subprocess.run(
        args,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    output = proc.stdout.strip()
    if proc.returncode:
        return f"$ {shlex.join(args)}\nexit={proc.returncode}\n{output}"
    return output or f"$ {shlex.join(args)}\nok"


def run_shell(command: str, timeout: int) -> str:
    LOG.info("running shell: %s", command)
    proc = subprocess.run(
        ["bash", "-lc", command],
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    output = proc.stdout.strip()
    if proc.returncode:
        return f"$ {command}\nexit={proc.returncode}\n{output}"
    return output or f"$ {command}\nok"


def help_text(config: Config, chat_id: str) -> str:
    shell_state = "on" if config.allow_shell else "off"
    allowed_state = "configured" if config.allowed_chat_ids else "not configured"
    return "\n".join(
        [
            "quant-trading Telegram bot",
            f"chat_id: {chat_id}",
            f"allowed_chat_ids: {allowed_state}",
            f"shell: {shell_state}",
            "",
            "/status - 服务状态与健康检查",
            "/health - FastAPI health check",
            "/logs [service] - 最近 80 行 journal 日志",
            "/deploy - git pull、安装依赖、重启服务",
            "/run <cmd> - 执行 shell 命令（仅 TELEGRAM_ALLOW_SHELL=1 时可用）",
        ]
    )


def service_name(raw: str) -> str:
    allowed = {
        "web": "quant-trading-fund-web.service",
        "crawler": "quant-trading-fund-crawler.service",
        "advisor": "quant-trading-fund-advisor.service",
        "telegram": "quant-trading-telegram-bot.service",
    }
    return allowed.get(raw.strip().lower() or "telegram", "quant-trading-telegram-bot.service")


def handle_command(config: Config, chat_id: str, text: str) -> str:
    cmd, _, rest = text.strip().partition(" ")
    cmd = cmd.split("@", 1)[0].lower()
    if cmd in {"/start", "/help"}:
        return help_text(config, chat_id)
    if not config.allowed_chat_ids:
        return (
            f"当前未配置 TELEGRAM_ALLOWED_CHAT_IDS，拒绝执行命令。\n"
            f"请把这个 chat_id 加入环境变量后重启服务: {chat_id}"
        )
    if chat_id not in config.allowed_chat_ids:
        return f"未授权 chat_id: {chat_id}"
    if cmd == "/health":
        return run_command(["curl", "-sf", "http://127.0.0.1:8010/health"], config.command_timeout)
    if cmd == "/status":
        return run_shell(
            "curl -sf http://127.0.0.1:8010/health || true; "
            "systemctl --user --no-pager --full status "
            "quant-trading-fund-web.service "
            "quant-trading-fund-crawler.service "
            "quant-trading-telegram-bot.service",
            config.command_timeout,
        )
    if cmd == "/logs":
        return run_command(
            [
                "journalctl",
                "--user",
                "-u",
                service_name(rest),
                "-n",
                "80",
                "--no-pager",
            ],
            config.command_timeout,
        )
    if cmd == "/deploy":
        return run_shell(
            "set -e; "
            "git pull --ff-only; "
            "source ~/miniconda3/etc/profile.d/conda.sh; "
            "conda activate quant; "
            "pip install -q -e '.[web,crawler]' -i https://pypi.tuna.tsinghua.edu.cn/simple; "
            "mkdir -p ~/.config/systemd/user; "
            "cp deploy/ecs/systemd/*.service ~/.config/systemd/user/; "
            "systemctl --user daemon-reload; "
            "systemctl --user restart quant-trading-fund-web.service "
            "quant-trading-fund-crawler.service",
            max(config.command_timeout, 240),
        )
    if cmd == "/run":
        if not config.allow_shell:
            return "TELEGRAM_ALLOW_SHELL 未开启，拒绝执行 /run。"
        if not rest.strip():
            return "用法: /run <shell command>"
        return run_shell(rest, config.command_timeout)
    return "未知命令。发送 /help 查看可用命令。"


def run_loop(config: Config) -> None:
    bot = TelegramBot(config)
    offset: int | None = None
    LOG.info("telegram bot started; allowed_chat_ids=%s", sorted(config.allowed_chat_ids))
    while True:
        try:
            for update in bot.get_updates(offset):
                offset = int(update["update_id"]) + 1
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = str(chat.get("id", ""))
                text = str(message.get("text") or "").strip()
                if not chat_id or not text.startswith("/"):
                    continue
                try:
                    reply = handle_command(config, chat_id, text)
                except subprocess.TimeoutExpired:
                    reply = "命令执行超时。"
                except Exception as exc:  # noqa: BLE001 - bot should report command errors.
                    LOG.exception("command failed")
                    reply = f"执行失败: {exc}"
                bot.send_message(chat_id, reply)
        except Exception:
            LOG.exception("poll failed")
            time.sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram bot for quant-trading ECS operations")
    parser.add_argument("--once", action="store_true", help="Validate config and exit")
    args = parser.parse_args()
    logging.basicConfig(
        level=os.environ.get("TELEGRAM_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = load_config()
    if args.once:
        print("telegram bot config ok")
        return
    run_loop(config)


if __name__ == "__main__":
    main()
