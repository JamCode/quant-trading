#!/usr/bin/env bash
# Merge DASHSCOPE / DingTalk keys from project .env into ECS fund-stack.env (secrets not printed).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
ENV_FILE="${ROOT}/.env"
[[ -f "$ENV_FILE" ]] || { echo "missing ${ENV_FILE}" >&2; exit 1; }

REMOTE_SCRIPT="$(mktemp)"
trap 'rm -f "$REMOTE_SCRIPT"' EXIT

python3 - "$ENV_FILE" >"$REMOTE_SCRIPT" <<'PY'
import base64
import sys

env_file = sys.argv[1]
keys = {
    "DASHSCOPE_API_KEY",
    "DINGTALK_WEBHOOK_URL",
    "DINGTALK_SECRET",
    "QWEN_MODEL",
    "FUND_ADVISOR_ENABLE_SEARCH",
    "FUND_ADVISOR_STYLE",
    "FUND_ADVISOR_HORIZON",
}
vals: dict[str, str] = {}
for raw in open(env_file, encoding="utf-8"):
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, _, v = line.partition("=")
    k, v = k.strip(), v.strip().strip('"').strip("'")
    if k in keys and v:
        vals[k] = v
for req in ("DASHSCOPE_API_KEY", "DINGTALK_WEBHOOK_URL", "DINGTALK_SECRET"):
    if req not in vals:
        raise SystemExit(f"missing {req} in {env_file}")

blob = base64.b64encode(repr(vals).encode()).decode()
print(
    f"""#!/bin/bash
set -euo pipefail
runuser -l wanghan -c "python3 -c '
import base64
vals = eval(base64.b64decode(\\\"{blob}\\\").decode())
path = \\\"/home/wanghan/quant-trading/deploy/ecs/fund-stack.env\\\"
try:
    text = open(path, encoding=\\\"utf-8\\\").read()
except FileNotFoundError:
    text = \\\"\\\"
lines = text.splitlines()
out = []
seen = set()
for line in lines:
    if not line.strip() or line.strip().startswith(\\\"#\\\") or \\\"=\\\" not in line:
        out.append(line)
        continue
    k = line.split(\\\"=\\\", 1)[0].strip()
    if k in vals:
        out.append(f\\\"{{k}}={{vals[k]}}\\\")
        seen.add(k)
    else:
        out.append(line)
for k, v in vals.items():
    if k not in seen:
        out.append(f\\\"{{k}}={{v}}\\\")
open(path, \\\"w\\\", encoding=\\\"utf-8\\\").write(chr(10).join(out).rstrip() + chr(10))
print(\\\"updated:\\\", \\\", \\\".join(sorted(vals)))
'"
"""
)
PY

chmod +x "$REMOTE_SCRIPT"
"${SCRIPT_DIR}/cloud-assistant-run.sh" -f "$REMOTE_SCRIPT"
