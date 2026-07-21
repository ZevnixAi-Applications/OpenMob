# Interactive iOS Debugging

OpenMob can attach a live lldb session to an iOS app, set breakpoints, step, inspect
state, and evaluate expressions — over REST (`/api/v1/debug`, see [API.md](API.md))
and over MCP (`debug_*` tools from `openmob mcp`).

## How it works

lldb's Python module ships with Xcode and only loads under Xcode's own CPython, so it
cannot be imported into the engine's interpreter. Each debug session instead spawns a
dedicated worker (`engine/src/openmob/lldb_worker.py`) via `xcrun python3` with
`sys.path` pointed at `xcrun lldb -P`, and drives it with a JSON-lines protocol over
stdin/stdout. This keeps the full lldb SB API (structured breakpoints, threads,
frames, typed values — no prompt scraping) while isolating lldb from the engine
process: a crashed worker kills one session, not the server.

Session model:

- One session per device; a session survives across REST/MCP calls.
- `attach` resolves `bundle_id` to a pid (the app must already be running), attaches,
  arms any initial breakpoints, then resumes the app.
- Sessions idle for **10 minutes** are detached automatically; detach without
  `kill` leaves the app running.
- `state` responses are depth-limited (20 frames, 30 locals, 10 children, 2 levels)
  so they stay LLM-friendly.

## Simulator (fully supported)

Simulator apps are ordinary macOS processes, so lldb attaches directly — **no tunnel,
no sudo, no pairing**. `device_id` is the simulator UDID (must be Booted).

```bash
# Boot a simulator and run your app (or the bundled testbed):
xcrun simctl boot <UDID>
testapp/build.sh <UDID>        # builds + installs + launches ai.zevnix.openmob.testbed

# Attach by bundle id, arming a breakpoint on the testbed's 2s timer:
curl -X POST http://127.0.0.1:8930/api/v1/debug/sessions \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"<UDID>","bundle_id":"ai.zevnix.openmob.testbed",
       "breakpoints":["-[ViewController tick:]"]}'

# A couple of seconds later the breakpoint has fired:
curl http://127.0.0.1:8930/api/v1/debug/sessions/<SID>/state
#   {"state":"stopped","stop_reason":"breakpoint",
#    "stack":[{"function":"-[ViewController tick:]","file":"main.m","line":31,...},...],
#    "locals":[{"name":"self","type":"ViewController *",...},...]}

curl -X POST .../sessions/<SID>/eval -d '{"expr":"(NSString *)[self->_label text]"}'
#   {"value":"0x...","summary":"@\"tick 19\"","type":"NSString *","description":"tick 19"}

curl -X POST .../sessions/<SID>/step -d '{"kind":"over"}'
curl -X POST .../sessions/<SID>/continue
curl -X DELETE .../sessions/<SID>        # detach; the app keeps running
```

Breakpoint specs: `File.swift:42` / `main.m:31` (file:line), `-[Class method:]`,
`Module.Type.method`, or any symbol name.

Via MCP the same flow is `debug_attach` → `debug_state` → `debug_eval` →
`debug_step` → `debug_detach`, addressed by `device_id` instead of a session id.
`scripts/e2e_debug_test.sh` runs this end-to-end through `claude -p`.

## Real devices (iOS 17+): gated behind a capability check

Debugging a physical iPhone requires plumbing that OpenMob cannot set up by itself:

1. **A usermode tunnel** (needs root):

   ```bash
   sudo pymobiledevice3 remote tunneld
   ```

2. **A debugserver** on the device (via the tunnel):

   ```bash
   pymobiledevice3 developer debugserver start-server
   ```

   Pass the `connect://[host]:port` URL it prints as `debugserver_url` when creating
   the session.

When any prerequisite is missing, session creation fails with a structured error —
HTTP 409 `{"error":"capability_missing","commands":[...]}` (REST) or the same shape
from `debug_attach` (MCP) — listing exactly the commands above. With both in place
the engine connects lldb to the remote debugserver over the gdb-remote protocol.
The real-device path is unit-tested against mocks; the simulator path is verified
live and is the recommended target.

## Notes and limits

- stdout/stderr capture (`GET .../output`) uses an lldb ring buffer; for *attached*
  processes lldb usually cannot intercept output that already goes to the app's own
  descriptors, so expect it to be empty unless the process was launched under the
  debugger.
- `eval` runs with breakpoints ignored and a 15 s expression timeout. The process
  must be stopped (at a breakpoint, or via `pause`).
- Variadic ObjC calls (e.g. `+[NSString stringWithFormat:]`) can fail in lldb's
  expression parser without full type info; prefer simple message sends and member
  access (`self->_count`, `[self->_label text]`).
