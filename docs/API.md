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
| GET | `/virtual-devices` | `[{"name","platform":"android"\|"ios","kind":"avd"\|"simulator","state":"running"\|"stopped","device_id":str\|null}]` |
| POST | `/virtual-devices/launch` | `{"name":"Pixel_7"}` → `{"ok":true,"note":"booting"\|"already running"}` (idempotent) |

### Developer tools (see docs/DEVTOOLS.md)

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/devices/{id}/logs` | `?lines=200&filter=str` → `{"logs":"..."}` (recent snapshot; filter = case-insensitive substring) |
| POST | `/devices/{id}/screenshot/save` | `{"path":"/abs/path.png"}` → `{"ok":true,"path":"..."}` (writes PNG on the engine host, creates dirs) |
| GET | `/devices/{id}/crashes` | `?limit=5` → recent app crash summaries, newest first |
| POST | `/devices/{id}/open_url` | `{"url":"myapp://deep/link"}` |
| POST | `/devices/{id}/clear_data` | `{"package":"com.example.app"}` (Android only; iOS → 502) |
| POST | `/devices/{id}/force_stop` | `{"package":"com.example.app"}` |
| POST | `/devices/{id}/push` | `{"local_path","device_path"}` (paths on the engine host / device) |
| POST | `/devices/{id}/pull` | `{"device_path","local_path"}` |
| GET | `/devices/{id}/info` | battery %, OS version, model, … |
| GET | `/devices/{id}/flutter/vm-service` | `{"url","device_url","devtools_hint"}` (Android, debug Flutter app) |
| POST | `/devices/{id}/flutter/hot-reload` | `{"success","isolates":[...],"vm_service_url"}` |

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

## Virtual devices

The `/virtual-devices` endpoints (listed in the REST table above) launch AVDs/simulators.
Virtual devices are Android AVDs and iOS Simulators defined on this machine; once
booted they appear in `/devices` like any other device (`device_id` is the adb serial /
simulator UDID). See `docs/VIRTUAL_DEVICES.md`.

## WebSocket

`ws://127.0.0.1:8930/api/v1/devices/{id}/stream`

Server pushes binary JPEG frames (one WebSocket binary message per frame). Client sends nothing; close to stop.

- **iOS**: frames are relayed from WDA's MJPEG screen stream (see docs/IOS.md), capped at ~15 fps; only the newest frame is sent, stale frames are dropped. If the MJPEG stream is unavailable, the server falls back to screenshot polling (~1 fps in practice).
- **Android** (and the iOS fallback): screenshot-poll loop at up to ~8 fps.

The wire contract is identical in all cases: binary JPEG messages, no metadata.

`ws://127.0.0.1:8930/api/v1/devices/{id}/logs/stream?filter=str`

Server pushes log lines as text messages (one line per message) as they appear. `filter` is an optional case-insensitive substring match. Client sends nothing; close to stop.

## MCP server

`openmob mcp` runs a stdio MCP server exposing tools mirroring the REST surface: `list_devices`, `get_screenshot`, `tap`, `swipe`, `input_text`, `press_key`, `install_app`, `uninstall_app`, `list_apps`, `launch_app`, `list_virtual_devices`, `launch_virtual_device`, plus developer tools: `get_logs`, `save_screenshot`, `get_crash_logs`, `open_url`, `clear_app_data`, `force_stop`, `push_file`, `pull_file`, `device_info`, `flutter_vm_service`, `flutter_hot_reload`.

Debugger tools (one session per device, addressed by `device_id`): `debug_attach`, `debug_breakpoint` (`op`: add/remove/list), `debug_step` (`kind`: in/over/out/continue/pause), `debug_eval`, `debug_state`, `debug_detach`. See [DEBUGGING.md](DEBUGGING.md).

## CLI

- `openmob serve` — start HTTP/WS server on port 8930 (`--port` to override)
- `openmob mcp` — start MCP stdio server
- `openmob devices` — print detected devices
