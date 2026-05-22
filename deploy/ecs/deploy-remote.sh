#!/usr/bin/env bash
# 本机一键：推送代码 → root 初始化 MySQL → wanghan 启服务 + Nginx
#   ECS_KEY="$HOME/Documents/quant-trading/my-ecs-key2.pem" ./deploy/ecs/deploy-remote.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

ECS_USER="${ECS_USER:-wanghan}"
ECS_HOST="${ECS_HOST:-47.110.78.65}"
ECS="${ECS_USER}@${ECS_HOST}"
ROOT="root@${ECS_HOST}"

if [[ -z "${ECS_KEY:-}" ]]; then
  echo "请设置 ECS_KEY" >&2
  exit 1
fi
chmod 600 "$ECS_KEY"
SSH=(ssh -i "$ECS_KEY" -o StrictHostKeyChecking=accept-new)

"${SCRIPT_DIR}/push-and-setup.sh"

echo "==> root: mysqld + fund_svc schema + fund-stack.env"
"${SSH[@]}" "$ROOT" 'bash -s' < "${SCRIPT_DIR}/root_mysql_bootstrap.sh"

echo "==> wanghan: systemd + nginx + health"
"${SSH[@]}" "$ECS" 'bash -s' < "${SCRIPT_DIR}/remote_provision.sh"

echo "==> public check"
curl -sS -m 15 "https://wanghanai.xyz/quant-funds/health" && echo ""

echo "deploy-remote: done"
