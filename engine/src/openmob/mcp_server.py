"""MCP stdio server exposing device control tools to AI agents."""

from mcp.server.fastmcp import FastMCP, Image

from openmob.debugger import CapabilityError, DebugError, DebugSessionManager
from openmob.manager import DeviceManager

manager = DeviceManager()
debug_manager = DebugSessionManager()

mcp = FastMCP(
    "openmob",
    instructions=(
        "Control connected Android/iOS devices: list them, take screenshots, "
        "tap, swipe, type, press keys, and manage apps. Coordinates are device pixels. "
        "debug_* tools drive an interactive lldb session against an iOS app "
        "(simulator UDIDs attach directly; real devices need a tunnel, errors explain how)."
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


def run() -> None:
    """Run the MCP server over stdio (blocking)."""
    mcp.run()
