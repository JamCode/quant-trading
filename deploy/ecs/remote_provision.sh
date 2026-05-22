#!/usr/bin/env bash
# 在 ECS 上以 wanghan 执行（由本机 ssh bash -s < deploy/ecs/remote_provision.sh）
set -euo pipefail

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
PY="${HOME}/miniconda3/envs/quant/bin/python"

if [[ ! -x "$PY" ]]; then
  echo "missing conda env quant at $PY" >&2
  exit 1
fi

ENV_FILE="$HOME/quant-trading/deploy/ecs/fund-stack.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE — run deploy/ecs/root_mysql_bootstrap.sh as root first" >&2
  exit 1
fi

mkdir -p "$HOME/.config/systemd/user"
cp "$HOME/quant-trading/deploy/ecs/systemd/"*.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable quant-trading-fund-web.service quant-trading-fund-crawler.service
systemctl --user restart quant-trading-fund-web.service quant-trading-fund-crawler.service || true
sleep 4
curl -sS http://127.0.0.1:8010/health && echo ""

if ! grep -q 'location /quant-funds/' "$HOME/guitar-ai-coach/deploy/ecs/nginx/guitar-server.conf"; then
  echo "nginx: missing /quant-funds/ in guitar-server.conf — sync guitar-ai-coach deploy/ecs/nginx first" >&2
  exit 1
fi
echo "nginx: using guitar-server.conf from guitar-ai-coach repo"
sudo nginx -t && sudo systemctl reload nginx
sudo loginctl enable-linger "$(whoami)" 2>/dev/null || true
echo "remote_provision: ok"
