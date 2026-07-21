# Getting Started with OpenMob

This guide takes you from a fresh checkout to controlling a device — as a person
through the desktop app and CLI, or as an AI agent through MCP.

- [Prerequisites](#prerequisites)
- [Install the engine](#install-the-engine)
- [Your first Android device](#your-first-android-device)
- [Your first iOS device](#your-first-ios-device)
- [Run the desktop app](#run-the-desktop-app)
- [Use the CLI](#use-the-cli)
- [Wire up the MCP server](#wire-up-the-mcp-server)
- [Troubleshooting](#troubleshooting)

## Prerequisites

OpenMob runs on **macOS**.

| Tool | Needed for | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | The engine (required) | Installs Python 3.12 automatically. `brew install uv`. |
| `adb` (Android SDK platform-tools) | Android devices/emulators | `brew install --cask android-platform-tools`, or the Android SDK. |
| [Flutter](https://docs.flutter.dev/get-started/install) (stable) | The desktop app; Flutter run-mode | Optional if you only use the engine + MCP. |
| Xcode | iOS devices, simulators, the macOS app build | From the App Store. Simulators and the iOS lldb debugger need it. |
| `ffmpeg` | Android low-latency video mirror | `brew install ffmpeg`. Without it, Android falls back to screenshot polling. |

You only need the tools for the platforms you actually use. The engine runs with
just `uv`; adb-less machines simply won't see Android devices, and so on.

## Install the engine

```sh
git clone https://github.com/ZevnixAi-Applications/OpenMob.git
cd OpenMob/engine
uv sync                     # creates .venv and installs dependencies
uv run openmob serve        # HTTP/WebSocket API on http://127.0.0.1:8930
```

`openmob serve` also advertises the engine over mDNS (`_openmob._tcp`) so the app
can discover engines on your network. Leave it running; open a second terminal for
the commands below.

Sanity check:

```sh
curl http://127.0.0.1:8930/api/v1/health     # {"status":"ok","version":"0.1.0"}
```

## Your first Android device

1. On the phone, enable **Developer options** (Settings → About phone → tap *Build
   number* 7 times), then turn on **USB debugging**.
2. Connect the phone by USB and tap **Allow** on the "Allow USB debugging?" prompt.
3. Verify the host sees it:

   ```sh
   adb devices                 # your serial should be listed as "device"
   uv run openmob devices      # OpenMob should list it too
   ```

That's it — no on-device app is required for Android. The engine uses `adb` for
input, screen capture, logs, and app management.

Android emulators (AVDs) work the same way once booted; you can also list, create,
and launch them from OpenMob — see [VIRTUAL_DEVICES.md](VIRTUAL_DEVICES.md).

## Your first iOS device

iOS needs more setup than Android because Apple requires a signed **WebDriverAgent
(WDA)** runner on the phone for input injection. The full, verified walkthrough is
in **[IOS.md](IOS.md)**; the short version:

1. On the iPhone: **Trust** this Mac, enable **Developer Mode** (Settings → Privacy
   & Security → Developer Mode), and turn on **Enable UI Automation** (Settings →
   Developer).
2. Build and install WDA once with the helper script (needs an Apple Developer team
   configured in Xcode):

   ```sh
   scripts/setup-wda.sh [UDID]
   ```

3. Start WDA and forward its ports over usbmux (no sudo, no tunnel):

   ```sh
   uvx pymobiledevice3 usbmux forward 8100 8100 &   # WebDriver commands
   uvx pymobiledevice3 usbmux forward 9100 9100 &   # MJPEG screen stream
   ```

4. `uv run openmob devices` should now show the iPhone as controllable.

> **iOS simulators** are much simpler: boot one (via Xcode or
> `xcrun simctl boot <UDID>`, or straight from OpenMob) and it appears
> automatically. Input uses a per-simulator WDA that OpenMob builds and starts on
> the first tap, so the very first interaction takes a few extra seconds.

Read [IOS.md](IOS.md) before your first physical-device run — provisioning and
Developer Mode are the usual snags.

## Run the desktop app

```sh
cd app
flutter pub get
flutter run -d macos
```

The app connects to the engine at `http://127.0.0.1:8930` by default. It can also
**discover engines on your network** (the sidebar's engine-settings dialog) via
mDNS, which is handy when the engine runs on a different Mac.

In the app you can:

- click a device in the sidebar to mirror and control it (click-to-tap, drag to
  swipe, type into the toolbar, hardware-key buttons);
- open several devices as **tabs**, or a **split** view side by side, with an
  optional **sync-input** mode that mirrors your gestures to every pane;
- open the **Logs** panel (scope: foreground app / a specific app / whole device,
  plus a "Flutter only" toggle and a filter);
- launch and create **virtual devices** from the sidebar.

## Use the CLI

```sh
openmob serve       # start the HTTP/WebSocket API (--port, --host, --no-mdns)
openmob mcp         # start the MCP stdio server (for AI agents)
openmob devices     # print detected devices and exit
```

Run them through uv from the `engine/` directory (`uv run openmob …`) unless you
have installed the package onto your `PATH`.

Flags for `serve`:

- `--port <n>` — listen on a different port (default `8930`).
- `--host 0.0.0.0` — allow LAN clients (there is no auth in v0, so only do this on
  a trusted network).
- `--no-mdns` — disable mDNS advertising.

## Wire up the MCP server

`openmob mcp` speaks the Model Context Protocol over stdio, so any MCP client can
drive your devices. Use an **absolute path** to your `engine/` directory.

### Claude Code

```sh
claude mcp add openmob -- uv run --project /absolute/path/to/OpenMob/engine openmob mcp
```

### Claude Desktop (or any MCP client using a JSON config)

Add to the client's MCP config file:

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

Restart the client, then ask the agent to *list devices*, *take a screenshot*,
*tap*, *read the app's logs*, and so on. The full tool list is in the
[project README](../README.md#mcp--ai-agents) and [API.md](API.md).

> The MCP server and the HTTP server share one engine and one device abstraction —
> you can run the app and an agent against the same devices at the same time.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `openmob devices` shows nothing (Android) | `adb devices` first — approve the USB-debugging prompt on the phone; try a different cable/port; `adb kill-server && adb start-server`. |
| Android screen mirror is black or laggy | Install `ffmpeg` (`brew install ffmpeg`) for the H.264 pipeline; without it OpenMob falls back to ~8 fps screenshot polling. Force polling with `OPENMOB_ANDROID_STREAM=poll`. |
| iPhone not listed | Confirm `xcrun devicectl list devices` shows **connected** (not just "paired"), Developer Mode is on, and the Mac is trusted. See [IOS.md](IOS.md). |
| iOS taps do nothing / screen won't mirror | WDA isn't running or its ports aren't forwarded. Re-run the `usbmux forward` commands and `curl http://127.0.0.1:8100/status`. |
| iOS simulator's first tap hangs for a while | Expected — OpenMob builds and starts WDA for the simulator on first input. Later taps are fast. |
| `flutter not found` on Flutter run tools | Add `flutter` to `PATH`, or set `OPENMOB_FLUTTER` / `OPENMOB_DART` to the binaries. |
| MCP server doesn't appear in the client | Use an absolute `--project` path to `engine/`, confirm `uv` is on `PATH`, then restart the client. Test manually with `uv run --project /path/to/engine openmob mcp`. |
| Port 8930 already in use | `openmob serve --port <other>` (and point the app's engine settings at it). |

More platform-specific detail lives in [IOS.md](IOS.md), [DEVTOOLS.md](DEVTOOLS.md),
and [VIRTUAL_DEVICES.md](VIRTUAL_DEVICES.md).
</content>
