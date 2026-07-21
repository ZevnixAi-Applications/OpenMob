# Virtual Devices (Android AVDs + iOS Simulators)

The engine can list, create, and boot the device images defined on this machine, and
control booted iOS Simulators as first-class devices. Android emulators need no special
handling once booted — they show up through adb like physical devices.

## Listing and launching

- `GET /api/v1/virtual-devices` returns every launchable image:
  Android AVDs (`emulator -list-avds`, run state matched to serials via
  `adb -s <serial> emu avd name`) and iOS Simulators
  (`xcrun simctl list devices --json`, unavailable ones skipped).
- `POST /api/v1/virtual-devices/launch {"name": ..., "windowed": false}` boots one,
  idempotently, **headless by default** so the device mirrors inside OpenMob rather
  than in a separate native window:
  - AVD: spawns a detached `emulator -avd NAME -no-window -no-boot-anim`; returns
    `{"ok":true,"note":"booting"}` immediately (first boot can take minutes). It still
    registers with adb, and OpenMob mirrors it via its screen stream.
  - Simulator: `xcrun simctl boot UDID` only (no `open -a Simulator`); OpenMob drives
    it through WDA + `simctl io screenshot`.
  - `"windowed": true` restores the platform's own window (emulator UI / Simulator.app).
  - Already-running targets return `{"ok":true,"note":"already running"}`.

Once booted, the device appears in `GET /devices` via the normal 5s polling —
AVDs as `android` (adb serial like `emulator-5554`), simulators as `ios` (UDID). The
desktop app auto-opens a just-launched device as a tab as soon as it comes online, so
the mirror shows up inside OpenMob without an extra click.
The MCP server mirrors this with `list_virtual_devices` / `launch_virtual_device`,
and the desktop app shows a "Virtual Devices" sidebar section with launch buttons.

Requirements: Android SDK at `$ANDROID_HOME` (or `~/Library/Android/sdk`) for AVDs;
Xcode for simulators. Missing tooling just means that platform's list is empty.

## Creating new devices

- `GET /api/v1/virtual-devices/create-options` reports what can be created on this
  machine: `{android: {available, reason, device_profiles, system_images}, ios:
  {available, reason, device_types, runtimes}}`.
  - Android: `sdkmanager --list` (system images, split installed vs available) and
    `avdmanager list device` (hardware profiles like `pixel_7`). `available` is false
    with a `reason` when the SDK command-line tools are missing.
  - iOS: `xcrun simctl list devicetypes/runtimes --json`; `available` is false when
    Xcode is absent or no runtime is installed.
- `POST /api/v1/virtual-devices/create` starts a creation **job** and returns its
  snapshot (`{id, platform, name, status, progress, log, error, device_id}`) without
  blocking:
  - Android `{platform, name, device_profile, system_image}`: if the chosen
    `system-images;...` package is not installed it is downloaded first
    (`sdkmanager`, licenses auto-accepted), then `avdmanager create avd`. The download
    can take minutes, so `progress` (0-100) and a `log` tail stream while it runs.
  - iOS `{platform, name, device_type, runtime}`: `xcrun simctl create` — fast, no
    download when the runtime is present.
- `GET /api/v1/virtual-devices/create/jobs/{id}` returns the job snapshot for polling.

The MCP server exposes `get_create_options` and `create_virtual_device`. In the desktop
app, the "+ New" button in the VIRTUAL DEVICES sidebar header opens a create dialog
(platform toggle, name, profile + image/runtime dropdowns) that polls the job and shows
download progress; the new (stopped) device then appears in the list via polling.

## Simulator control architecture

Physical iPhones use a single WDA URL (`OPENMOB_WDA_URL`, default
`http://127.0.0.1:8100` via usbmux forward — see `docs/IOS.md`; unchanged, still
first-real-device-only). Simulators extend that design with a **per-device WDA
registry** (`openmob/sim.py`):

```
GET  /devices/{udid}/screenshot ──> xcrun simctl io UDID screenshot   (fast path, no WDA)
POST /devices/{udid}/tap        ──> WDA on 127.0.0.1:<port>           (port 8101+, per sim)
```

- **Screenshots & geometry** use `simctl` only, so listing devices and streaming
  never requires WDA. Screen size in pixels comes from the screenshot PNG header;
  the pixel→point scale (WDA speaks points) is derived from WDA's
  `/window/size` on first input.
- **Input** (tap/swipe/text/keys) goes through a WebDriverAgent instance running
  *inside the simulator*. Simulators share the Mac's network stack, so WDA is
  reachable on localhost directly — no forwarding.
- **App management** uses `simctl install/uninstall/launch/listapps`.

### The WDA registry

`SimWdaRegistry` assigns each simulator UDID a stable port starting at **8101**
(skipping ports that are already in use), builds WDA once, and starts/tracks one
`xcodebuild` subprocess per simulator:

1. **Checkout**: `runner/ios/WebDriverAgent` (gitignored; override with
   `OPENMOB_WDA_DIR`). Clone if absent:
   `git clone https://github.com/appium/WebDriverAgent.git runner/ios/WebDriverAgent`
2. **Build once** (no signing needed for simulators), into the scratch
   derivedData `runner/ios/WebDriverAgent/sim-build`:
   `xcodebuild -project WebDriverAgent.xcodeproj -scheme WebDriverAgentRunner
   -sdk iphonesimulator -destination "generic/platform=iOS Simulator"
   -derivedDataPath sim-build CODE_SIGNING_ALLOWED=NO build-for-testing`
3. **Run per simulator**, detached:
   `xcodebuild ... -destination "id=<sim-udid>" -derivedDataPath sim-build
   test-without-building` with `TEST_RUNNER_USE_PORT=<port>` in the environment.
   xcodebuild forwards `TEST_RUNNER_*` variables into the test runner with the
   prefix stripped, and WDA reads `USE_PORT`
   (`WebDriverAgentLib/Utilities/FBConfiguration.m`).
4. **Health**: `GET http://127.0.0.1:<port>/status` — the registry waits up to
   120s for it after spawning, and reuses any WDA already answering on the port.

All of this happens lazily on the first *input* action against a booted
simulator; the first tap therefore takes a few extra seconds (or minutes on the
very first run, which builds WDA). Shutting the simulator down ends its
XCUITest session and the tracked `xcodebuild` exits.

## Notes / limitations

- AVD `state` only becomes `running` once the guest's adbd is up; a cold first
  boot of a Play Store image can sit at `stopped` (adb `offline`) for minutes.
- The same AVD cannot be booted twice; launch is a no-op if it is running.
- Simulator `logs()` is not implemented yet.
- WDA runner processes are tracked per engine process; a WDA left running by a
  previous engine is reused if it still answers on its port.
