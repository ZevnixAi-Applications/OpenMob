# OpenMob Engine API (v0)

The engine serves a local HTTP + WebSocket API for UIs, and an MCP server for AI agents. Both are thin layers over the same device abstraction.

- Base URL: `http://127.0.0.1:8930/api/v1`
- No auth in v0 (binds 127.0.0.1 by default; pass `--host 0.0.0.0` to `openmob serve` to allow LAN clients).

## mDNS discovery

`openmob serve` advertises itself over mDNS/Bonjour as an `_openmob._tcp.local.` service so apps can find engines on the local network:

- Instance name: `OpenMob Engine on <hostname>`
- Port: the serve port (default 8930)
- TXT record: `version=<engine version>`

The service is unregistered cleanly on shutdown. Disable advertising with `openmob serve --no-mdns`. Advertising is best-effort: if registration fails the API still serves. Note that discovery across devices only helps if the engine is reachable from them, i.e. it was started with `--host 0.0.0.0`.

Verify from macOS with `dns-sd -B _openmob._tcp local.`

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
| GET | `/devices/{id}/apps` | `[{"package","name"}]` — `name` is the friendly app label where resolvable (best-effort, cached), else the package id |
| POST | `/devices/{id}/launch` | `{"package":"com.example.app"}` |
| GET | `/virtual-devices` | `[{"name","platform":"android"\|"ios","kind":"avd"\|"simulator","state":"running"\|"stopped","device_id":str\|null}]` |
| POST | `/virtual-devices/launch` | `{"name":"Pixel_7","windowed":false}` → `{"ok":true,"note":"booting"\|"already running"}` (idempotent; headless unless `windowed`) |
| GET | `/virtual-devices/create-options` | `{"android":{"available","reason","device_profiles":[{"id","name"}],"system_images":[{"id","api","tag","abi","installed"}]},"ios":{"available","reason","device_types":[{"id","name"}],"runtimes":[{"id","name","available"}]}}` |
| POST | `/virtual-devices/create` | `{"platform":"android"\|"ios","name",...}` (Android: `device_profile`,`system_image`; iOS: `device_type`,`runtime`) → create-job snapshot |
| GET | `/virtual-devices/create/jobs/{id}` | `{"id","platform","name","status":"queued"\|"running"\|"succeeded"\|"failed","progress":int\|null,"log":[str],"error":str\|null,"device_id":str\|null}` |

### Developer tools (see docs/DEVTOOLS.md)

| Method | Path | Body / Notes |
|---|---|---|
| GET | `/devices/{id}/logs` | `?lines=200&filter=str` → `{"logs":"..."}` (recent snapshot; filter = case-insensitive substring). App-scope with `&package=<id>`, `&pid=<n>`, or `&scope=foreground` (Android); `&flutter=true` narrows to Flutter output. A scoped app that isn't running returns `""`. |
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
- **Android**: frames come from a low-latency H.264 video pipeline (`adb exec-out screenrecord --output-format=h264` decoded to JPEG by `ffmpeg`), relayed at up to ~20 fps while the screen is changing, newest frame only (stale frames are dropped). screenrecord only encodes on display updates, so an idle screen is refreshed via `screencap` about once per second; the first frame is also a `screencap` so clients render immediately. The pipeline restarts itself transparently around screenrecord's 180 s recording limit. If `ffmpeg` is missing or the device rejects `screenrecord`, the server falls back to `screencap` polling (~8 fps) transparently. Set `OPENMOB_ANDROID_STREAM=poll` to force the polling path (`video` is the default). Requires `ffmpeg` (Homebrew path or `PATH`).

The wire contract is identical in all cases: binary JPEG messages, no metadata. The `/screenshot` REST endpoint is unaffected: it always returns a full-resolution PNG.

`ws://127.0.0.1:8930/api/v1/devices/{id}/logs/stream?filter=str`

Server pushes log lines as text messages (one line per message) as they appear. `filter` is an optional case-insensitive substring match. Client sends nothing; close to stop.

The tail can be scoped to a single app instead of the whole device with the same params as the snapshot: `&package=<id>`, `&pid=<n>`, `&scope=foreground` (Android), and `&flutter=true`. When scoped by package, the engine resolves the app's live pid and re-resolves it periodically, so a **restarted app (new pid) is followed automatically** and the tail streams nothing (staying connected) while the app is not running.

## MCP server

`openmob mcp` runs a stdio MCP server exposing tools mirroring the REST surface: `list_devices`, `get_screenshot`, `tap`, `swipe`, `input_text`, `press_key`, `install_app`, `uninstall_app`, `list_apps`, `launch_app`, `list_virtual_devices`, `launch_virtual_device`, `get_create_options`, `create_virtual_device`, plus developer tools: `get_logs`, `save_screenshot`, `get_crash_logs`, `open_url`, `clear_app_data`, `force_stop`, `push_file`, `pull_file`, `device_info`, `flutter_vm_service`, `flutter_run`, `flutter_hot_reload`, `flutter_hot_restart`, `flutter_stop`, `flutter_devtools_url`.

Debugger tools (one session per device, addressed by `device_id`): `debug_attach`, `debug_breakpoint` (`op`: add/remove/list), `debug_step` (`kind`: in/over/out/continue/pause), `debug_eval`, `debug_state`, `debug_detach`. See [DEBUGGING.md](DEBUGGING.md).

## CLI

- `openmob serve` — start HTTP/WS server on port 8930 (`--port` to override, `--host 0.0.0.0` for LAN access, `--no-mdns` to disable mDNS advertising)
- `openmob mcp` — start MCP stdio server
- `openmob devices` — print detected devices
