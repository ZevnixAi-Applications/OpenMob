# Virtual Devices (Android AVDs + iOS Simulators)

The engine can list and boot the device images defined on this machine, and control
booted iOS Simulators as first-class devices. Android emulators need no special
handling once booted — they show up through adb like physical devices.

## Listing and launching

- `GET /api/v1/virtual-devices` returns every launchable image:
  Android AVDs (`emulator -list-avds`, run state matched to serials via
  `adb -s <serial> emu avd name`) and iOS Simulators
  (`xcrun simctl list devices --json`, unavailable ones skipped).
- `POST /api/v1/virtual-devices/launch {"name": ...}` boots one, idempotently:
  - AVD: spawns a detached, windowed `emulator -avd NAME`; returns
    `{"ok":true,"note":"booting"}` immediately (first boot can take minutes).
  - Simulator: `xcrun simctl boot UDID` + `open -a Simulator`.
  - Already-running targets return `{"ok":true,"note":"already running"}`.

Once booted, the device appears in `GET /devices` via the normal 5s polling —
AVDs as `android` (adb serial like `emulator-5554`), simulators as `ios` (UDID).
The MCP server mirrors this with `list_virtual_devices` / `launch_virtual_device`,
and the desktop app shows a "Virtual Devices" sidebar section with launch buttons.

Requirements: Android SDK at `$ANDROID_HOME` (or `~/Library/Android/sdk`) for AVDs;
Xcode for simulators. Missing tooling just means that platform's list is empty.

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
