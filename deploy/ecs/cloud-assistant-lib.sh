# shellcheck shell=bash
# 云助手公共函数（由 cloud-assistant-*.sh source）

readonly _CLOUD_ASSISTANT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

_cloud_assistant_die() {
  echo "cloud-assistant: $*" >&2
  exit 1
}

cloud_assistant_load_env() {
  local _timeout_cli="${ECS_COMMAND_TIMEOUT:-}"
  if [[ -f "${_CLOUD_ASSISTANT_DIR}/cloud-assistant.env" ]]; then
    # shellcheck disable=SC1091
    set -a
    source "${_CLOUD_ASSISTANT_DIR}/cloud-assistant.env"
    set +a
  fi
  ECS_REGION_ID="${ECS_REGION_ID:-cn-hangzhou}"
  ECS_PUBLIC_IP="${ECS_PUBLIC_IP:-47.110.78.65}"
  if [[ -n "${_timeout_cli}" ]]; then
    ECS_COMMAND_TIMEOUT="${_timeout_cli}"
  else
    ECS_COMMAND_TIMEOUT="${ECS_COMMAND_TIMEOUT:-300}"
  fi
  ECS_REPO_PATH="${ECS_REPO_PATH:-/home/wanghan/quant-trading}"
  ECS_GIT_BRANCH="${ECS_GIT_BRANCH:-main}"
}

cloud_assistant_require_cli() {
  command -v aliyun >/dev/null 2>&1 || _cloud_assistant_die \
    "未找到 aliyun CLI。安装: brew install aliyun-cli 或见 deploy/ecs/README.md"
  aliyun ecs DescribeRegions --region "$ECS_REGION_ID" >/dev/null 2>&1 || _cloud_assistant_die \
    "aliyun 未配置或 AK 无效。请运行: aliyun configure（勿将 AK 提交 Git）"
}

cloud_assistant_resolve_instance_id() {
  if [[ -n "${ECS_INSTANCE_ID:-}" ]]; then
    return 0
  fi
  echo "==> 查询实例 ID（公网 IP ${ECS_PUBLIC_IP}）..."
  local json
  local tmp
  tmp="$(mktemp)"
  trap 'rm -f "$tmp"' RETURN
  aliyun ecs DescribeInstances \
    --RegionId "$ECS_REGION_ID" \
    --PageSize 100 \
    >"$tmp" 2>/dev/null || _cloud_assistant_die "DescribeInstances 失败，请在 cloud-assistant.env 填写 ECS_INSTANCE_ID"

  ECS_INSTANCE_ID="$(
    python3 - "$tmp" "$ECS_PUBLIC_IP" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    data = json.load(f)
ip = sys.argv[2]
for inst in data.get("Instances", {}).get("Instance", []) or []:
    pubs = inst.get("PublicIpAddress", {}).get("IpAddress") or []
    eip = inst.get("EipAddress", {}).get("IpAddress") or ""
    all_ips = list(pubs) + ([eip] if eip else [])
    if ip in all_ips:
        print(inst["InstanceId"])
        raise SystemExit(0)
raise SystemExit(1)
PY
  )" || _cloud_assistant_die "未找到 IP=${ECS_PUBLIC_IP} 的实例，请设置 ECS_INSTANCE_ID"

  echo "==> ECS_INSTANCE_ID=${ECS_INSTANCE_ID}"
}

cloud_assistant_check_agent() {
  local json
  json="$(aliyun ecs DescribeCloudAssistantStatus \
    --RegionId "$ECS_REGION_ID" \
    --InstanceId.1 "$ECS_INSTANCE_ID" \
    2>/dev/null)" || {
    echo "警告: 无法查询云助手状态，继续尝试 RunCommand" >&2
    return 0
  }
  if ! grep -qE 'CloudAssistantStatus.*true|Available' <<<"$json"; then
    echo "警告: 云助手可能未就绪，若失败请在控制台安装 Agent。响应片段: $(head -c 200 <<<"$json")" >&2
  fi
}

cloud_assistant_run_shell() {
  local script_content="$1"
  local b64 invoke_id json status i

  b64="$(printf '%s' "$script_content" | base64 | tr -d '\n')"

  echo "==> RunCommand on ${ECS_INSTANCE_ID} (timeout ${ECS_COMMAND_TIMEOUT}s)..."
  json="$(aliyun ecs RunCommand \
    --RegionId "$ECS_REGION_ID" \
    --Type RunShellScript \
    --ContentEncoding Base64 \
    --CommandContent "$b64" \
    --Timeout "$ECS_COMMAND_TIMEOUT" \
    --InstanceId.1 "$ECS_INSTANCE_ID" \
    )" || _cloud_assistant_die "RunCommand 失败"

  invoke_id="$(python3 -c "import json,sys; print(json.load(sys.stdin)['InvokeId'])" <<<"$json")"
  echo "==> InvokeId=${invoke_id}"

  local poll_secs=3
  local max_polls=$(( (ECS_COMMAND_TIMEOUT + poll_secs - 1) / poll_secs ))
  if (( max_polls < 60 )); then
    max_polls=60
  fi
  for i in $(seq 1 "$max_polls"); do
    sleep "$poll_secs"
    json="$(aliyun ecs DescribeInvocations \
      --RegionId "$ECS_REGION_ID" \
      --InvokeId "$invoke_id" \
      )"
    status="$(printf '%s' "$json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
items = d.get('Invocations', {}).get('Invocation') or []
if not items:
    print('Pending')
else:
    print(items[0].get('InvocationStatus', 'Pending'))
")"
    echo "    status[$i]=${status}"
    case "$status" in
      Success) break ;;
      Failed|Cancelled|Stopped|PartialFailed)
        _cloud_assistant_print_output "$invoke_id" || true
        _cloud_assistant_die "命令执行失败: ${status}"
        ;;
    esac
  done

  if [[ "$status" != "Success" ]]; then
    _cloud_assistant_print_output "$invoke_id" || true
    _cloud_assistant_die "等待超时，最后状态: ${status}"
  fi

  _cloud_assistant_print_output "$invoke_id"
}

_cloud_assistant_print_output() {
  local invoke_id="$1" json
  json="$(aliyun ecs DescribeInvocationResults \
    --RegionId "$ECS_REGION_ID" \
    --InvokeId "$invoke_id" \
    )" || return 1

  printf '%s' "$json" | python3 -c "
import json, sys, base64
d = json.load(sys.stdin)
inv = d.get('Invocation') or d
items = inv.get('InvocationResults', {}).get('InvocationResult') or []
if not items:
    items = d.get('InvocationResults', {}).get('InvocationResult') or []
if not items:
    print('(no output)')
    sys.exit(0)
out = items[0].get('Output') or ''
if not out:
    print('(empty)')
    sys.exit(0)
try:
    print(base64.b64decode(out).decode('utf-8', errors='replace'))
except Exception:
    print(out)
"
}
