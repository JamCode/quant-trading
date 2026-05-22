#!/usr/bin/env bash
# 在本机执行：rsync quant-trading → ECS，创建 venv 并 pip install。
#   ECS_KEY="$HOME/Documents/quant-trading/my-ecs-key2.pem" ./deploy/ecs/push-and-setup.sh
# 可选：ECS_USER（默认 wanghan）、ECS_HOST（默认 47.110.78.65）

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

ECS_USER="${ECS_USER:-wanghan}"
ECS_HOST="${ECS_HOST:-47.110.78.65}"
ECS="${ECS_USER}@${ECS_HOST}"

if [[ -z "${ECS_KEY:-}" ]]; then
  echo "请设置 ECS_KEY，例如：" >&2
  echo "  ECS_KEY=\"\$HOME/Documents/quant-trading/my-ecs-key2.pem\" $0" >&2
  exit 1
fi
chmod 600 "$ECS_KEY"

SSH=(ssh -i "$ECS_KEY" -o StrictHostKeyChecking=accept-new)
RSYNC=(rsync -avz -e "ssh -i $ECS_KEY -o StrictHostKeyChecking=accept-new")

echo "==> rsync repo -> ${ECS}:~/quant-trading/"
"${SSH[@]}" "$ECS" "mkdir -p ~/quant-trading"
"${RSYNC[@]}" \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.git' \
  --exclude '*.pem' \
  --exclude '*.egg-info' \
  "$REPO_ROOT/" "$ECS:~/quant-trading/"

echo "==> remote: conda env quant + pip install [web,crawler]"
"${SSH[@]}" "$ECS" bash << 'REMOTE'
set -euo pipefail
cd "$HOME/quant-trading"
CONDA="$HOME/miniconda3"
PY="$CONDA/envs/quant/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "missing $PY — create with: conda create -n quant python=3.12 -y" >&2
  exit 1
fi
PIP_INDEX="${PIP_INDEX:-https://pypi.tuna.tsinghua.edu.cn/simple}"
"$PY" -m pip install -q -U pip setuptools wheel -i "$PIP_INDEX"
"$PY" -m pip install -q -e ".[web,crawler]" -i "$PIP_INDEX"
"$PY" -c "import fastapi; import fund_platform; print('imports ok')"
REMOTE

echo "==> systemd user units (optional, copy + reload)"
"${SSH[@]}" "$ECS" bash << 'REMOTE_INNER'
set -euo pipefail
mkdir -p "$HOME/.config/systemd/user"
cp "$HOME/quant-trading/deploy/ecs/systemd/"*.service "$HOME/.config/systemd/user/"
systemctl --user daemon-reload || true
echo ""
echo "Next on ECS:"
echo "  1) mysql ... < ~/quant-trading/schema/mysql/001_init.sql"
echo "  2) cp ~/quant-trading/deploy/ecs/fund-stack.env.example ~/quant-trading/deploy/ecs/fund-stack.env && edit DATABASE_URL"
echo "  3) systemctl --user enable --now quant-trading-fund-web.service quant-trading-fund-crawler.service"
echo "  4) curl -sS http://127.0.0.1:8010/health"
REMOTE_INNER

echo "==> done"
