"""MCP stdio server exposing device control tools to AI agents."""

from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from openmob import flutter
from openmob.device import DeviceError
from openmob.manager import DeviceManager

manager = DeviceManager()

mcp = FastMCP(
    "openmob",
    instructions=(
        "Control connected Android/iOS devices: list them, take screenshots, "
        "tap, swipe, type, press keys, and manage apps. Coordinates are device pixels. "
        "Developer tools: device logs (get_logs), crash reports (get_crash_logs), "
        "deep links (open_url), file transfer (push_file/pull_file), device_info, and "
        "Flutter debugging (flutter_vm_service, flutter_hot_reload)."
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


@mcp.tool()
def get_logs(device_id: str, lines: int = 200, filter: str = "") -> str:
    """Get recent device logs, optionally filtered to lines containing `filter`."""
    return manager.get(device_id).logs(lines=lines, filter_str=filter or None)


@mcp.tool()
def save_screenshot(device_id: str, path: str) -> str:
    """Capture the device screen and write it as a PNG to an absolute host path."""
    target = Path(path)
    if not target.is_absolute():
        raise DeviceError(f"path must be absolute: {path}")
    png = manager.get(device_id).screenshot()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)
    return str(target)


@mcp.tool()
def get_crash_logs(device_id: str, limit: int = 5) -> list[dict[str, str]]:
    """Get the most recent app crash reports (newest first) with parsed summaries."""
    return manager.get(device_id).crash_reports(limit=limit)


@mcp.tool()
def open_url(device_id: str, url: str) -> str:
    """Open a URL or deep link on the device."""
    manager.get(device_id).open_url(url)
    return "ok"


@mcp.tool()
def clear_app_data(device_id: str, package: str) -> str:
    """Clear an app's data and cache (Android only)."""
    manager.get(device_id).clear_app_data(package)
    return "ok"


@mcp.tool()
def force_stop(device_id: str, package: str) -> str:
    """Force-stop a running app by package/bundle identifier."""
    manager.get(device_id).force_stop(package)
    return "ok"


@mcp.tool()
def push_file(device_id: str, local_path: str, device_path: str) -> str:
    """Copy a local file to the device (iOS: `bundle.id:/path` targets an app container)."""
    manager.get(device_id).push_file(local_path, device_path)
    return "ok"


@mcp.tool()
def pull_file(device_id: str, device_path: str, local_path: str) -> str:
    """Copy a file from the device to the local machine."""
    manager.get(device_id).pull_file(device_path, local_path)
    return "ok"


@mcp.tool()
def device_info(device_id: str) -> dict[str, str | int]:
    """Get battery percentage, OS version, and model details for a device."""
    return manager.get(device_id).system_info()


@mcp.tool()
def flutter_vm_service(device_id: str) -> dict[str, str]:
    """Find a running debug Flutter app's Dart VM service and forward it to the host."""
    return flutter.vm_service(manager.get(device_id))


@mcp.tool()
def flutter_hot_reload(device_id: str) -> dict[str, object]:
    """Hot-reload the running debug Flutter app via its Dart VM service."""
    return flutter.hot_reload(manager.get(device_id))


def run() -> None:
    """Run the MCP server over stdio (blocking)."""
    mcp.run()
