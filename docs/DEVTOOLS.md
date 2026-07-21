# OpenMob Developer Tools

The engine's developer-tools pack: device logs, crash reports, everyday app verbs, file transfer, device info, and Flutter debugging. Everything is exposed three ways — REST (`/api/v1`, see docs/API.md), MCP tools (`openmob mcp`), and where noted, the desktop app UI.

## Logs

- **Snapshot** — `GET /devices/{id}/logs?lines=N&filter=str` / MCP `get_logs(device_id, lines, filter)`.
  - Android: `adb logcat -d -t N`. When a filter is set the engine over-fetches, then keeps the last N matching lines. Filtering is a case-insensitive substring match, applied server-side.
  - iOS: captures ~3 seconds of `pymobiledevice3 syslog live` output (iOS has no dump-the-ring-buffer equivalent over usbmux), then filters/trims the same way. Works over plain usbmux — no sudo, no tunnel.
- **Live tail** — `WS /devices/{id}/logs/stream?filter=str`, one log line per text message.
  - Android: `adb logcat -T 1` subprocess (starts at "now", no buffer replay).
  - iOS: `pymobiledevice3 syslog live` subprocess (`PYTHONUNBUFFERED=1` so lines arrive promptly).
- **UI**: the desktop app has a collapsible "Logs" panel under the device screen with a filter box, pause, and clear. It only connects while expanded.

## Screenshots to disk

`POST /devices/{id}/screenshot/save {"path":"/abs/out.png"}` / MCP `save_screenshot(device_id, path)` writes the PNG to the given absolute path on the engine host (parent directories are created) and returns the path. Relative paths are rejected.

## Crash reports

`GET /devices/{id}/crashes?limit=N` / MCP `get_crash_logs(device_id, limit)` — newest first.

- **Android**: parses `dumpsys dropbox --print data_app_crash`; if dropbox has no entries, falls back to the `logcat -b crash` buffer. Each entry: `{date, process, exception}` (first line of the stack).
- **iOS**: `pymobiledevice3 crash ls`, then pulls the newest N `.ips` files and parses the headline. Each entry: `{name, bundle, app_name, date, os_version, exception_type, signal, termination_reason}`. An `.ips` file is a one-line JSON header followed by a JSON body; some report types (Jetsam, spin dumps) lack the `exception` block, so those fields come back empty.

## Daily verbs

| Verb | Android | iOS |
|---|---|---|
| `open_url` | `am start -a android.intent.action.VIEW -d URL` | WDA `POST /session/{id}/url` (creates a WDA session; live-untested) |
| `clear_app_data` | `pm clear` | not supported — returns a clear `DeviceError` (uninstall + reinstall instead) |
| `force_stop` | `am force-stop` | WDA `/wda/apps/terminate` (session-based; live-untested) |
| `push_file` / `pull_file` | `adb push` / `adb pull` | AFC. Plain paths live under `/var/mobile/Media`; `bundle.id:/path` targets that app's container via house arrest (`pymobiledevice3 apps push/pull`). Container access requires the app to be installed with a debuggable/dev profile on some iOS versions. |
| `device_info` | `getprop` (OS, SDK, model, manufacturer) + `dumpsys battery` | lockdown values (ProductVersion, ProductType, DeviceName, BuildVersion) + `com.apple.mobile.battery` domain |

REST names: `open_url`, `clear_data`, `force_stop`, `push`, `pull`, `info` (see docs/API.md).

## Flutter debugging (Android)

A debug-mode Flutter app logs `The Dart VM service is listening on http://127.0.0.1:PORT/TOKEN=/` on startup.

- `GET /devices/{id}/flutter/vm-service` / MCP `flutter_vm_service(device_id)` finds the most recent such line in logcat, runs `adb forward tcp:0 tcp:PORT`, and returns:
  - `url` — host-reachable VM service URL (open it in Dart DevTools: `dart devtools`, or `dart devtools --machine` from tooling)
  - `device_url` — the original on-device URL
- `POST /devices/{id}/flutter/hot-reload` / MCP `flutter_hot_reload(device_id)` connects to the VM service WebSocket (`<url>ws`), calls `getVM`, and runs `reloadSources` for every isolate. Response: `{"success", "isolates": [{"isolate", "success", "reason"?}], "vm_service_url"}`.

Caveat found during live verification: hot reload requires the app to have been started by `flutter run` (which hosts the incremental kernel compiler). An APK that was `flutter build apk --debug` + installed + launched exposes a working VM service (RPCs like `getVersion` succeed) but `reloadSources` fails with `Error while starting Kernel isolate task` — the engine surfaces that reason in the response.

iOS: VM service detection is not implemented (device syslog does not carry the Flutter banner the same way; use `flutter attach`). The endpoint returns a clear `DeviceError` on iOS devices.

## Manual iOS commands (fallbacks)

If the engine can't reach the device services, these are the equivalents it runs under the hood:

```sh
pymobiledevice3 syslog live --udid <UDID>          # live logs
pymobiledevice3 crash ls --udid <UDID>             # list crash reports
pymobiledevice3 crash pull -m '<regex>' <outdir>   # pull matching reports
pymobiledevice3 afc pull/push …                    # /var/mobile/Media files
pymobiledevice3 apps pull/push <bundle> …          # app container files
```
