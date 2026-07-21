#!/usr/bin/env bash
# OpenMob MCP-with-real-Claude E2E test.
#
# Runs the `claude` CLI non-interactively against the OpenMob MCP server and
# asks it to drive the emulator (list devices, screenshot, tap center,
# screenshot). Pass criteria:
#   1. stdout contains E2E-MCP-OK (Claude confirms every tool call succeeded)
#   2. the tap physically toggled the testbed color, verified via an engine
#      screenshot before/after (proves Claude's tap landed on the device).
#
# Prereqs: engine serving on 8930, testbed app installed and in the foreground
# on the target device (run scripts/e2e_test.py first, or the gate script).
# Device defaults to emulator-5554; override with $1 or OPENMOB_DEVICE.

set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEVICE="${1:-${OPENMOB_DEVICE:-emulator-5554}}"
BASE="http://127.0.0.1:8930/api/v1"

sample_center() {
  E2E_DEVICE="$DEVICE" uv run --project "$REPO/engine" python - <<'PY'
import io, os, httpx
from PIL import Image
device = os.environ["E2E_DEVICE"]
r = httpx.get(f"http://127.0.0.1:8930/api/v1/devices/{device}/screenshot", timeout=30)
r.raise_for_status()
img = Image.open(io.BytesIO(r.content)).convert("RGB")
w, h = img.size
print(",".join(map(str, img.getpixel((w // 2, h // 2))[:3])))
PY
}

echo "== MCP E2E: sampling center color before Claude runs"
BEFORE="$(sample_center)" || { echo "FAIL: could not sample before-color"; exit 1; }
echo "   before=$BEFORE"

PROMPT="Using only the openmob MCP tools: call list_devices; take a screenshot of device $DEVICE; tap device $DEVICE at the exact center of its screen; take another screenshot. If and only if every tool call succeeded without error, output exactly: E2E-MCP-OK"

echo "== MCP E2E: running claude -p against the openmob MCP server"
OUT="$(claude -p "$PROMPT" \
  --mcp-config "$REPO/scripts/mcp-config.json" \
  --strict-mcp-config \
  --allowedTools "mcp__openmob__*" 2>&1)"
STATUS=$?
echo "----- claude output -----"
echo "$OUT"
echo "-------------------------"

if [ $STATUS -ne 0 ]; then
  echo "FAIL: claude exited with status $STATUS"
  exit 1
fi
if ! echo "$OUT" | grep -q "E2E-MCP-OK"; then
  echo "FAIL: stdout does not contain E2E-MCP-OK"
  exit 1
fi

echo "== MCP E2E: verifying the tap physically toggled the testbed color"
sleep 1
AFTER="$(sample_center)" || { echo "FAIL: could not sample after-color"; exit 1; }
echo "   after=$AFTER"

if [ "$BEFORE" = "$AFTER" ]; then
  echo "FAIL: center color did not change ($BEFORE -> $AFTER); tap did not land"
  exit 1
fi
# Near-pure red/green check (+-10 per channel: iOS WDA screenshots pass
# through display color management, e.g. pure red arrives as 253,0,2).
VERDICT="$(E2E_PIXEL="$AFTER" uv run --project "$REPO/engine" python - <<'PY'
import os
pixel = tuple(int(v) for v in os.environ["E2E_PIXEL"].split(","))
ok = any(
    all(abs(p - c) <= 10 for p, c in zip(pixel, color))
    for color in ((255, 0, 0), (0, 255, 0))
)
print("ok" if ok else "no")
PY
)"
if [ "$VERDICT" != "ok" ]; then
  echo "FAIL: after-color $AFTER is not (near-)pure red/green"
  exit 1
fi

echo "PASS: E2E-MCP-OK received and tap toggled color ($BEFORE -> $AFTER)"
echo "MCP-GATE-OK"
