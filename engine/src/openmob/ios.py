"""iOS device backend: pymobiledevice3 for discovery, WebDriverAgent over HTTP for control.

Control goes through a WebDriverAgent (WDA) server running on the phone, reached at
`OPENMOB_WDA_URL` (default http://127.0.0.1:8100, via `pymobiledevice3 usbmux forward`).
v1 limitation: a single WDA URL is configured, so control targets the first iOS device
only; discovery and app listing work for any number of connected devices.

WDA speaks in POINTS while the OpenMob API contract (docs/API.md) uses device PIXELS
(consistent with screenshots and the Android backend), so width/height are reported in
pixels and incoming coordinates are divided by the screen scale before being sent to
WDA. See docs/IOS.md for phone setup and the WDA endpoint reference.
"""

import asyncio
import base64
import binascii
import concurrent.futures
import os
import subprocess
from collections.abc import Coroutine
from typing import Any

import httpx

from openmob.device import Device, DeviceError

DEFAULT_WDA_URL = "http://127.0.0.1:8100"

WDA_TIMEOUT = 5.0
SCREENSHOT_TIMEOUT = 15.0
LOCKDOWN_TIMEOUT = 5.0

_WDA_UNREACHABLE = "WDA not running on device — see docs/IOS.md"
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

_BUTTONS = {"volume_up": "volumeUp", "volume_down": "volumeDown"}
_KEYS = ("home", "power", "volume_up", "volume_down", "enter")


def _run_coro(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine to completion from sync code, even under a running event loop.

    `asyncio.run` raises RuntimeError when called on a thread that already has a
    running loop — which is exactly how the MCP server invokes sync tools (FastMCP
    calls them directly on the event loop thread). In that case run the coroutine
    on a throwaway thread with its own loop.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def wda_url() -> str:
    """Base URL of the WebDriverAgent server (usually a usbmux forward to the phone)."""
    return os.environ.get("OPENMOB_WDA_URL", DEFAULT_WDA_URL)


def pixels_to_points(value: float, scale: float) -> float:
    """Convert device pixels (our API contract) to points (what WDA expects)."""
    return round(value / scale, 2)


def parse_png_size(png: bytes) -> tuple[int, int]:
    """Read (width, height) from a PNG header."""
    if not png.startswith(_PNG_MAGIC) or len(png) < 24:
        raise DeviceError("not a PNG")
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


class _InvalidSession(DeviceError):
    """WDA rejected the cached session id (WDA restarted); recreate and retry once."""


class WdaClient:
    """Minimal WebDriver client for WDA with lazy session management."""

    def __init__(self, base_url: str | None = None, client: httpx.Client | None = None) -> None:
        self._http = client or httpx.Client(base_url=base_url or wda_url(), timeout=WDA_TIMEOUT)
        self._session_id: str | None = None

    def request(
        self, method: str, path: str, body: dict | None = None, timeout: float = WDA_TIMEOUT
    ) -> object:
        """Send a request and return the unwrapped WebDriver `value`."""
        try:
            response = self._http.request(method, path, json=body, timeout=timeout)
        except httpx.HTTPError as exc:
            raise DeviceError(_WDA_UNREACHABLE) from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise DeviceError(f"WDA returned non-JSON for {method} {path}") from exc
        value = payload.get("value") if isinstance(payload, dict) else None
        if isinstance(value, dict) and value.get("error"):
            error = value["error"]
            message = value.get("message") or error
            if error == "invalid session id":
                raise _InvalidSession(message)
            raise DeviceError(f"WDA {method} {path} failed: {message}")
        if response.status_code >= 400:
            raise DeviceError(f"WDA {method} {path} failed: HTTP {response.status_code}")
        return value

    def session_id(self) -> str:
        """Return the cached WDA session id, creating a session on first use."""
        if self._session_id is None:
            value = self.request("POST", "/session", {"capabilities": {"alwaysMatch": {}}})
            session_id = value.get("sessionId") if isinstance(value, dict) else None
            if not session_id:
                raise DeviceError("WDA did not return a session id")
            self._session_id = session_id
        return self._session_id

    def session_request(
        self, method: str, path: str, body: dict | None = None, timeout: float = WDA_TIMEOUT
    ) -> object:
        """Send a request under /session/{id}, recreating the session once if stale."""
        try:
            return self.request(method, f"/session/{self.session_id()}{path}", body, timeout)
        except _InvalidSession:
            self._session_id = None
            return self.request(method, f"/session/{self.session_id()}{path}", body, timeout)


class IosDevice(Device):
    """An iOS device discovered over usbmux and controlled via WebDriverAgent."""

    def __init__(
        self, udid: str, name: str, status: str = "online", wda: WdaClient | None = None
    ) -> None:
        self._udid = udid
        self._name = name
        self._status = status
        self._wda_client = wda
        self._geometry: tuple[int, int, float] | None = None

    @property
    def _wda(self) -> WdaClient:
        if self._wda_client is None:
            self._wda_client = WdaClient()
        return self._wda_client

    @property
    def id(self) -> str:
        return self._udid

    @property
    def name(self) -> str:
        return self._name

    @property
    def platform(self) -> str:
        return "ios"

    @property
    def status(self) -> str:
        return self._status

    @property
    def width(self) -> int:
        return self._screen_geometry()[0]

    @property
    def height(self) -> int:
        return self._screen_geometry()[1]

    def _screen_geometry(self) -> tuple[int, int, float]:
        """Return (width_px, height_px, scale); WDA reports points, we expose pixels."""
        if self._geometry is None:
            window = self._wda.session_request("GET", "/window/size")
            if not isinstance(window, dict) or "width" not in window:
                raise DeviceError(f"unexpected WDA window size: {window!r}")
            try:
                screen = self._wda.session_request("GET", "/wda/screen")
                scale = float(screen["scale"])  # type: ignore[index, call-overload]
                size = round(window["width"] * scale), round(window["height"] * scale)
            except (DeviceError, KeyError, TypeError, ValueError):
                # Fallback: derive the scale from screenshot pixels vs window points.
                size = parse_png_size(self.screenshot())
                scale = size[0] / window["width"]
            self._geometry = (*size, scale)
        return self._geometry

    def screenshot(self) -> bytes:
        value = self._wda.request("GET", "/screenshot", timeout=SCREENSHOT_TIMEOUT)
        if not isinstance(value, str):
            raise DeviceError(f"unexpected WDA screenshot response: {type(value).__name__}")
        try:
            png = base64.b64decode(value)
        except (binascii.Error, ValueError) as exc:
            raise DeviceError("WDA screenshot is not valid base64") from exc
        if not png.startswith(_PNG_MAGIC):
            raise DeviceError("WDA screenshot did not return a PNG")
        return png

    def tap(self, x: int, y: int) -> None:
        scale = self._screen_geometry()[2]
        body = {"x": pixels_to_points(x, scale), "y": pixels_to_points(y, scale)}
        self._wda.session_request("POST", "/wda/tap", body)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        scale = self._screen_geometry()[2]
        body = {
            "fromX": pixels_to_points(x1, scale),
            "fromY": pixels_to_points(y1, scale),
            "toX": pixels_to_points(x2, scale),
            "toY": pixels_to_points(y2, scale),
            "duration": duration_ms / 1000,
        }
        self._wda.session_request("POST", "/wda/dragfromtoforduration", body)

    def input_text(self, text: str) -> None:
        self._wda.session_request("POST", "/wda/keys", {"value": list(text)})

    def press_key(self, key: str) -> None:
        if key == "home":
            self._wda.request("POST", "/wda/homescreen")
        elif key == "power":
            self._wda.session_request("POST", "/wda/lock")
        elif button := _BUTTONS.get(key):
            self._wda.session_request("POST", "/wda/pressButton", {"name": button})
        elif key == "enter":
            self.input_text("\n")
        else:
            raise DeviceError(f"unknown key {key!r}, expected one of: {', '.join(_KEYS)}")

    def install_app(self, path: str) -> None:
        self._devicectl("install", "app", "--device", self._udid, path, timeout=300)

    def uninstall_app(self, package: str) -> None:
        self._devicectl("uninstall", "app", "--device", self._udid, package, timeout=120)

    def _devicectl(self, *args: str, timeout: float) -> None:
        cmd = ["xcrun", "devicectl", "device", *args]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except FileNotFoundError as exc:
            raise DeviceError("xcrun not found: install Xcode command line tools") from exc
        if result.returncode != 0:
            detail = result.stderr.decode(errors="replace").strip() or "unknown devicectl error"
            raise DeviceError(f"devicectl {' '.join(args[:2])} failed: {detail}")

    def list_apps(self) -> list[dict[str, str]]:
        async def fetch() -> dict[str, dict]:
            from pymobiledevice3.services.installation_proxy import InstallationProxyService

            lockdown = await _lockdown_client(self._udid)
            try:
                async with InstallationProxyService(lockdown) as proxy:
                    return await proxy.get_apps(application_type="User")
            finally:
                await lockdown.close()

        try:
            apps = _run_coro(fetch())
        except Exception as exc:
            raise DeviceError(f"could not list apps on {self._udid}: {exc}") from exc
        return sorted(
            (
                {
                    "package": bundle_id,
                    "name": info.get("CFBundleDisplayName")
                    or info.get("CFBundleName")
                    or bundle_id,
                }
                for bundle_id, info in apps.items()
            ),
            key=lambda app: app["package"],
        )

    def launch_app(self, package: str) -> None:
        self._wda.session_request("POST", "/wda/apps/launch", {"bundleId": package})

    def logs(self) -> str:
        raise DeviceError(
            "iOS log capture is not supported yet; "
            "run `pymobiledevice3 syslog live` instead (see docs/IOS.md)"
        )


async def _lockdown_client(udid: str):
    """Open a lockdown client over usbmux with a short timeout (caller must close)."""
    from pymobiledevice3.lockdown import create_using_usbmux

    return await asyncio.wait_for(
        create_using_usbmux(udid, autopair=False), timeout=LOCKDOWN_TIMEOUT
    )


def _lockdown_name(udid: str) -> str:
    """Best-effort device name via lockdown; fall back to the UDID."""

    async def fetch() -> str:
        lockdown = await _lockdown_client(udid)
        try:
            name = await lockdown.get_value(key="DeviceName")
            product = await lockdown.get_value(key="ProductType")
        finally:
            await lockdown.close()
        return str(name or product or udid)

    try:
        return _run_coro(fetch())
    except Exception:
        return udid


def discover() -> list[IosDevice]:
    """Discover connected iOS devices via usbmux (control requires WDA, see docs/IOS.md)."""

    async def fetch() -> list:
        from pymobiledevice3 import usbmux

        return await usbmux.list_devices()

    try:
        muxed = _run_coro(fetch())
    except Exception:
        return []
    devices: list[IosDevice] = []
    seen: set[str] = set()
    for mux_device in muxed:
        udid = mux_device.serial
        if udid in seen:  # a device can show up over both USB and WiFi
            continue
        seen.add(udid)
        devices.append(IosDevice(udid, _lockdown_name(udid)))
    return devices
