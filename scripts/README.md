# OpenMob release-gate E2E scripts

End-to-end gate that proves the full automation flow works through the OpenMob
engine HTTP API and through real Claude via MCP, using the deterministic
testbed app in `testapp/`.

## Prerequisites

- Engine serving: `cd engine && uv run openmob serve` (port 8930)
- Android emulator online as `emulator-5554` (`adb devices`)
- Testbed APK built: `cd testapp && flutter build apk --release`
- `claude` CLI installed (for the MCP test)

## Running the gate

```sh
# 1. Engine-API harness (installs + launches the testbed via the engine,
#    then drives everything through http://127.0.0.1:8930/api/v1 only):
uv run --project engine python scripts/e2e_test.py
# Green run ends with "E2E-OK". Release gate = green TWICE consecutively.

# 2. MCP-with-real-Claude test (needs the testbed foregrounded on page 1,
#    which a prior e2e_test.py run leaves in place):
bash scripts/e2e_mcp_test.sh
# Green run ends with "MCP-GATE-OK".
```

## What the harness checks

`e2e_test.py` (engine HTTP API only — adb is never used for automation):

- `/devices` lists the emulator with a sane size
- screenshot decodes and matches the reported size; center pixel is a pure
  testbed color
- tap toggles pure red <-> green, verified across 11 taps
- `/text` drives the top-strip parity indicator (yellow = odd char count,
  blue = even), with an extra append that catches dropped keystrokes
- swipe navigates to the pure-magenta page 2 and a tap returns
- soak: 40 consecutive screenshot+tap cycles with zero HTTP errors and zero
  wrong colors, then a 20 s WebSocket stream asserting >= 15 frames, no
  inter-frame gap > 4 s, and every frame's center sampling to an expected
  color (never black/white/garbage)

`e2e_mcp_test.sh` runs `claude -p` with `scripts/mcp-config.json`
(`--strict-mcp-config`, tools allow-listed to `mcp__openmob__*`), requires the
model to answer `E2E-MCP-OK` only if every MCP tool call succeeded, and then
independently verifies via an engine screenshot that Claude's center tap
really toggled the testbed color.

## Testbed app contract (`testapp/lib/main.dart`)

- Page 1: background pure red `#FF0000` <-> pure green `#00FF00` on tap;
  TextField in the bottom 10%; top 15% strip pure blue `#0000FF` (even chars)
  / pure yellow `#FFFF00` (odd), absent at 0 chars
- Page 2 (swipe left): pure magenta `#FF00FF`; tap snaps back to page 1
- No animated color transitions; layout is keyboard-inset independent
