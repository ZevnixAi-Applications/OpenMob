"""MCP stdio server exposing device control tools to AI agents."""

from mcp.server.fastmcp import FastMCP, Image

from openmob.manager import DeviceManager

manager = DeviceManager()

mcp = FastMCP(
    "openmob",
    instructions=(
        "Control connected Android/iOS devices: list them, take screenshots, "
        "tap, swipe, type, press keys, and manage apps. Coordinates are device pixels."
    ),
)


@mcp.tool()
def list_devices() -> list[dict[str, str | int]]:
    """List connected devices with id, name, platform, status, and screen size."""
    return [device.info() for device in manager.refresh()]


@mcp.tool()
def get_screenshot(device_id: str) -> Image:
    """Capture the device screen and return it as a PNG image."""
    return Image(data=manager.get(device_id).screenshot(), format="png")


@mcp.tool()
def tap(device_id: str, x: int, y: int) -> str:
    """Tap the screen at device pixel coordinates (x, y)."""
    manager.get(device_id).tap(x, y)
    return "ok"


@mcp.tool()
def swipe(device_id: str, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> str:
    """Swipe from (x1, y1) to (x2, y2) over duration_ms milliseconds."""
    manager.get(device_id).swipe(x1, y1, x2, y2, duration_ms)
    return "ok"


@mcp.tool()
def input_text(device_id: str, text: str) -> str:
    """Type text into the currently focused input field."""
    manager.get(device_id).input_text(text)
    return "ok"


@mcp.tool()
def press_key(device_id: str, key: str) -> str:
    """Press a key: home, back, power, volume_up, volume_down, or enter."""
    manager.get(device_id).press_key(key)
    return "ok"


@mcp.tool()
def install_app(device_id: str, path: str) -> str:
    """Install an app from a local package file path (.apk / .ipa)."""
    manager.get(device_id).install_app(path)
    return "ok"


@mcp.tool()
def uninstall_app(device_id: str, package: str) -> str:
    """Uninstall an app by package identifier."""
    manager.get(device_id).uninstall_app(package)
    return "ok"


@mcp.tool()
def list_apps(device_id: str) -> list[dict[str, str]]:
    """List installed third-party apps on the device."""
    return manager.get(device_id).list_apps()


@mcp.tool()
def launch_app(device_id: str, package: str) -> str:
    """Launch an app by package identifier."""
    manager.get(device_id).launch_app(package)
    return "ok"


def run() -> None:
    """Run the MCP server over stdio (blocking)."""
    mcp.run()
