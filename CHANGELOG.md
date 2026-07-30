# Changelog

All notable changes to OpenMob are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Windows host support** — the engine runs cross-platform, the Flutter app
  builds for Windows, and an Inno Setup installer is produced by CI. Windows
  controls Android devices and emulators; iOS remains macOS-only and iOS calls
  return a clear "requires macOS" error. See [docs/WINDOWS.md](docs/WINDOWS.md).
- Continuous integration: engine lint (`ruff`) and tests (`pytest`) on Linux and
  macOS, app `flutter analyze` and `flutter test`, on every pull request.
- Release automation: installers for macOS (`.dmg`) and Windows (`.exe`) are
  built on native runners and attached to published GitHub Releases.
- `CHANGELOG.md`, `SECURITY.md`, and `CODE_OF_CONDUCT.md`.

### Notes

- The Windows installer is produced from this version onward. Release 0.1.0
  predates Windows support and ships a macOS DMG only.

## [0.1.0] — 2026-07-21

First public release. macOS DMG only.

### Added

- **Engine** (Python) — device control for Android via `adb` and iOS via a
  WebDriverAgent runner and `pymobiledevice3`, exposed as a local HTTP and
  WebSocket API, an MCP server, and an `openmob` CLI (`serve`, `mcp`, `devices`).
- **Desktop app** (Flutter, macOS) — device sidebar, live screen mirror with
  click-to-tap and drag-to-swipe, tabs and split view, and log/Flutter/debug
  panels.
- Live mirroring — H.264 stream on Android, WDA MJPEG on iOS, with coordinate
  translation to device pixels.
- App management — install, launch, force-stop, uninstall, clear data (Android),
  and deep links.
- Observability — app-scoped log streaming, crash reports, battery/OS/model
  info, and file push/pull.
- **Flutter run-mode** — hot reload, hot restart, and DevTools against a project
  launched through OpenMob.
- **Interactive iOS debugger** — an lldb session with breakpoints, stepping,
  expression evaluation, and backtraces (simulator; real devices need a tunnel).
- Virtual devices — list, create, and boot Android AVDs and iOS simulators,
  headless, from the app.
- **MCP server** — the full device surface exposed as tools for Claude and other
  MCP-capable agents.
- Deterministic testbed app and an end-to-end release-gate harness.
- Docs: getting started, architecture, engine API, developer tools, debugging,
  virtual devices, and iOS setup.

[Unreleased]: https://github.com/ZevnixAi-Applications/OpenMob/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ZevnixAi-Applications/OpenMob/releases/tag/v0.1.0
