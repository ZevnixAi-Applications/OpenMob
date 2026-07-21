# OpenMob app

Flutter desktop app for the OpenMob engine: browse connected devices, stream their screens, and control them.

## Run

```sh
flutter run -d macos
```

The app talks to the engine at `http://127.0.0.1:8930` by default; change it in Engine settings (gear icon in the sidebar).

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
