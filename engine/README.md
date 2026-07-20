# OpenMob Engine

Python engine for OpenMob: controls Android (and soon iOS) devices and exposes them over a local HTTP/WebSocket API and an MCP stdio server. See `../docs/API.md` for the API contract.

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and `adb` (Android SDK platform-tools) for Android devices.

```sh
uv run openmob devices        # print detected devices
uv run openmob serve          # HTTP/WS API on 127.0.0.1:8930 (--port to override)
uv run openmob mcp            # MCP stdio server for AI agents
```

Development:

```sh
uv run pytest
uv run ruff check .
```
