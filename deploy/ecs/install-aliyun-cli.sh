#!/usr/bin/env bash
# 本机安装阿里云 CLI（macOS）
set -euo pipefail

if command -v aliyun >/dev/null 2>&1; then
  echo "aliyun 已安装: $(command -v aliyun)"
  aliyun version 2>/dev/null || true
  exit 0
fi

if command -v brew >/dev/null 2>&1; then
  echo "==> brew install aliyun-cli"
  brew install aliyun-cli
else
  echo "==> 官方安装脚本（无 Homebrew 时）"
  echo "请打开: https://help.aliyun.com/document_detail/121541.html"
  exit 1
fi

echo ""
echo "下一步: aliyun configure"
echo "  使用 RAM 子账号 AccessKey（勿提交 Git）"
