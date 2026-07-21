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

All action endpoints return `{"ok":true}` or HTTP 4xx/5xx with `{"detail":"..."}`.

## WebSocket

`ws://127.0.0.1:8930/api/v1/devices/{id}/stream`

Server pushes binary JPEG frames (one WebSocket binary message per frame) at ~5–10 fps. Client sends nothing; close to stop.

## MCP server

`openmob mcp` runs a stdio MCP server exposing tools mirroring the REST surface: `list_devices`, `get_screenshot`, `tap`, `swipe`, `input_text`, `press_key`, `install_app`, `uninstall_app`, `list_apps`, `launch_app`.

## CLI

- `openmob serve` — start HTTP/WS server on port 8930 (`--port` to override, `--host 0.0.0.0` for LAN access, `--no-mdns` to disable mDNS advertising)
- `openmob mcp` — start MCP stdio server
- `openmob devices` — print detected devices
