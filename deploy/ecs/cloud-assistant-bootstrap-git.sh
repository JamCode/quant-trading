#!/usr/bin/env bash
# 首次：经云助手在 ECS 上 git clone（或跳过重克隆）
#   ./deploy/ecs/cloud-assistant-bootstrap-git.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=cloud-assistant-lib.sh
source "${SCRIPT_DIR}/cloud-assistant-lib.sh"

cloud_assistant_load_env
cloud_assistant_require_cli
cloud_assistant_resolve_instance_id
cloud_assistant_check_agent

GIT_REPO="${GIT_REPO:-git@github.com:JamCode/quant-trading.git}"

read -r -d '' REMOTE_SCRIPT <<EOF || true
#!/bin/bash
set -euo pipefail
runuser -l wanghan -c '
  set -e
  if [[ -d ${ECS_REPO_PATH}/.git ]]; then
    echo "git repo already exists at ${ECS_REPO_PATH}"
    cd ${ECS_REPO_PATH} && git remote -v && git status -sb
    exit 0
  fi
  mkdir -p "\$(dirname ${ECS_REPO_PATH})"
  git clone --branch ${ECS_GIT_BRANCH} ${GIT_REPO} ${ECS_REPO_PATH}
  cd ${ECS_REPO_PATH} && git log -1 --oneline
'
EOF

cloud_assistant_run_shell "$REMOTE_SCRIPT"
echo "cloud-assistant-bootstrap-git: ok"
echo "若 clone 因 GitHub SSH 失败，请在 Workbench 上手动 clone，或改用 HTTPS + PAT。"
