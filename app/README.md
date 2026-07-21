# OpenMob app

Flutter client for the OpenMob engine: a device lab that mirrors and controls
Android/iOS phones exposed by an engine (`openmob serve`) over HTTP/WebSocket.

Runs on macOS (desktop layout: sidebar + device pane) and on Android/iOS
phones (device list that opens a full-screen control view). The layout is
chosen automatically from the window width (breakpoint: 700 px).

- Bundle / application id: `ai.zevnix.openmob`
- Display name: OpenMob

## Prerequisites

- Flutter (stable channel)
- An OpenMob engine reachable on the network — or use the built-in demo mode
  ("Try demo" on the connect screen), which fakes an engine with a generated
  device so the app can be exercised with no engine at all.

## Run

All commands from this `app/` directory.

### macOS

```sh
flutter run -d macos
```

The engine usually runs on the same machine, so the default engine URL
(`http://127.0.0.1:8930`) works out of the box.

### Android

```sh
flutter run -d <android-device-id>   # flutter devices to list
# or build an APK:
flutter build apk --debug
```

### iOS

```sh
flutter run -d <ios-device-id>
# or build without signing:
flutter build ios --debug --no-codesign
```

On a phone, open Engine settings (gear icon) and enter the engine URL as seen
from the phone, e.g. `http://192.168.1.50:8930` — the machine running
`openmob serve` must be on the same network and the engine must listen on a
LAN-reachable interface (not just 127.0.0.1).

### Network notes

- The engine speaks plain `http`/`ws` on the LAN. Android is configured with
  `android:usesCleartextTraffic="true"`; iOS with
  `NSAppTransportSecurity > NSAllowsLocalNetworking` plus a local-network
  usage description and `_openmob._tcp` Bonjour service entry (for future
  mDNS discovery).
- On first connect iOS will ask for local-network permission — required for
  the app to reach the engine.

## Tests / checks

```sh
flutter analyze
flutter test
```
