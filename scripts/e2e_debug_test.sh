#!/usr/bin/env bash
#
# e2e_debug_test.sh — end-to-end smoke test for the openmob MCP debug_* tools.
#
# Drives a real `claude -p` run against `openmob mcp`, asking it to attach to the
# testbed app in a booted iOS simulator, hit a breakpoint, read the backtrace,
# evaluate an expression, and detach. Passes when the model prints DEBUG-MCP-OK.
#
# Prereqs:
#   - a booted iOS simulator with the testbed running: testapp/build.sh
#   - the `claude` CLI on PATH
#
# Usage: ./e2e_debug_test.sh [UDID]   (defaults to the booted simulator)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENGINE_DIR="$(cd "${SCRIPT_DIR}/../engine" && pwd)"
BUNDLE_ID="ai.zevnix.openmob.testbed"

UDID="${1:-}"
if [[ -z "${UDID}" ]]; then
    UDID="$(xcrun simctl list devices booted -j \
        | /usr/bin/python3 -c 'import json,sys
devices = json.load(sys.stdin)["devices"]
booted = [d["udid"] for ds in devices.values() for d in ds if d["state"] == "Booted"]
print(booted[0] if booted else "")')"
fi
[[ -n "${UDID}" ]] || { echo "No booted simulator found — boot one and run testapp/build.sh"; exit 1; }
echo "[e2e-debug] simulator: ${UDID}"

MCP_CONFIG="$(mktemp -t openmob-mcp-config)"
trap 'rm -f "${MCP_CONFIG}"' EXIT
cat > "${MCP_CONFIG}" <<EOF
{
  "mcpServers": {
    "openmob": {
      "command": "uv",
      "args": ["--directory", "${ENGINE_DIR}", "run", "openmob", "mcp"]
    }
  }
}
EOF

PROMPT="Using ONLY the openmob MCP debug tools, debug the iOS app '${BUNDLE_ID}' \
already running in simulator ${UDID}: \
1) debug_attach with device_id='${UDID}', bundle_id='${BUNDLE_ID}', and \
breakpoints=['-[ViewController tick:]'] (the app ticks every 2 seconds, so the \
breakpoint fires on its own). \
2) Wait a moment, then debug_state and report the top stack frame of the stopped thread. \
3) debug_eval expression '(int)1+2'. \
4) debug_step kind='over'. \
5) debug_step kind='continue', then debug_detach (kill=false). \
If the backtrace showed -[ViewController tick:] and the eval returned 3, finish your \
reply with the exact token DEBUG-MCP-OK. Otherwise print DEBUG-MCP-FAIL and why."

OUTPUT="$(claude -p "${PROMPT}" \
    --mcp-config "${MCP_CONFIG}" \
    --allowedTools "mcp__openmob__debug_attach,mcp__openmob__debug_breakpoint,mcp__openmob__debug_step,mcp__openmob__debug_eval,mcp__openmob__debug_state,mcp__openmob__debug_detach" \
    2>&1)" || { echo "${OUTPUT}"; echo "[e2e-debug] claude -p failed"; exit 1; }

echo "${OUTPUT}"
if grep -q "DEBUG-MCP-OK" <<< "${OUTPUT}"; then
    echo "[e2e-debug] PASS"
else
    echo "[e2e-debug] FAIL — sentinel not found"
    exit 1
fi
