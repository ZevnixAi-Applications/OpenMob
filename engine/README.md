# OpenMob Engine

Python engine for OpenMob: controls Android and iOS devices and exposes them over a local HTTP/WebSocket API and an MCP stdio server. See `../docs/API.md` for the API contract.

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and `adb` (Android SDK platform-tools) for Android devices.

```sh
uv run openmob devices        # print detected devices
uv run openmob serve          # HTTP/WS API on 127.0.0.1:8930 (--port to override)
uv run openmob mcp            # MCP stdio server for AI agents
```

iOS: discovery works for any USB-connected iPhone (Developer Mode on, trusted). Control additionally requires a running WebDriverAgent on the phone plus a usbmux port forward — see `../docs/IOS.md` for setup. The engine talks to WDA at `OPENMOB_WDA_URL` (default `http://127.0.0.1:8100`); v1 supports one WDA URL, so control targets the first iOS device only. App install/uninstall uses `xcrun devicectl` (Xcode required). Coordinates and screen sizes are device pixels everywhere (the engine converts to WDA points internally).

Development:

```sh
uv run pytest
uv run ruff check .
```
