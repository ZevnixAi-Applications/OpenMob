# OpenMob Architecture

How the pieces fit together, for contributors. Pair this with [API.md](API.md)
(the wire contract) and the source under `engine/src/openmob/` and `app/lib/`.

## The big picture

```
   Humans                         AI agents
     │                                │
     ▼ (Flutter desktop app)          ▼ (MCP client: Claude, …)
┌─────────────────┐            ┌──────────────────┐
│  app/  (Dart)   │            │  external client │
└────────┬────────┘            └────────┬─────────┘
         │ HTTP + WebSocket              │ MCP (stdio)
         │ 127.0.0.1:8930                │
         ▼                               ▼
┌──────────────────────────────────────────────────────┐
│  engine/  (Python, uv)                                │
│                                                        │
│   server.py (FastAPI)      mcp_server.py (FastMCP)     │
│        └──────────────┬──────────────┘                 │
│                       ▼                                 │
│              manager.py  (DeviceManager: discover/get)  │
│                       │                                 │
│      ┌────────────────┼─────────────────┐               │
│      ▼                ▼                 ▼               │
│  android.py        ios.py             sim.py            │
│  (adb)         (WDA + pymobiledevice3) (simctl + WDA)   │
│                                                        │
│  supporting: videostream.py  logstream.py  flutter.py   │
│              flutter_run.py  debugger.py + lldb_worker  │
│              virtual.py  mdns.py  device.py             │
└──────────────────────────────────────────────────────┘
         │              │                 │
      adb / USB      usbmux / USB      local sockets
         ▼              ▼                 ▼
   Android device    iPhone           iOS simulator
   / emulator        (WDA runner)     (WDA in-sim)
```

Two front doors, one core: **`server.py`** (FastAPI HTTP + WebSocket) and
**`mcp_server.py`** (FastMCP stdio) are both thin adapters over the same
`DeviceManager` and the same `Device` objects. Anything the app can do over HTTP,
an agent can do over MCP, because they call identical backend methods.

## The device abstraction

`device.py` defines the `Device` interface (and `DeviceError`) that every backend
implements: `info()`, `screenshot()`, `tap()`, `swipe()`, `input_text()`,
`press_key()`, `install_app()`, `list_apps()`, `launch_app()`, `logs()`,
`crash_reports()`, `open_url()`, `force_stop()`, `clear_app_data()`,
`push_file()` / `pull_file()`, `system_info()`, and so on.

`manager.py`'s `DeviceManager`:

- `refresh()` — polls each backend's discovery (adb serials, usbmux iPhones, booted
  simulators) and returns the current `Device` list. The server polls this every
  ~5 s; MCP `list_devices` calls it on demand.
- `get(device_id)` — returns the backend `Device` for an id (adb serial / iPhone
  UDID / simulator UDID), raising `DeviceError` if it's gone.

**Coordinates are device pixels everywhere** at the API boundary. Backends convert
internally where the underlying tool disagrees (WDA speaks *points*, so `ios.py`
and `sim.py` divide by the pixel→point scale).

### Backends

| Module | Target | Under the hood |
|---|---|---|
| `android.py` | Android phones + emulators | `adb` (`input`, `screencap`, `screenrecord`, `logcat`, `pm`, `am`, `dumpsys`, `getprop`). |
| `ios.py` | Physical iPhones | WebDriverAgent over usbmux-forwarded HTTP for input/screen; `pymobiledevice3` for syslog, crash reports, AFC/container files, device info; `xcrun devicectl` for install/launch. v0 = single WDA URL, first device only. |
| `sim.py` | iOS simulators | `simctl` for screenshots, install/launch/list; a **per-simulator WDA registry** (`SimWdaRegistry`) that assigns each UDID a port from 8101, builds WDA once, and runs one `xcodebuild` test-runner per sim for input. |
| `virtual.py` | AVDs + simulators (as *images*) | `emulator`/`avdmanager`/`sdkmanager` (Android) and `simctl` (iOS) to list, create (as async jobs), and boot — headless by default. Booted images then show up through the normal backends. |

## Streaming

Screen mirror is a WebSocket that pushes **binary JPEG frames** (one frame per
message, no metadata) at `…/devices/{id}/stream`. The wire contract is identical
across platforms; only the source differs:

- **Android** (`videostream.py`) — a low-latency H.264 pipeline:
  `adb exec-out screenrecord --output-format=h264` decoded to JPEG by `ffmpeg`, up
  to ~20 fps, newest-frame-only. An idle screen is refreshed via `screencap` ~1/s;
  the pipeline self-restarts around screenrecord's 180 s limit. Falls back to
  `screencap` polling if `ffmpeg` is missing or `screenrecord` is rejected. Force
  polling with `OPENMOB_ANDROID_STREAM=poll`.
- **iOS device** — WDA's MJPEG server (port 9100, usbmux-forwarded) relayed
  directly, capped ~15 fps, newest-frame-only; falls back to `GET /screenshot`
  polling (~1 fps) if MJPEG is unavailable. See [IOS.md](IOS.md).
- **iOS simulator** — `simctl io screenshot` polling.

The engine always keeps only the newest frame, so a slow client gets *fresher*
frames rather than a growing backlog. The REST `/screenshot` endpoint is separate
and always returns a full-resolution PNG.

Logs stream the same way but as **text messages**, one log line each
(`logstream.py`, `LogScope`) — see [DEVTOOLS.md](DEVTOOLS.md) for scoping.

## Flutter run-mode

`flutter.py` does best-effort VM-service detection + a `reloadSources` fallback
that only works for apps someone else launched via `flutter run` (an installed APK
rejects it). To make hot reload *real*, `flutter_run.py`'s `FlutterRunManager`
launches the app itself with `flutter run --machine` and drives that daemon's
line-oriented JSON protocol. Because the engine owns the process (and its kernel
compiler), `app.restart` with `fullRestart:false`/`true` is a genuine hot
reload/restart, and it can serve a DevTools URL wired to the app's VM service.

## iOS debugging

`debugger.py` (`DebugSessionManager`) manages one lldb session per device. lldb's
Python module only loads under Xcode's CPython, so each session spawns
`lldb_worker.py` via `xcrun python3` (with `sys.path` pointed at `xcrun lldb -P`)
and drives it with a JSON-lines protocol over stdin/stdout. This keeps the full
lldb SB API (structured breakpoints, typed frame values — no prompt scraping) while
isolating a crash to one session instead of the whole engine. Simulator attach is
direct; real-device attach needs a tunnel and is not fully wired — see
[DEBUGGING.md](DEBUGGING.md).

## The desktop app

`app/lib/` is a Flutter macOS app. Notable pieces:

- `api/engine_client.dart` — the HTTP/WebSocket client for the engine API.
- `api/engine_discovery.dart` — mDNS discovery of engines on the network.
- `state/app_state.dart` — app state: devices, the active device, tab vs. `split`
  layout, and sync-input mode.
- `util/coord_sync.dart` — maps a click on the rendered mirror to device-pixel
  coordinates before sending a tap.
- `widgets/` — `device_screen` (mirror + click-to-tap), `device_grid` /
  `device_pane` / `device_tab_bar` (multi-device layout), `toolbar` (keys + text),
  `logs_panel`, `flutter_run_panel`, `sidebar`, `create_device_dialog`.

## Worked example: how a tap flows

1. **UI** — the user clicks the mirrored screen in `device_screen.dart`.
   `coord_sync.dart` converts the click position within the rendered image to
   **device-pixel** `(x, y)`.
2. **Client** — `engine_client.dart` sends `POST /api/v1/devices/{id}/tap` with
   `{"x": …, "y": …}`.
3. **Server** — `server.py`'s route handler calls `manager.get(id).tap(x, y)`.
   (An MCP agent reaches the same line via the `tap` tool in `mcp_server.py`.)
4. **Backend** — the concrete `Device` runs the platform action:
   - `android.py` → `adb shell input tap x y`;
   - `ios.py` → WDA `POST /session/{id}/wda/tap` with `(x, y)` converted to points;
   - `sim.py` → the simulator's WDA instance, same conversion.
5. The device acts; the next mirror frame reflects the change.

The reverse direction (screen, logs) flows over the WebSocket streams above.

## API surface & config

- Base URL: `http://127.0.0.1:8930/api/v1` (REST + WebSocket). No auth in v0; binds
  `127.0.0.1` unless `--host 0.0.0.0`. Full contract in [API.md](API.md).
- mDNS (`mdns.py`): advertises `_openmob._tcp.local.` as `OpenMob Engine on
  <hostname>` with a `version` TXT record; `--no-mdns` disables it.
- Key env vars: `OPENMOB_ANDROID_STREAM`, `OPENMOB_WDA_URL`,
  `OPENMOB_WDA_MJPEG_PORT`, `OPENMOB_WDA_DIR`, `OPENMOB_FLUTTER`, `OPENMOB_DART`
  (see the relevant docs for each).
</content>
