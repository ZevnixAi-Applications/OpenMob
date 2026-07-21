"""MCP stdio server exposing device control tools to AI agents."""

from pathlib import Path

from mcp.server.fastmcp import FastMCP, Image

from openmob import flutter, virtual
from openmob.debugger import CapabilityError, DebugError, DebugSessionManager
from openmob.device import DeviceError
from openmob.logstream import LogScope
from openmob.manager import DeviceManager

manager = DeviceManager()
debug_manager = DebugSessionManager()

mcp = FastMCP(
    "openmob",
    instructions=(
        "Control connected Android/iOS devices: list them, take screenshots, "
        "tap, swipe, type, press keys, and manage apps. Coordinates are device pixels. "
        "debug_* tools drive an interactive lldb session against an iOS app "
        "(simulator UDIDs attach directly; real devices need a tunnel, errors explain how). "
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
def debug_attach(
    device_id: str,
    pid: int | None = None,
    bundle_id: str | None = None,
    breakpoints: list[str] | None = None,
    debugserver_url: str | None = None,
) -> dict:
    """Attach an lldb debug session to an iOS app on the given device (one per device).

    Provide pid or bundle_id (bundle id is resolved to the running process; launch the
    app first). Optional breakpoints (e.g. "File.swift:42", "-[Class method:]") are
    armed before the app resumes. Returns session info; the app keeps running.
    """
    try:
        session, attach = debug_manager.create(
            device_id=device_id,
            pid=pid,
            bundle_id=bundle_id,
            breakpoints=breakpoints,
            debugserver_url=debugserver_url,
        )
    except CapabilityError as exc:
        return {"error": "capability_missing", "detail": str(exc), "commands": exc.commands}
    return {**session.info(), "attach": attach}


@mcp.tool()
def debug_breakpoint(
    device_id: str, op: str, spec: str | None = None, id: int | None = None
) -> dict:
    """Manage breakpoints in the device's debug session.

    op="add" needs spec ("File.swift:42", "-[Class method:]", or a symbol name);
    op="remove" needs id; op="list" returns all breakpoints with hit counts.
    """
    session = debug_manager.get_by_device(device_id)
    if op == "add":
        if not spec:
            raise DebugError("op='add' requires spec")
        return session.breakpoint_set(spec)
    if op == "remove":
        if id is None:
            raise DebugError("op='remove' requires id")
        return session.breakpoint_delete(id)
    if op == "list":
        return {"breakpoints": session.breakpoint_list()}
    raise DebugError(f"unknown op {op!r} (expected add/remove/list)")


@mcp.tool()
def debug_step(device_id: str, kind: str) -> dict:
    """Advance the debugged app: kind = "in" | "over" | "out" | "continue" | "pause".

    in/over/out step the stopped thread and return the new frame; continue resumes
    until the next breakpoint (poll debug_state); pause interrupts a running app.
    """
    return debug_manager.get_by_device(device_id).step(kind)


@mcp.tool()
def debug_eval(device_id: str, expression: str, frame_id: int | None = None) -> dict:
    """Evaluate an expression (ObjC/Swift/C) in a stopped frame of the debugged app."""
    return debug_manager.get_by_device(device_id).eval(expression, frame_id)


@mcp.tool()
def debug_state(
    device_id: str, stack: bool = True, vars: bool = True, threads: bool = False
) -> dict:
    """Report the debug session: process state, breakpoints, and when stopped the
    stop reason, backtrace, and frame-0 locals (set threads=True for all threads)."""
    return debug_manager.get_by_device(device_id).state(
        stack=stack, variables=vars, threads=threads
    )


@mcp.tool()
def debug_detach(device_id: str, kill: bool = False) -> dict:
    """End the device's debug session; the app keeps running unless kill=True."""
    session = debug_manager.get_by_device(device_id)
    return debug_manager.remove(session.id, kill=kill)


@mcp.tool()
def get_logs(
    device_id: str,
    lines: int = 200,
    filter: str = "",
    package: str = "",
    scope: str = "",
    flutter: bool = False,
) -> str:
    """Get recent logs, scoped to one app instead of the whole device by default.

    Pass `package` to scope to that app's live process (the useful case: an app's own
    output, including Flutter print/debugPrint), or `scope="foreground"` to auto-target
    the foreground app (Android). `flutter=True` narrows to Flutter framework output.
    With none of these it returns the whole-device log. `filter` is a case-insensitive
    substring match. A scoped app that is not running returns an empty string.
    """
    log_scope = LogScope(
        package=package or None,
        foreground=scope == "foreground",
        flutter=flutter,
    )
    return manager.get(device_id).logs(
        lines=lines,
        filter_str=filter or None,
        scope=log_scope if (log_scope.is_app_scoped or log_scope.flutter) else None,
    )


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


@mcp.tool()
def list_virtual_devices() -> list[dict[str, str | None]]:
    """List launchable virtual devices (Android AVDs and iOS Simulators)."""
    return virtual.list_virtual_devices()


@mcp.tool()
def launch_virtual_device(name: str, windowed: bool = False) -> str:
    """Boot a virtual device by name; it then appears in list_devices once online.

    Boots headless by default (no native emulator/Simulator window) so it is
    mirrored inside OpenMob; pass windowed=True to also open the platform's window.
    """
    result = virtual.launch(name, windowed=windowed)
    return str(result.get("note", "ok"))


@mcp.tool()
def get_create_options() -> dict:
    """Installable images and hardware profiles for creating new virtual devices.

    Returns {"android": {device_profiles, system_images}, "ios": {device_types, runtimes}};
    each section has an `available` flag and a `reason` when the tooling is missing.
    """
    return virtual.create_options()


@mcp.tool()
def create_virtual_device(
    platform: str,
    name: str,
    device_profile: str | None = None,
    system_image: str | None = None,
    device_type: str | None = None,
    runtime: str | None = None,
) -> dict:
    """Create a new AVD (platform="android") or iOS simulator (platform="ios").

    Android needs device_profile (e.g. "pixel_7") and system_image (e.g.
    "system-images;android-35;google_apis;arm64-v8a"); an uninstalled image is
    downloaded first, so a job id is returned — poll GET
    /virtual-devices/create/jobs/{id} for progress. iOS needs device_type and
    runtime identifiers (from get_create_options) and completes quickly.
    """
    return virtual.create_virtual_device(
        platform=platform,
        name=name,
        device_profile=device_profile,
        system_image=system_image,
        device_type=device_type,
        runtime=runtime,
    )


def run() -> None:
    """Run the MCP server over stdio (blocking)."""
    mcp.run()
