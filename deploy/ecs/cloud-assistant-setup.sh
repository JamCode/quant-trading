#!/usr/bin/env bash
# 一次性：安装 CLI、写 cloud-assistant.env、登录阿里云（OAuth 或 AK）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"

if ! command -v aliyun >/dev/null 2>&1; then
  "$SCRIPT_DIR/install-aliyun-cli.sh"
fi

if [[ ! -f "$SCRIPT_DIR/cloud-assistant.env" ]]; then
  cp "$SCRIPT_DIR/cloud-assistant.env.example" "$SCRIPT_DIR/cloud-assistant.env"
  echo "已创建 $SCRIPT_DIR/cloud-assistant.env"
fi

if [[ -f "$HOME/.aliyun/config.json" ]]; then
  echo "已存在 ~/.aliyun/config.json，跳过登录"
  aliyun configure list 2>/dev/null || true
else
  echo ""
  echo "=========================================="
  echo "  需要登录阿里云（一次性）"
  echo "=========================================="
  echo "推荐 OAuth（浏览器登录，不用粘贴 AccessKey）："
  echo "  aliyun configure --mode OAuth --profile default"
  echo ""
  echo "或使用 AccessKey："
  echo "  aliyun configure --mode AK --profile default"
  echo ""
  read -r -p "现在用 OAuth 登录？[Y/n] " ans
  if [[ "${ans:-Y}" =~ ^[Yy]$ ]]; then
    aliyun configure --mode OAuth --profile default
  else
    aliyun configure --mode AK --profile default
  fi
fi

echo ""
echo "==> 测试 API（查询地域）"
aliyun ecs DescribeRegions --region cn-hangzhou 2>&1 | head -5

echo ""
echo "==> 云助手探活"
"$SCRIPT_DIR/cloud-assistant-run.sh" 'hostname && whoami'

echo ""
echo "完成。日常部署: $SCRIPT_DIR/cloud-assistant-deploy.sh"
