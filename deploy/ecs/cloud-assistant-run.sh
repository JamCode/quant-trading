#!/usr/bin/env bash
# 经云助手执行任意 shell（root 环境）
#   ./deploy/ecs/cloud-assistant-run.sh 'hostname && whoami'
#   ./deploy/ecs/cloud-assistant-run.sh -f deploy/ecs/scripts/my-check.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=cloud-assistant-lib.sh
source "${SCRIPT_DIR}/cloud-assistant-lib.sh"

cloud_assistant_load_env
cloud_assistant_require_cli
cloud_assistant_resolve_instance_id
cloud_assistant_check_agent

if [[ "${1:-}" == "-f" ]]; then
  [[ -n "${2:-}" && -f "${2}" ]] || _cloud_assistant_die "用法: $0 -f path/to/script.sh"
  CMD="$(cat "$2")"
else
  CMD="${*:-hostname && whoami && id}"
fi

cloud_assistant_run_shell "$CMD"
