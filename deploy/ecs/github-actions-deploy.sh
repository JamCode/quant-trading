#!/usr/bin/env bash
# GitHub Actions / CI：rsync 代码 → pip install → 重启 fund 服务 → health check
# 需环境变量：ECS_KEY（私钥路径）
# 可选：ECS_HOST、ECS_USER、ECS_PORT（默认 2222）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ECS_USER="${ECS_USER:-wanghan}"
ECS_HOST="${ECS_HOST:-47.110.78.65}"
ECS_PORT="${ECS_PORT:-2222}"
export ECS_PORT

if [[ -z "${ECS_KEY:-}" ]]; then
  echo "ECS_KEY is required" >&2
  exit 1
fi

"${SCRIPT_DIR}/push-and-setup.sh"

SSH=(ssh -i "$ECS_KEY" -p "$ECS_PORT" -o StrictHostKeyChecking=accept-new)
ECS="${ECS_USER}@${ECS_HOST}"

echo "==> restart systemd user services"
"${SSH[@]}" "$ECS" bash << 'REMOTE'
set -euo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
mkdir -p "$HOME/.config/systemd/user"
cp "$HOME/quant-trading/deploy/ecs/systemd/"*.service "$HOME/.config/systemd/user/"
cp "$HOME/quant-trading/deploy/ecs/systemd/"*.timer "$HOME/.config/systemd/user/" 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable quant-trading-fund-web.service quant-trading-fund-crawler.service
systemctl --user restart quant-trading-fund-web.service quant-trading-fund-crawler.service
if grep -q '^TELEGRAM_BOT_TOKEN=.' "$HOME/quant-trading/deploy/ecs/fund-stack.env" 2>/dev/null; then
  systemctl --user enable quant-trading-telegram-bot.service
  systemctl --user restart quant-trading-telegram-bot.service
fi
sleep 4
curl -sf http://127.0.0.1:8010/health && echo ""
REMOTE

echo "github-actions-deploy: ok"
