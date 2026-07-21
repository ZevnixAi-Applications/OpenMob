# OpenMob on Windows

OpenMob runs on **Windows 10/11 (x64)** as an **Android** device lab — control
real Android phones and emulators from your PC, with the live mirror, app-scoped
logs, crash reports, Flutter run-mode, and the MCP server all working.

> **iOS is not available on Windows.** Controlling an iPhone needs Xcode to build
> and sign WebDriverAgent, and `xcrun`/`simctl`/lldb are macOS-only tools. On
> Windows, iOS devices and simulators don't appear, and any iOS-specific call
> returns a clear "requires macOS" error. iOS support requires a Mac.

There are two ways to run OpenMob on Windows: install the packaged app from a
**Release**, or run it **from source**. Both need the engine running locally and
an Android device with USB debugging enabled.

---

## Prerequisites

| Tool | Why | How to install |
| --- | --- | --- |
| **Android platform-tools** (`adb`) | Talk to Android devices/emulators | [Download the standalone zip](https://developer.android.com/tools/releases/platform-tools), unzip, and add the folder to your `PATH` — or set `ANDROID_HOME`/`ANDROID_SDK_ROOT`. The engine also auto-detects `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`. |
| **uv** | Runs the Python engine | `winget install astral-sh.uv` — or `powershell -c "irm https://astral.sh/uv/install.ps1 \| iex"` |
| **ffmpeg** *(optional)* | Low-latency Android video mirror | `choco install ffmpeg`, or add an ffmpeg build to `PATH`. Without it, the mirror falls back to screenshot polling. |
| **Flutter + Visual Studio 2022** *(source builds only)* | Build the desktop app on Windows | [Flutter for Windows](https://docs.flutter.dev/get-started/install/windows) + Visual Studio 2022 with the **"Desktop development with C++"** workload, then `flutter config --enable-windows-desktop`. Not needed if you install the packaged app. |

---

## Option A — Install from a Release (recommended)

Use this once a Windows installer has been published on the
[Releases](https://github.com/ZevnixAi-Applications/OpenMob/releases/latest) page.

1. **Install the app.** Download `OpenMob-<version>-windows-setup.exe` and run it.
   It installs to Program Files and adds a Start Menu shortcut.
2. **Install `adb`** (see Prerequisites) so the engine can reach Android devices.
3. **Install `uv` and start the engine** in PowerShell:

   ```powershell
   winget install astral-sh.uv
   git clone https://github.com/ZevnixAi-Applications/OpenMob.git
   cd OpenMob\engine
   uv run openmob serve            # HTTP/WebSocket API on 127.0.0.1:8930
   ```

   > On Windows the app has **no "Start engine" button** (that's macOS-only) — run
   > `openmob serve` yourself and leave it running.
4. **Launch OpenMob** from the Start Menu. It connects to the engine at
   `127.0.0.1:8930` by default (and can also discover it over mDNS). See
   [Connect a device](#connect-a-device).

> The Windows installer is produced by CI on a Windows runner. If the Releases
> page has no `-windows-setup.exe` yet, the workflow hasn't been added/run — see
> [Building the Windows installer](#building-the-windows-installer), or use
> Option B in the meantime.

---

## Option B — Run from source

Works today without a published installer. Needs Flutter + Visual Studio (see
Prerequisites).

```powershell
# 1. Get the code
git clone https://github.com/ZevnixAi-Applications/OpenMob.git
cd OpenMob

# 2. Start the engine (first terminal)
cd engine
uv run openmob serve            # 127.0.0.1:8930

# 3. Build & run the app (second terminal)
cd ..\app
flutter pub get
flutter run -d windows          # or: flutter build windows --release
```

`flutter build windows --release` produces a portable build under
`app\build\windows\x64\runner\Release\` (`openmob.exe` plus its DLLs) that you can
zip and copy to another PC.

---

## Connect a device

1. On the Android phone: **Settings → About phone →** tap **Build number** 7×
   to unlock Developer Options, then **Settings → Developer options → USB
   debugging** on.
2. Plug the phone in over USB and accept the **"Allow USB debugging?"** prompt.
3. Confirm the PC sees it:

   ```powershell
   adb devices
   ```

4. The device appears in OpenMob's sidebar — click it to mirror and control.

To use an emulator instead, boot an AVD (Android Studio's Device Manager, or the
**Virtual Devices** section inside OpenMob) and it shows up the same way.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| App says "Engine offline" | The engine isn't running or is on another port. Start `openmob serve` and check `http://127.0.0.1:8930/api/v1/health` in a browser. |
| `adb` not found | Add platform-tools to `PATH`, or set `ANDROID_HOME`. Test with `adb version`. |
| Device not listed | Re-check USB debugging, accept the on-device prompt, try a different cable/port, and run `adb kill-server; adb devices`. |
| Mirror is choppy | Install `ffmpeg` and put it on `PATH` for the H.264 video stream. |
| Engine can't be reached from another PC | Start it with `openmob serve --host 0.0.0.0` and allow the port through Windows Firewall (LAN only — there's no auth in v0). |

---

## Building the Windows installer

The packaged `.exe` is built by GitHub Actions on a Windows runner — you don't
need a Windows machine to produce it.

1. Add the workflow to the repo: copy `ci-workflows/release.yml` into
   `.github/workflows/release.yml` (use GitHub's **Add file → Create new file**
   web editor). The installer is defined by `installer/windows/openmob.iss`
   (Inno Setup).
2. Publish a release. CI builds the app on `windows-latest`, packages it with Inno
   Setup, and attaches `OpenMob-<version>-windows-setup.exe` to that release
   (alongside the macOS `.dmg`).

---

See [Getting started](GETTING_STARTED.md) for the full cross-platform guide and
[Architecture](ARCHITECTURE.md) for how the engine and app fit together.
