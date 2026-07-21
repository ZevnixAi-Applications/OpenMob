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

All action endpoints return `{"ok":true}` or HTTP 4xx/5xx with `{"detail":"..."}`.

Virtual devices are Android AVDs and iOS Simulators defined on this machine; once
booted they appear in `/devices` like any other device (`device_id` is the adb serial /
simulator UDID). See `docs/VIRTUAL_DEVICES.md`.

## WebSocket

`ws://127.0.0.1:8930/api/v1/devices/{id}/stream`

Server pushes binary JPEG frames (one WebSocket binary message per frame) at ~5–10 fps. Client sends nothing; close to stop.

## MCP server

`openmob mcp` runs a stdio MCP server exposing tools mirroring the REST surface: `list_devices`, `get_screenshot`, `tap`, `swipe`, `input_text`, `press_key`, `install_app`, `uninstall_app`, `list_apps`, `launch_app`, `list_virtual_devices`, `launch_virtual_device`.

## CLI

- `openmob serve` — start HTTP/WS server on port 8930 (`--port` to override)
- `openmob mcp` — start MCP stdio server
- `openmob devices` — print detected devices
