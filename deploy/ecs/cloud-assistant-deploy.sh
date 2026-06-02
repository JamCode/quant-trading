#!/usr/bin/env bash
# 经云助手在 ECS 上部署 quant-trading（git pull + pip + 重启服务）
# 不依赖本机 SSH。需：aliyun configure + 云助手 Agent + ECS 上已有 git 仓库。
#
#   cp deploy/ecs/cloud-assistant.env.example deploy/ecs/cloud-assistant.env
#   ./deploy/ecs/cloud-assistant-bootstrap-git.sh   # 首次
#   ./deploy/ecs/cloud-assistant-deploy.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=cloud-assistant-lib.sh
source "${SCRIPT_DIR}/cloud-assistant-lib.sh"

cloud_assistant_load_env
cloud_assistant_require_cli
cloud_assistant_resolve_instance_id
cloud_assistant_check_agent

GIT_FETCH_PRIMARY="${GIT_FETCH_URL:-}"

read -r -d '' REMOTE_SCRIPT <<EOF || true
#!/bin/bash
set -euo pipefail
runuser -l wanghan -c '
  set -e
  cd ${ECS_REPO_PATH}
  if [[ ! -d .git ]]; then
    echo "missing git repo at ${ECS_REPO_PATH}; run cloud-assistant-bootstrap-git.sh first" >&2
    exit 1
  fi
  BR="${ECS_GIT_BRANCH}"
  ok=0
  for url in \
    "${GIT_FETCH_PRIMARY}" \
    "https://ghfast.top/https://github.com/JamCode/quant-trading.git" \
    "https://mirror.ghproxy.com/https://github.com/JamCode/quant-trading.git" \
    "https://github.com/JamCode/quant-trading.git"
  do
    [[ -n "\$url" ]] || continue
    echo "git fetch via \$url"
    git remote set-url origin "\$url"
    if timeout 120 git fetch origin "\$BR"; then
      ok=1
      break
    fi
  done
  if [[ "\$ok" -ne 1 ]]; then
    echo "git fetch failed (ECS may not reach GitHub); set GIT_FETCH_URL in cloud-assistant.env" >&2
    exit 1
  fi
  git reset --hard "origin/\${BR}"
  source ~/miniconda3/etc/profile.d/conda.sh
  conda activate quant
  pip install -q -U pip setuptools wheel -i https://pypi.tuna.tsinghua.edu.cn/simple
  pip install -q -e ".[web,crawler]" -i https://pypi.tuna.tsinghua.edu.cn/simple
  python -c "import fastapi; import fund_platform; print(\"imports ok\")"
  export XDG_RUNTIME_DIR=/run/user/\$(id -u)
  mkdir -p ~/.config/systemd/user
  cp deploy/ecs/systemd/*.service ~/.config/systemd/user/
  cp deploy/ecs/systemd/*.timer ~/.config/systemd/user/ 2>/dev/null || true
  systemctl --user daemon-reload
  systemctl --user enable quant-trading-fund-web.service quant-trading-fund-crawler.service
  systemctl --user enable quant-trading-fund-advisor.timer
  systemctl --user restart quant-trading-fund-web.service quant-trading-fund-crawler.service
  systemctl --user restart quant-trading-fund-advisor.timer
  if grep -q "^TELEGRAM_BOT_TOKEN=." deploy/ecs/fund-stack.env 2>/dev/null; then
    systemctl --user enable quant-trading-telegram-bot.service
    systemctl --user restart quant-trading-telegram-bot.service
  fi
  sleep 4
  curl -sf http://127.0.0.1:8010/health && echo
'
EOF

cloud_assistant_run_shell "$REMOTE_SCRIPT"
echo "cloud-assistant-deploy: ok"
