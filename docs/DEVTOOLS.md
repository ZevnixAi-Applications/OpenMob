# OpenMob Developer Tools

The engine's developer-tools pack: device logs, crash reports, everyday app verbs, file transfer, device info, and Flutter debugging. Everything is exposed three ways — REST (`/api/v1`, see docs/API.md), MCP tools (`openmob mcp`), and where noted, the desktop app UI.

## Logs

Logs are **app-scoped by default**, not a device-wide firehose: the point is to see *your app's* output (especially Flutter `print`/`debugPrint`), not system spam. A scope is one of: a `package` (resolve the app's live pid and filter to it), an explicit `pid`, `scope=foreground` (auto-target the foreground app, Android), or none (whole device — an explicit opt-in). `flutter=true` narrows to Flutter output. All scoping params work on both the snapshot and the live tail.

- **Snapshot** — `GET /devices/{id}/logs?lines=N&filter=str[&package=&pid=&scope=foreground&flutter=true]` / MCP `get_logs(device_id, lines, filter, package, scope, flutter)`.
  - Android: `adb logcat -d -t N`. Scoped by pid via `logcat --pid=<pid>` (one flag per pid; on pre-Android-7 devices, which lack `--pid`, the engine greps the pid column instead). `flutter=true` appends the `flutter:V *:S` filterspec. A `filter` over-fetches then keeps the last N matching lines (case-insensitive substring). A scoped app that is not running returns `""`.
  - iOS (device): `pymobiledevice3 syslog live` for ~3 s (iOS has no dump-the-ring-buffer equivalent over usbmux), scoped with `--pid` or `--process-name`. Works over plain usbmux — no sudo, no tunnel.
  - iOS (simulator): `xcrun simctl spawn <udid> log show --last 30s`, scoped with an NSPredicate (`processID == <pid>` / `process == "<name>"`).
- **Live tail** — `WS /devices/{id}/logs/stream?filter=str[&package=&pid=&scope=foreground&flutter=true]`, one log line per text message.
  - Android: `adb logcat -T 1` (starts at "now", no buffer replay). **Scoped tails re-resolve the pid on a timer**, so a restarted app (new pid) is followed automatically; while the app isn't running the tail stays connected and streams nothing until it comes up.
  - iOS (device): `pymobiledevice3 syslog live [--pid|--process-name]` (`PYTHONUNBUFFERED=1` so lines arrive promptly). The process-name filter follows the app across restarts on its own.
  - iOS (simulator): `xcrun simctl spawn <udid> log stream --level debug` with the same predicate.
- **UI**: the desktop app's collapsible "Logs" panel has a **scope selector** at the top — Foreground app (Android default) / a specific installed app / Whole device — plus a **Flutter only** toggle, a filter box, pause, and clear. When the scoped app isn't running the empty state reads "Waiting for &lt;app&gt; to produce logs…". It only connects while expanded.

**iOS scoping caveat**: iOS filters by process *name* or pid, not bundle id. The engine derives the process name from the bundle id's last component (`com.acme.MyApp` → `MyApp`), which is the CFBundleExecutable for most Flutter/Xcode apps but can be wrong (e.g. Flutter's iOS target is often `Runner`); pass an explicit `pid` when the name guess misses. `scope=foreground` and the `flutter` tag are Android-only. The real-device syslog path itself is verified working without sudo; the process-scoping flags are live-untested on the read-only iPhone in this setup.

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
