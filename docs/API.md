# OpenMob Engine API (v0)

The engine serves a local HTTP + WebSocket API for UIs, and an MCP server for AI agents. Both are thin layers over the same device abstraction.

- Base URL: `http://127.0.0.1:8930/api/v1`
- No auth in v0 (localhost only, bind 127.0.0.1).

## REST

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/health` | `{"status":"ok","version":"..."}` |
| GET | `/devices` | `[{"id","name","platform":"android"\|"ios","status":"online"\|"offline","width":int,"height":int}]` |
| GET | `/devices/{id}/screenshot` | PNG bytes (`image/png`) |
| POST | `/devices/{id}/tap` | `{"x":int,"y":int}` — device pixel coords |
| POST | `/devices/{id}/swipe` | `{"x1","y1","x2","y2","duration_ms":300}` |
| POST | `/devices/{id}/text` | `{"text":"hello"}` |
| POST | `/devices/{id}/key` | `{"key":"home"\|"back"\|"power"\|"volume_up"\|"volume_down"\|"enter"}` |
| POST | `/devices/{id}/install` | multipart `file` (.apk / .ipa) |
| POST | `/devices/{id}/uninstall` | `{"package":"com.example.app"}` |
| GET | `/devices/{id}/apps` | `[{"package","name"}]` |
| POST | `/devices/{id}/launch` | `{"package":"com.example.app"}` |

All action endpoints return `{"ok":true}` or HTTP 4xx/5xx with `{"detail":"..."}`.

## Debugger (`/api/v1/debug`)

Interactive lldb sessions for iOS apps — see [DEBUGGING.md](DEBUGGING.md) for concepts, capabilities, and examples.

| Method | Path | Body / Notes |
|---|---|---|
| POST | `/debug/sessions` | `{"device_id","pid"?\|"bundle_id"?,"breakpoints":["main.m:31","-[Class method:]"],"debugserver_url"?}` → session info + attach result; app resumes running |
| GET | `/debug/sessions` | list active sessions |
| GET | `/debug/sessions/{id}/state` | `?stack=&vars=&threads=` → `{"state","breakpoints",...}`; when stopped also `stop_reason`, backtrace, frame-0 locals |
| POST | `/debug/sessions/{id}/breakpoints` | `{"spec":"File.swift:42"}` → `{"id","resolved","locations",...}` |
| GET | `/debug/sessions/{id}/breakpoints` | list breakpoints with hit counts |
| DELETE | `/debug/sessions/{id}/breakpoints/{bpid}` | remove one breakpoint |
| POST | `/debug/sessions/{id}/continue` | resume until the next breakpoint (poll state) |
| POST | `/debug/sessions/{id}/pause` | interrupt a running process |
| POST | `/debug/sessions/{id}/step` | `{"kind":"in"\|"over"\|"out"}` → new frame |
| POST | `/debug/sessions/{id}/eval` | `{"expr":"(int)1+2","frame_id"?}` → `{"value","summary","type","description"}` |
| GET | `/debug/sessions/{id}/output` | captured stdout/stderr ring buffer |
| DELETE | `/debug/sessions/{id}` | `?kill=false` — detach (app keeps running) or kill |

Debug errors return 400 `{"detail"}`; unknown sessions 404; missing real-device
prerequisites 409 `{"detail","error":"capability_missing","commands":[...]}` with the
exact commands to run. Sessions idle for 10 minutes are detached automatically.

## WebSocket

`ws://127.0.0.1:8930/api/v1/devices/{id}/stream`

Server pushes binary JPEG frames (one WebSocket binary message per frame) at ~5–10 fps. Client sends nothing; close to stop.

## MCP server

`openmob mcp` runs a stdio MCP server exposing tools mirroring the REST surface: `list_devices`, `get_screenshot`, `tap`, `swipe`, `input_text`, `press_key`, `install_app`, `uninstall_app`, `list_apps`, `launch_app`.

Debugger tools (one session per device, addressed by `device_id`): `debug_attach`, `debug_breakpoint` (`op`: add/remove/list), `debug_step` (`kind`: in/over/out/continue/pause), `debug_eval`, `debug_state`, `debug_detach`. See [DEBUGGING.md](DEBUGGING.md).

## CLI

- `openmob serve` — start HTTP/WS server on port 8930 (`--port` to override)
- `openmob mcp` — start MCP stdio server
- `openmob devices` — print detected devices
