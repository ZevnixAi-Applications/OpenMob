# OpenMob app

Desktop (macOS) UI for the OpenMob engine: browse connected devices, stream their
screens live, and control them with tap, swipe, text and hardware-key input over
the engine's local HTTP/WS API (see `docs/API.md`).

## Run

```sh
flutter run -d macos
```

The app talks to the engine at `http://127.0.0.1:8930` by default; change it in Engine settings (gear icon in the sidebar).

## Multi-device view

Devices open as VS Code-style tabs. Clicking a device in the sidebar opens
(or re-activates) its tab; the tab's `x` closes it. The open set and the
active tab persist across restarts.

### Layouts

- **Single** (default): the active tab fills the main pane. Only the active
  device's screen stream is connected; switching tabs disposes the previous
  stream.
- **Split** (grid icon in the tab bar's right corner): every open device is
  visible at once — 1-3 devices side by side, 4+ in a 2-column grid. Each
  pane runs its own WebSocket stream, keeps its own aspect-correct mirror
  and tap/swipe handling, and has a slim header with the device name and a
  close button. Offline devices show an offline pane state.

### Focus and the toolbar

The bottom toolbar (back/home/power/volume/text) always targets the
**focused** pane: in single view that is the active tab; in split view,
click any pane to focus it — the focused pane gets an accent outline and
the toolbar shows the target device's name.

### Sync input

The link icon (enabled in split view only) toggles sync-input mode. While on:

- Taps and swipes on any pane are also sent to every other visible online
  device, with coordinates translated proportionally to each device's
  reported resolution (a tap at 50%/30% lands at 50%/30% everywhere).
- Text and keys sent from the toolbar go verbatim to all online panes.
- All panes show a blue border; mirrored panes flash briefly when a
  broadcast fires.
- Offline devices are skipped, and a failure on one device never blocks
  the others (errors surface, deduped, in the error banner).

## Connecting to an engine

- **Auto-discovery (mDNS):** the engine advertises itself as `_openmob._tcp` on the local network. Use "Find engines on my network" — on the engine-offline screen or in Engine settings — to list engines (name + host:port); tapping one applies its URL. Discovery uses the first-party `multicast_dns` package. If nothing is found within the timeout, the dialog falls back to manual URL entry guidance. Note: engines are only reachable from other machines when started with `openmob serve --host 0.0.0.0`.
- **Start engine (macOS only):** when the engine is offline, the "Start engine" button launches it using the command configured in Engine settings and polls `/health` for up to 30 s (a clear error including the attempted command is shown on failure).
  - Default command: `uv run --project <repo>/engine openmob serve` when the app runs from a repo checkout (found by walking up from the working directory / executable for `engine/pyproject.toml`); otherwise `openmob serve` (engine on PATH).
  - The command runs through `/bin/zsh -l -c` so it sees your normal login PATH (Homebrew's `uv` etc.), and is started **detached**: the engine keeps running if the app quits or restarts. Stop it manually (Ctrl+C in its terminal, or `pkill -f "openmob serve"`).

### Manual test: engine auto-start

1. Make sure nothing is listening on 8930 (`lsof -nP -iTCP:8930`).
2. `flutter run -d macos` — the main pane shows "Engine offline" with a "Start engine" button (macOS only).
3. Optionally open Engine settings and adjust "Start engine command".
4. Click "Start engine": a "Starting engine…" spinner shows while `/health` is polled; within a few seconds the sidebar turns green ("connected · v…").
5. Quit the app; the engine keeps running (detached). Relaunch — it connects immediately.
6. Failure path: set the command to something invalid (e.g. `nonexistent-cmd serve`), click "Start engine", and after 30 s an error appears that includes the command tried.

### Manual test: discovery

1. Start an engine anywhere on the LAN: `openmob serve --host 0.0.0.0` (add `--port` as needed).
2. In the app, click "Find engines on my network" (offline screen or Engine settings).
3. The dialog shows "Searching your network…", then lists `OpenMob Engine on <hostname>` with `host:port`. Tap an entry to connect.

## Platform notes

- The macOS app is sandboxed; `network.client`/`network.server` entitlements (needed for the API, mDNS's UDP 5353 socket, and the spawned engine) are declared in `macos/Runner/*.entitlements`.
- This branch has no `ios/` runner. The discovery/connect UI is written portably (pure-Dart `multicast_dns`); on iOS the runner must declare `NSBonjourServices` with `_openmob._tcp` (already done on the mobile branch).

## Tests

```sh
flutter analyze
flutter test
```
