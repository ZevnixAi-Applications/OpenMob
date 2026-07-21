# OpenMob

[![CI](https://github.com/ZevnixAi-Applications/OpenMob/actions/workflows/ci.yml/badge.svg)](https://github.com/ZevnixAi-Applications/OpenMob/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Platform](https://img.shields.io/badge/host-macOS-000000?logo=apple&logoColor=white)](#platform-support)
[![Devices](https://img.shields.io/badge/devices-Android%20%2B%20iOS-3ddc84?logo=android&logoColor=white)](#platform-support)

**Open-source mobile device control for humans and AI agents.**

OpenMob controls real Android and iOS devices — and emulators and simulators —
from your Mac. Live screen mirror, tap/swipe/type, app install, app-scoped logs
and crash reports, Flutter run-mode with genuine hot reload and DevTools, an
interactive iOS lldb debugger, and one-command virtual-device create/launch.

You drive it three ways: a **Flutter desktop app**, a **CLI**, or an **MCP
server** that lets AI agents (Claude and others) operate the phone directly.

---

## Why OpenMob

Mirroring and automating a phone from a laptop usually means gluing together
`adb`, WebDriverAgent, `pymobiledevice3`, `simctl`, screen-copy tools, and a pile
of shell scripts — or paying for a closed product that does it for you. OpenMob
packages those free, battle-tested primitives into one coherent tool with a real
UI and a first-class MCP surface, and keeps the whole thing open (MIT).

- **One abstraction, every target.** Android phones, iPhones, Android emulators,
  and iOS simulators all present the same device interface and the same API.
- **Built for AI agents, not just people.** Every capability the app has is also
  an MCP tool, so an agent can list devices, see the screen, tap, read *your
  app's* logs, and debug — over the same engine.
- **Honest about iOS.** iOS is genuinely hard; OpenMob documents exactly what is
  verified on real hardware and what still needs setup or isn't wired yet, rather
  than hiding it. See [Roadmap & limitations](#roadmap--limitations).

## Features

**Device control**
- 🖥️ Live screen mirror — low-latency H.264 video on Android, WDA MJPEG on iOS,
  with automatic fallbacks so a device never goes blank.
- 👆 Tap, swipe, type, and hardware keys (home / back / power / volume / enter).
- 📱 Multi-device view: tabs, a side-by-side split, and an optional
  synchronized-input mode that mirrors your gestures to every pane at once.

**App workflow**
- 📦 Install and uninstall `.apk` / `.ipa`, list installed apps, launch, force-stop.
- 🪵 **App-scoped logs** — see *your app's* output (including Flutter
  `print` / `debugPrint`), not a device-wide firehose, with a live tail that
  follows the app across restarts.
- 💥 Parsed crash reports, newest first (Android dropbox/logcat, iOS `.ips`).
- 🔗 Deep links, file push/pull, `clear_app_data` (Android), device info.

**Flutter developer tools**
- 🔥 `flutter run` managed by the engine, so **hot reload and hot restart are
  real** — the engine owns the kernel compiler, not just the VM service.
- 🛠️ A DevTools URL wired straight to the running app's VM service.

**iOS debugging**
- 🐞 An interactive **lldb** session over REST/MCP: attach, breakpoints, step,
  backtrace, typed locals, expression eval — fully working against the simulator.

**Virtual devices**
- 🚀 List, **create**, and boot Android AVDs and iOS simulators from OpenMob;
  headless by default so they mirror inside the app instead of a separate window.

## Quick start

### 1. Run the engine

The engine is Python, managed with [uv](https://docs.astral.sh/uv/).

```sh
git clone https://github.com/ZevnixAi-Applications/OpenMob.git
cd OpenMob/engine
uv sync
uv run openmob serve        # HTTP/WebSocket API on http://127.0.0.1:8930
```

Plug in an Android phone with **USB debugging** enabled (accept the trust
prompt), then in another terminal:

```sh
uv run openmob devices      # should list your device
```

> Android needs `adb` (Android SDK platform-tools) on your `PATH`. iOS needs a
> few more steps — see [docs/IOS.md](docs/IOS.md).

### 2a. Open the desktop app

```sh
cd ../app
flutter pub get
flutter run -d macos        # the app talks to the engine on 127.0.0.1:8930
```

Your device shows up in the sidebar; click it to mirror and control it.

### 2b. …or let an AI agent drive (MCP)

Instead of (or alongside) the app, expose the engine to an AI agent as an MCP
server — see the next section.

Full walkthrough: **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)**.

## MCP / AI agents

`openmob mcp` runs a stdio [Model Context Protocol](https://modelcontextprotocol.io)
server. Point Claude Code, Claude Desktop, or any MCP client at it and the agent
can see and drive your devices.

Add it to your MCP config (adjust the absolute path to your checkout):

```json
{
  "mcpServers": {
    "openmob": {
      "command": "uv",
      "args": [
        "run",
        "--project",
        "/absolute/path/to/OpenMob/engine",
        "openmob",
        "mcp"
      ]
    }
  }
}
```

For Claude Code you can also register it directly:

```sh
claude mcp add openmob -- uv run --project /absolute/path/to/OpenMob/engine openmob mcp
```

Then ask the agent things like *"list my devices, screenshot the phone, tap the
login button, and show me the app's last 50 log lines."*

**Tools exposed** (all addressed by `device_id` from `list_devices`):

| Group | Tools |
|---|---|
| Devices | `list_devices`, `get_screenshot`, `save_screenshot`, `device_info` |
| Input | `tap`, `swipe`, `input_text`, `press_key` |
| Apps | `install_app`, `uninstall_app`, `list_apps`, `launch_app`, `force_stop`, `clear_app_data`, `open_url` |
| Diagnostics | `get_logs`, `get_crash_logs`, `push_file`, `pull_file` |
| Flutter | `flutter_run`, `flutter_hot_reload`, `flutter_hot_restart`, `flutter_stop`, `flutter_devtools_url`, `flutter_vm_service` |
| iOS debugger | `debug_attach`, `debug_breakpoint`, `debug_step`, `debug_eval`, `debug_state`, `debug_detach` |
| Virtual devices | `list_virtual_devices`, `launch_virtual_device`, `get_create_options`, `create_virtual_device` |

Coordinates are **device pixels** everywhere. The same capabilities are also
available over plain HTTP/WebSocket — see [docs/API.md](docs/API.md).

## Architecture

```
┌──────────────────── Mac ────────────────────┐        ┌── Android device / AVD ──┐
│                                              │        │                          │
│  app/     Flutter desktop UI ────┐           │─ USB ──│ adb (screenrecord, input)│
│                                  │           │        └──────────────────────────┘
│  MCP client (Claude, …) ─────┐   │ HTTP + WS │
│                              ▼   ▼           │        ┌──── iOS device / Sim ────┐
│  engine/  Python device engine (uv)          │─ USB ──│ WebDriverAgent (XCUITest)│
│    • unified Device abstraction              │        │ pymobiledevice3 / simctl │
│    • FastAPI HTTP + WebSocket API (:8930)    │        │ devicectl (install)      │
│    • FastMCP stdio server (AI agent tools)   │        └──────────────────────────┘
│    • Android H.264 / iOS MJPEG stream relays │
└──────────────────────────────────────────────┘
```

- **`engine/`** — Python (uv). Device backends: `adb` for Android, WebDriverAgent
  + `pymobiledevice3` + `devicectl` for iPhones, `simctl` + WebDriverAgent for iOS
  simulators. Exposes a local HTTP/WebSocket API *and* an MCP server over the same
  device abstraction, and advertises itself via mDNS (`_openmob._tcp`).
- **`app/`** — Flutter macOS desktop app: device list, live mirror, click-to-tap,
  logs panel, Flutter run panel, and virtual-device create/launch.
- **`runner/`** — on-device companions. iOS: a signed WebDriverAgent XCUITest
  runner (Apple requires a signed runner for input injection). Android needs none.

Deeper dive for contributors: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

## Platform support

| Capability | Android device | Android AVD | iOS device | iOS simulator |
|---|---|---|---|---|
| Discovery | ✅ | ✅ | ✅ | ✅ |
| Screen mirror | ✅ H.264 | ✅ H.264 | ✅ WDA MJPEG¹ | ✅ simctl² |
| Tap / swipe / type / keys | ✅ | ✅ | ✅¹ | ✅ |
| Install / launch / uninstall | ✅ | ✅ | ✅ (`devicectl`) | ✅ (`simctl`) |
| App-scoped logs & tail | ✅ | ✅ | ✅ | ⚠️ not yet |
| Crash reports | ✅ | ✅ | ✅ | ✅ |
| Deep links / file transfer / info | ✅ | ✅ | ✅ | ✅ |
| `clear_app_data` | ✅ | ✅ | ⛔ Apple limitation | ⛔ |
| Flutter run + hot reload | ✅ | ✅ | ✅ (via `flutter run`) | ✅ |
| lldb interactive debug | — | — | ⚠️ transport only³ | ✅ fully working |
| Create virtual device | — | ✅ (`sdkmanager`/`avdmanager`) | — | ✅ (`simctl`) |

¹ Physical iPhones need a WebDriverAgent runner built and installed once, plus a
usbmux port forward — see [docs/IOS.md](docs/IOS.md). v0 targets the **first** iOS
device only (single WDA URL).
² iOS simulators mirror via `simctl` screenshots; input uses a per-simulator WDA
instance built and started on first tap.
³ Real-device lldb: the no-sudo tunnel transport is verified, but attaching to a
running process for a live backtrace is **not yet wired end-to-end** — see
[Roadmap & limitations](#roadmap--limitations) and [docs/DEBUGGING.md](docs/DEBUGGING.md).

## How OpenMob compares

OpenMob is honest about where it sits. It is not a test framework and it is not a
cloud device farm — it is a local, open device-control product plus an agent
surface.

| | **OpenMob** | Appium | scrcpy | Paid device-control apps |
|---|---|---|---|---|
| What it is | Product + engine + agent API | Automation toolkit/protocol | Android mirror/control | Closed product |
| Android + iOS | ✅ both | ✅ both | Android only | Usually both |
| Desktop UI | ✅ | — | ✅ | ✅ |
| AI-agent (MCP) surface | ✅ built-in | via 3rd-party wrappers | — | Varies |
| Open source | ✅ MIT | ✅ | ✅ | ⛔ |
| Cost | Free | Free | Free | Paid |

OpenMob stands on the same free, permissively licensed primitives as the paid
tools — `adb`, WebDriverAgent (BSD-3), `pymobiledevice3` — and keeps the product
layer open too. See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).

## Development

```
OpenMob/
├── engine/     Python device engine — CLI, HTTP/WS API, MCP server (uv)
├── app/        Flutter macOS desktop app
├── runner/     on-device companions (iOS WebDriverAgent runner + branding)
├── scripts/    setup-wda.sh and the end-to-end release-gate harness
├── testapp/    deterministic Flutter testbed used by the E2E gate
└── docs/        API contract, iOS setup, dev tools, architecture
```

Engine:

```sh
cd engine
uv sync
uv run openmob devices     # detected devices
uv run openmob serve       # HTTP/WS API
uv run openmob mcp         # MCP stdio server
uv run pytest              # unit tests (no device needed)
uv run ruff check .        # lint
```

App:

```sh
cd app
flutter pub get
flutter run -d macos       # needs the engine running
flutter analyze
flutter test
```

Contributions welcome — see **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## Roadmap & limitations

Deliberately honest. OpenMob is **v0.1.0, early development.**

- **iOS real-device lldb attach isn't fully wired.** The no-sudo userspace tunnel
  transport is verified, but `pymobiledevice3`'s `debugserver start-server` yields
  an *unattached* debugserver, so the engine connects with `pid 0` and cannot yet
  get a stopped process to backtrace. Simulator debugging is fully working.
  Details in [docs/DEBUGGING.md](docs/DEBUGGING.md).
- **iOS `clear_app_data` is unsupported** — Apple provides no per-app data-reset
  API. Uninstall + reinstall instead.
- **iOS control is first-device-only** (single WDA URL); multi-iPhone support is
  future work. Multiple Android devices and multiple simulators already work.
- **iOS Flutter VM-service auto-detection isn't implemented** — use `flutter_run`
  (managed) or `flutter attach`.
- **Simulator logs aren't implemented yet.**
- **No auth** in v0 — the engine binds `127.0.0.1` by default. Only pass
  `--host 0.0.0.0` on a trusted network.
- **No team / multi-user / remote-farm mode** — OpenMob is single-machine, local.
- **Host is macOS.** iOS features require Xcode; the engine leans on macOS tooling.

## Documentation

| Doc | What's in it |
|---|---|
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | Onboarding: install, first device, app, CLI, MCP |
| [docs/API.md](docs/API.md) | HTTP + WebSocket + MCP API contract |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the engine, backends, streaming, and app fit together |
| [docs/DEVTOOLS.md](docs/DEVTOOLS.md) | Logs, crash reports, daily verbs, Flutter debugging |
| [docs/DEBUGGING.md](docs/DEBUGGING.md) | Interactive iOS lldb sessions |
| [docs/VIRTUAL_DEVICES.md](docs/VIRTUAL_DEVICES.md) | Listing, creating, and booting AVDs/simulators |
| [docs/IOS.md](docs/IOS.md) | Physical-iPhone setup (WebDriverAgent + pymobiledevice3) |

## License

MIT © Zevnix AI. See [LICENSE](LICENSE) and [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md).
</content>
</invoke>
