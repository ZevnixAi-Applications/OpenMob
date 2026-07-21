# OpenMob

[![CI](https://github.com/ZevnixAi-Applications/OpenMob/actions/workflows/ci.yml/badge.svg)](https://github.com/ZevnixAi-Applications/OpenMob/actions/workflows/ci.yml)

**Open-source mobile device control for humans and AI agents.**

Control real Android and iOS devices from your Mac — live screen mirror, tap/swipe/type, app install, logs — through a desktop app, a CLI, or an MCP server that lets AI agents (Claude, etc.) drive your phone.

## Architecture

```
┌─────────────── Mac ────────────────┐        ┌── Android device ──┐
│  app/     Flutter desktop UI       │─ USB ──│ adb (built-in)     │
│  engine/  Python device engine     │        └────────────────────┘
│    • unified device abstraction    │        ┌──── iOS device ────┐
│    • MCP server (AI agent tools)   │─ USB ──│ runner/ios (WDA-   │
│    • local WebSocket API for UI    │        │ style XCUITest)    │
└────────────────────────────────────┘        └────────────────────┘
```

- **engine/** — Python (uv). Device backends: `adb` for Android, `pymobiledevice3` + WebDriverAgent for iOS. Exposes an MCP server and a local HTTP/WebSocket API.
- **app/** — Flutter macOS desktop app: device list, live mirror, click-to-tap.
- **runner/** — on-device companions. iOS: signed XCUITest runner (required by Apple for input injection). Android: none needed (adb covers it).

## Status

Early development. Android vertical slice first, iOS next.

## License

MIT
