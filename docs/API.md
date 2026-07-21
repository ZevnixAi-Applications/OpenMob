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

## WebSocket

`ws://127.0.0.1:8930/api/v1/devices/{id}/stream`

Server pushes binary JPEG frames (one WebSocket binary message per frame) at ~5–10 fps. Client sends nothing; close to stop.

`ws://127.0.0.1:8930/api/v1/devices/{id}/logs/stream?filter=str`

Server pushes log lines as text messages (one line per message) as they appear. `filter` is an optional case-insensitive substring match. Client sends nothing; close to stop.

## MCP server

`openmob mcp` runs a stdio MCP server exposing tools mirroring the REST surface: `list_devices`, `get_screenshot`, `tap`, `swipe`, `input_text`, `press_key`, `install_app`, `uninstall_app`, `list_apps`, `launch_app`, plus developer tools: `get_logs`, `save_screenshot`, `get_crash_logs`, `open_url`, `clear_app_data`, `force_stop`, `push_file`, `pull_file`, `device_info`, `flutter_vm_service`, `flutter_hot_reload`.

## CLI

- `openmob serve` — start HTTP/WS server on port 8930 (`--port` to override)
- `openmob mcp` — start MCP stdio server
- `openmob devices` — print detected devices
