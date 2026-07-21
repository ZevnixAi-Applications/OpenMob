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

## Simulator (✅ verified-live, fully supported)

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

## Real devices (iOS 17+): ⚙️ works-with-setup, with a known blocker

**Status (verified 2026-07-21 on a real iPhone, UDID `00008101-…`, iOS 26.5.2,
pymobiledevice3 9.36.1):**

- ✅ **The no-sudo tunnel transport works.** A pure-Python userspace tunnel forwarded
  to a local port lets the engine's lldb worker reach an on-device debugserver over
  gdb-remote — no root, no `tunneld`. Verified: `ConnectRemote` reaches the device and
  returns a live gdb-remote connection.
- ⛔ **Attaching to a *running* app for a backtrace is NOT yet possible from the
  engine.** pymobiledevice3's `debugserver start-server` starts an *unattached*
  debugserver (it is launch-oriented). `process connect` to it yields a connection
  with **no process** — the engine's connect returns `pid 0`, state `connected`, and
  there is nothing to break in or backtrace. Getting a stopped, debuggable process
  requires a debugserver that is already *attached* to (or *launching*) the target,
  which the current CLI does not expose in a form the engine consumes. This blocker is
  independent of sudo — a root `tunneld` + `start-server` hits the same wall.

So real-device lldb is honestly: **transport verified, attach not wired end-to-end.**
The simulator path (above) is the fully verified, recommended target.

### No-sudo tunnel runbook (verified to the "connected" step)

Run **one** command; it establishes the userspace tunnel and starts + forwards a
debugserver, no root required:

```bash
pymobiledevice3 developer debugserver start-server --userspace --local-port 10011
#   ...prints:  (lldb) process connect connect://[127.0.0.1]:10011
```

Then create a session, passing that URL as `debugserver_url`:

```bash
curl -X POST http://127.0.0.1:8930/api/v1/debug/sessions \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"<UDID>","bundle_id":"<bundle>",
       "debugserver_url":"connect://[127.0.0.1]:10011"}'
```

The engine trusts a supplied `debugserver_url` and connects lldb to it (no `tunneld`
probe). Observed today: the session is *created* (`pid 0`), but because the
`start-server` debugserver has no process attached, its state immediately reads
`exited` — `pause`/`state` report no running process and no backtrace is possible
(see the ⛔ blocker above).

### Root tunnel alternative

The kernel-routable tunnel needed by tools that drive an *external* lldb (e.g.
`pymobiledevice3 developer debugserver lldb`, which refuses the userspace tunnel):

```bash
sudo pymobiledevice3 remote tunneld           # one-time, needs root
pymobiledevice3 developer debugserver start-server --tunnel <UDID>
```

This still produces an *unattached* `start-server`, so it does not lift the ⛔ blocker
for the engine's attach flow; it only unblocks external-lldb tooling.

### Capability error

When no `debugserver_url` is supplied for a real device, session creation fails with a
structured error — HTTP 409 `{"error":"capability_missing","commands":[...]}` (REST) or
the same shape from `debug_attach` (MCP) — whose `commands` now include the no-sudo
userspace command above as well as the root-tunnel alternative.

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
