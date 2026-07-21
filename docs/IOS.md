# iOS Device Control (WebDriverAgent + pymobiledevice3)

How OpenMob controls a physical iPhone from this Mac. Android uses adb; iOS uses a
WebDriverAgent (WDA) XCUITest runner installed on the phone, driven over plain HTTP,
plus `pymobiledevice3` for USB port forwarding and (when needed) the iOS 17+ tunnel.

**This machine (verified 2026-07-20):**

| Item | Value |
|---|---|
| macOS | 26.5.2 (25F84), Darwin 25.5.0 |
| Xcode | 26.3 (17C529) at `/Applications/Xcode.app` |
| Apple Developer team | `76Z3N79K53` (paid) |
| Python tooling | `uv` / `uvx` at `/opt/homebrew/bin` (run pymobiledevice3 via `uvx pymobiledevice3 ...`) |
| Known device | iPhone 12 (iPhone13,2), CoreDevice ID `86CFC315-0AA7-55FB-A0A4-126961146109` — paired, but not USB-connected at time of writing |

> The repo path contains a space (`C DRIVE`). Always quote paths in shell commands.

## Architecture

```
engine (Mac) ──HTTP──> localhost:8100 ──usbmux forward──> WDA on iPhone :8100  (commands)
engine (Mac) ──HTTP──> localhost:9100 ──usbmux forward──> WDA on iPhone :9100  (MJPEG screen stream)
```

- WDA is an XCUITest bundle (`WebDriverAgentRunner-Runner.app`) from
  [github.com/appium/WebDriverAgent](https://github.com/appium/WebDriverAgent). It runs a
  WebDriver-compatible HTTP server on port **8100** and an MJPEG screen stream on port
  **9100** (overridable via `USE_PORT` / `MJPEG_SERVER_PORT` env vars in the scheme).
- Once WDA is *running*, plain usbmux TCP forwarding is enough to talk to it — **no
  tunnel, no sudo**.
- The iOS 17+ RemoteXPC **tunnel** (tunneld) is only needed for *developer services*
  (launching the runner without Xcode, syslog, DVT instruments, etc.). See below.

## Protocol landscape (what changed, verified July 2026)

- **iOS 17 (2023):** Apple moved developer services to CoreDevice/RemoteXPC. Old
  lockdown-based tools (`ios-deploy`, `ideviceinstaller`) stopped working on iOS 17+
  physical devices. Replacements: `xcrun devicectl` (Xcode 15+) and
  `pymobiledevice3` tunnels ([ios17-tunnels guide](https://github.com/doronz88/pymobiledevice3/blob/master/docs/guides/ios17-tunnels.md)).
- **iOS 17.4+:** faster tunnel path: `sudo pymobiledevice3 lockdown start-tunnel`
  (17.0–17.3.1 must use `remote start-tunnel`).
- **iOS 16+:** Developer Mode toggle required on the phone before any of this works.
- **Xcode 26 / iOS 26:** upstream WDA had a build failure on Xcode 26 (compiler-flag
  issue) fixed in WDA **v11.4.1** / XCUITest driver 9.5.0+ (March 2026)
  ([appium/appium#21347](https://github.com/appium/appium/issues/21347)). Always build
  WDA from current `master` or a tag ≥ v11.4.1.
- **`xcrun devicectl`** fully covers install/launch/terminate on iOS 17+ (it does NOT
  support iOS ≤ 15 devices):
  `xcrun devicectl device install app --device <UDID> <path.app|ipa>` and
  `xcrun devicectl device process launch --device <UDID> <bundle-id>`
  (`--terminate-existing`, `--console` flags available).
- The iPhone 12 supports iOS 26, so expect the device to be on iOS 18 or 26.

## Step 0 — Phone preparation (one-time, needs the phone in hand)

1. Plug the iPhone into this Mac via USB. Tap **Trust** on the phone, enter passcode.
2. Enable **Developer Mode**: Settings → Privacy & Security → Developer Mode → ON.
   The phone reboots and asks to confirm. (The toggle only *appears* after the phone
   has seen a Mac with Xcode / a development request at least once — if missing, open
   Xcode → Window → Devices and Simulators with the phone connected, then re-check.)
3. After reboot: Settings → Developer → **Enable UI Automation** → ON.
4. Verify visibility:
   ```sh
   xcrun devicectl list devices                # State should be "connected"
   uvx pymobiledevice3 usbmux list --no-color  # should print a JSON entry with the UDID
   ```
   The hardware UDID for an iPhone 12 looks like `00008101-XXXXXXXXXXXXXXXX`.

## Step 1 — Get + build + install WDA

Automated (preferred):

```sh
"/Users/zevnix/Desktop/C DRIVE/Apps/OpenMob/scripts/setup-wda.sh" [UDID]
```

The script clones `appium/WebDriverAgent` into `runner/ios/WebDriverAgent` (skips if
present), builds `WebDriverAgentRunner` for the connected device signed with team
`76Z3N79K53`, and installs the runner app via `devicectl`.

It also rebrands the runner's visible UI as OpenMob (home-screen label **OM
Runner** — kept short so iOS does not truncate it):

- copies `runner/ios/branding/icon-1024.png` (regenerable with
  `uv run --with pillow python runner/ios/branding/make_icon.py <out.png>`) over
  the Appium app icon in the runner's asset catalog;
- copies `runner/ios/branding/LaunchImage.imageset` +
  `LaunchBackground.colorset` (image regenerable with `make_launch.py`) into the
  catalog and adds a `UILaunchScreen` dict (`UIColorName` = LaunchBackground,
  `UIImageName` = LaunchImage) to the **built** bundle's Info.plist, giving a
  branded dark screen when the app is opened by hand. During an active XCUITest
  session the runner paints its own black window over it — expected;
- sets `CFBundleDisplayName = OM Runner` in the source `Info.plist` and the built
  bundle, then re-signs.

This is display-layer only — `CFBundleName`, class names, and bundle structure
are left untouched (changing `CFBundleName` breaks XCTest bundle loading).
Upstream BSD-3-Clause attribution is kept in `THIRD_PARTY_LICENSES.md`; license
headers in WDA source files are not removed.

What it does, manually:

```sh
cd "/Users/zevnix/Desktop/C DRIVE/Apps/OpenMob/runner/ios"
git clone https://github.com/appium/WebDriverAgent.git

xcodebuild \
  -project WebDriverAgent/WebDriverAgent.xcodeproj \
  -scheme WebDriverAgentRunner \
  -destination "id=$UDID" \
  -derivedDataPath WebDriverAgent/build \
  -allowProvisioningUpdates \
  CODE_SIGN_STYLE=Automatic \
  DEVELOPMENT_TEAM=76Z3N79K53 \
  PRODUCT_BUNDLE_IDENTIFIER=ai.zevnix.WebDriverAgentRunner \
  build-for-testing
```

Notes:

- `PRODUCT_BUNDLE_IDENTIFIER` **must be unique per team** — the default
  `com.facebook.WebDriverAgentRunner` may collide with a profile Apple won't issue.
  We use `ai.zevnix.WebDriverAgentRunner`; Xcode appends `.xctrunner` to the installed
  runner app, so on the phone it is **`ai.zevnix.WebDriverAgentRunner.xctrunner`**.
- `-allowProvisioningUpdates` is required for automatic signing from the CLI
  (headless xcodebuild is otherwise not allowed to create/refresh profiles).
- The built app lands at
  `runner/ios/WebDriverAgent/build/Build/Products/Debug-iphoneos/WebDriverAgentRunner-Runner.app`.
- First install of an app from a new team on this phone may require trusting the
  developer certificate: Settings → General → VPN & Device Management.

## Step 2 — Start WDA on the phone

**Option A — via xcodebuild (simplest, keeps a terminal busy):**

```sh
xcodebuild \
  -project "/Users/zevnix/Desktop/C DRIVE/Apps/OpenMob/runner/ios/WebDriverAgent/WebDriverAgent.xcodeproj" \
  -scheme WebDriverAgentRunner \
  -destination "id=$UDID" \
  -derivedDataPath "/Users/zevnix/Desktop/C DRIVE/Apps/OpenMob/runner/ios/WebDriverAgent/build" \
  -allowProvisioningUpdates \
  DEVELOPMENT_TEAM=76Z3N79K53 \
  PRODUCT_BUNDLE_IDENTIFIER=ai.zevnix.WebDriverAgentRunner \
  test-without-building
```

Leave it running: `xcodebuild` is the host process that keeps the XCUITest session
alive. Success looks like `ServerURLHere->http://<phone-ip>:8100<-ServerURLHere` in
the log. (Plain `test` = build + run in one step; `test-without-building` reuses the
Step 1 build.)

**Option B — preinstalled-WDA launch (no xcodebuild at runtime):**

Modern WDA runners can be launched directly as an app (this is what Appium's
`appium:usePreinstalledWDA` does):

```sh
xcrun devicectl device process launch --terminate-existing \
  --device "$UDID" ai.zevnix.WebDriverAgentRunner.xctrunner
```

If launching through pymobiledevice3 developer services instead, a tunnel is required
first (see tunneld below). Option A is the reliable default; use B once the flow is
proven.

## Step 3 — Reach WDA from the Mac (port forwarding)

USB forwarding via usbmux — no tunnel, no sudo:

```sh
uvx pymobiledevice3 usbmux forward 8100 8100 &   # WebDriver commands
uvx pymobiledevice3 usbmux forward 9100 9100 &   # MJPEG screen stream
curl http://127.0.0.1:8100/status                 # sanity check
open http://127.0.0.1:9100                        # live screen mirror in a browser
```

(If several iPhones are attached, add `--serial "$UDID"`.)

## tunneld (iOS 17+ developer services — only when needed)

Needed for `pymobiledevice3 developer ...` commands, app launch through
testmanagerd/DVT, syslog, etc. Not needed for plain HTTP to a running WDA.

```sh
sudo uvx pymobiledevice3 remote tunneld
```

- Runs a daemon on `http://127.0.0.1:49151`; other pymobiledevice3 commands
  auto-discover it via `--tunnel ''`.
- **sudo is required** — it creates a kernel TUN interface. A slower userspace mode
  exists (no root) but the sudo daemon is the documented default.
- One-shot alternative on iOS 17.4+: `sudo uvx pymobiledevice3 lockdown start-tunnel`.

## WDA HTTP API the engine calls

Base URL `http://127.0.0.1:8100` (through the forward). JSON in/out, WebDriver-style
`{"value": ...}` envelopes.

| Purpose | Method + path | Body / notes |
|---|---|---|
| Health check | `GET /status` | also returns `sessionId` if one exists |
| Create session | `POST /session` | `{"capabilities": {"alwaysMatch": {}}}`; add `"bundleId": "com.apple.Preferences"` inside `alwaysMatch` to launch an app with the session |
| Screenshot (PNG, base64) | `GET /screenshot` | session-less; also `GET /session/{id}/screenshot` |
| Element-less tap | `POST /session/{id}/wda/tap` | `{"x": 100, "y": 200}` (points, not pixels) |
| W3C actions (tap/swipe/drag) | `POST /session/{id}/actions` | standard W3C `actions` payload — use for swipes and multi-step gestures |
| Type text | `POST /session/{id}/wda/keys` | `{"value": ["h","i"]}` (needs focused field) |
| Home screen | `POST /wda/homescreen` | session-less |
| Press hardware button | `POST /session/{id}/wda/pressButton` | `{"name": "home"}` (`volumeUp`, `volumeDown`, ...) |
| Launch app | `POST /session/{id}/wda/apps/launch` | `{"bundleId": "..."}` |
| Terminate app | `POST /session/{id}/wda/apps/terminate` | `{"bundleId": "..."}` |
| Activate app | `POST /session/{id}/wda/apps/activate` | `{"bundleId": "..."}` |
| App state | `POST /session/{id}/wda/apps/state` | `{"bundleId": "..."}` → 4 = foreground |
| UI hierarchy | `GET /source?format=json` | accessibility tree (can be slow on busy screens) |
| Screen size | `GET /session/{id}/window/size` | for mapping model coords → points |
| MJPEG stream | `http://127.0.0.1:9100` | raw multipart MJPEG, no JSON |

Sessions die if WDA restarts; treat `invalid session id` errors as a cue to
`POST /session` again. Screenshot scale/quality for the MJPEG stream can be tuned via
session capability `settings` (`mjpegServerScreenshotQuality`, `mjpegServerFramerate`).

## MJPEG screen mirror (how the engine streams the screen)

The engine's WebSocket mirror (`/api/v1/devices/{id}/stream`, docs/API.md) does **not**
poll `GET /screenshot` for iOS anymore. It connects to WDA's MJPEG server and relays
JPEG frames directly — no re-encode, roughly 10x the frame rate of screenshot polling.

Setup — one extra forward next to the WDA one:

```sh
uvx pymobiledevice3 usbmux forward 9100 9100 &   # phone MJPEG port -> local 9100
```

If local port 9100 is taken by something else, forward to a different local port and
tell the engine:

```sh
uvx pymobiledevice3 usbmux forward 9110 9100 &
OPENMOB_WDA_MJPEG_PORT=9110 openmob serve
```

Behavior and caveats:

- **Config**: `OPENMOB_WDA_MJPEG_PORT` (default `9100`) — the *local* port the engine
  connects to at `127.0.0.1`. The phone side is always WDA's MJPEG port.
- **Frames only flow while a WDA session exists** on the phone (the MJPEG server
  accepts connections regardless, but stays silent without a session).
- **Fallback**: if the MJPEG connection is refused, times out, or goes silent for 5 s,
  the WS endpoint transparently falls back to the old screenshot-poll loop
  (`GET /screenshot` + PNG→JPEG re-encode, ~1 fps). Android streaming is unchanged.
- **Latency governance**: the engine reads the MJPEG socket continuously, keeps only
  the newest frame, and relays at most ~15 fps to the WS client — a slow client gets
  fresher frames, never a growing backlog.
- **Stream parameters**: WDA defaults are `mjpegServerFramerate` 10 fps,
  `mjpegServerScreenshotQuality` 25, `mjpegScalingFactor` 100. Tuning them requires
  the session-scoped settings API (`POST /session/{id}/appium/settings`), so the
  engine deliberately leaves them alone (it never creates sessions for streaming);
  set them via session capabilities if you own the WDA session.
- **Multipart quirk**: WDA advertises `boundary=--BoundaryString` but delimits parts
  with that literal string (not `--` + boundary as RFC 2046 says). The engine's parser
  keys on each part's `Content-Length` header instead of the boundary text.

## Troubleshooting

- **`xcodebuild` exit code 65 / signing errors** — almost always provisioning. Check:
  `-allowProvisioningUpdates` present; Xcode signed into the Apple ID owning team
  `76Z3N79K53` (Xcode → Settings → Accounts); bundle id unique (ours:
  `ai.zevnix.WebDriverAgentRunner`). Worst case open
  `WebDriverAgent.xcodeproj` in Xcode, select targets `WebDriverAgentLib` +
  `WebDriverAgentRunner`, enable "Automatically manage signing", pick team, build once
  from the IDE, then return to CLI.
- **`Unable to find a destination matching ... id=<udid>`** — phone not connected /
  not trusted / Developer Mode off. `xcrun devicectl list devices` must show
  state `connected`, not just `available (paired)`.
- **"xctrunner not found" / launch of `...xctrunner` fails** — the runner app on the
  phone has a stale bundle id. Uninstall any old `WebDriverAgentRunner-Runner` from
  the phone, rebuild, reinstall. Verify what's installed:
  `xcrun devicectl device info apps --device "$UDID" | grep -i xctrunner`.
- **Developer Mode prompt loop / toggle missing** — connect via USB, open Xcode's
  Devices and Simulators window once, then Settings → Privacy & Security. The phone
  must reboot for the toggle to take effect.
- **"Untrusted Developer" alert when the runner launches** — Settings → General →
  VPN & Device Management → trust the `76Z3N79K53` developer app.
- **WDA starts then times out / port 8100 dead** — the forward isn't up or WDA
  crashed. Re-check `usbmux forward`, watch the `xcodebuild` log; on iOS 26 make sure
  the WDA checkout is ≥ v11.4.1 (Xcode 26 build fix).
- **Passcode prompts during `test`** — the phone must be unlocked when the XCUITest
  session starts; disable auto-lock during long sessions (Settings → Display →
  Auto-Lock → Never).
- **Old lockdown tools fail (`ideviceinstaller`, `ios-deploy`)** — expected on
  iOS 17+; use `devicectl` / `pymobiledevice3` instead.

## Release-gate quirks (learned running the E2E gate on a real iPhone, 2026-07-21)

- **Debug-mode Flutter apps cannot be launched standalone on iOS 14+** (home screen
  or `devicectl process launch` shows a "can only be launched from Flutter tooling"
  screen — the debug engine needs an attached host). Build the testbed in **release**
  mode for gate runs: `flutter build ios --release --no-codesign`, then sign via
  xcodebuild.
- **`flutter build --no-codesign` + xcodebuild share `build/ios`**: a follow-up
  `xcodebuild ... build` sees the unsigned products as up-to-date and skips the
  signing step, leaving `build/ios/Debug-iphoneos/Runner.app` unsigned. Force it with
  `CODE_SIGNING_ALLOWED=YES CODE_SIGN_STYLE=Automatic`, and note the **signed** app
  lands in `~/Library/Developer/Xcode/DerivedData/Runner-*/Build/Products/
  <Config>-iphoneos/Runner.app` — install *that* with
  `xcrun devicectl device install app`.
- **`devicectl process launch` works fine for normal apps** on iOS 26 — only XCTest
  runner bundles (WDA) crash when launched that way (XCTRunnerDaemonSession); WDA
  must be started through `xcodebuild test-without-building`.
- **WDA screenshots are color-managed**: the testbed's pure colors come back slightly
  off (pure red `#FF0000` arrives as `(253, 0, 2)` on an iPhone 12 P3 panel). Pixel
  assertions must use a per-channel tolerance (the gate uses ±10 for PNG on iOS;
  Android stays at ±8).
- **`asyncio.run` under a running event loop** (fixed in `engine/src/openmob/ios.py`,
  `_run_coro`): FastMCP invokes *sync* tool functions directly on the event loop
  thread, so pymobiledevice3 discovery/`list_apps` calls that used `asyncio.run`
  raised `RuntimeError` there — swallowed by `discover()`'s broad `except`, making
  iOS devices silently disappear from the **MCP server only** (the FastAPI server
  runs sync endpoints in a threadpool, so it was unaffected). `_run_coro` now falls
  back to running the coroutine on a throwaway thread.
- Gate reference numbers on the iPhone 12 (1170x2532 @3x): soak 40/40 clean; WS
  stream ~80–91 frames per 20 s (~4–4.5 fps), max inter-frame gap ~0.36 s.

## Sources

- pymobiledevice3 iOS 17+ tunnels guide — <https://github.com/doronz88/pymobiledevice3/blob/master/docs/guides/ios17-tunnels.md>
- Appium XCUITest driver, real-device setup & provisioning — <https://appium.github.io/appium-xcuitest-driver/latest/getting-started/device-setup/>
- WebDriverAgent repo (build fixed for Xcode 26 in v11.4.1, 2026-03) — <https://github.com/appium/WebDriverAgent>, <https://github.com/appium/appium/issues/21347>
- WDA ports 8100/9100 and MJPEG internals — <https://trinhngocthuyen.com/posts/tech/mobile-e2e-wda/>
- `devicectl` as the iOS 17+ install/launch tool — <https://praeclarum.org/2025/10/21/many-ways-to-deploy-ios.html>
