"""iOS Simulator backend: simctl for screenshots/apps, per-simulator WDA for input.

Booted simulators are first-class devices (platform "ios"). This module extends
the single-WDA-URL design of `openmob.ios` (env `OPENMOB_WDA_URL` -> first real
USB device, unchanged) with a registry that runs one WebDriverAgent per
simulator on its own port (8101+). Simulators share the Mac's network stack, so
WDA inside a simulator is reachable on 127.0.0.1 directly — no forwarding.

WDA is built once for the simulator SDK (no code signing) into a scratch
derivedData next to the WebDriverAgent checkout, then started per simulator
with `xcodebuild test-without-building`. The port is injected through
`TEST_RUNNER_USE_PORT`: xcodebuild forwards `TEST_RUNNER_*` variables to the
test runner's environment with the prefix stripped, and WDA reads `USE_PORT`
(WebDriverAgentLib/Utilities/FBConfiguration.m).
"""

import os
import socket
import subprocess
import time
from pathlib import Path

import httpx

from openmob.device import DeviceError
from openmob.ios import IosDevice, WdaClient, parse_png_size
from openmob.virtual import list_simulators

SIM_WDA_BASE_PORT = 8101

_BUILD_TIMEOUT = 600
_BOOT_TIMEOUT = 120
_SIMCTL_TIMEOUT = 30


def wda_dir() -> Path:
    """WebDriverAgent checkout (env `OPENMOB_WDA_DIR`, default runner/ios in the repo)."""
    if configured := os.environ.get("OPENMOB_WDA_DIR"):
        return Path(configured)
    return Path(__file__).resolve().parents[3] / "runner" / "ios" / "WebDriverAgent"


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


class SimWdaRegistry:
    """Allocates one WDA port per simulator and tracks the xcodebuild subprocesses."""

    def __init__(self, base_port: int = SIM_WDA_BASE_PORT, port_is_free=_port_is_free) -> None:
        self._base_port = base_port
        self._port_is_free = port_is_free
        self._ports: dict[str, int] = {}
        self._procs: dict[str, subprocess.Popen] = {}

    def port_for(self, udid: str) -> int:
        """Stable port for a simulator, skipping ports something else is using."""
        if udid in self._ports:
            return self._ports[udid]
        port = self._base_port
        while port in self._ports.values() or not self._port_is_free(port):
            port += 1
        self._ports[udid] = port
        return port

    def url_for(self, udid: str) -> str:
        return f"http://127.0.0.1:{self.port_for(udid)}"

    def ensure_running(self, udid: str) -> str:
        """Return the WDA URL for a simulator, building and starting WDA if needed."""
        url = self.url_for(udid)
        if self._responding(url):
            return url
        self._build_once()
        self._spawn(udid, self._ports[udid])
        deadline = time.monotonic() + _BOOT_TIMEOUT
        while time.monotonic() < deadline:
            if self._responding(url):
                return url
            process = self._procs.get(udid)
            if process is not None and process.poll() is not None:
                raise DeviceError(
                    f"WDA runner for simulator {udid} exited with code {process.returncode}"
                )
            time.sleep(1)
        raise DeviceError(f"WDA on simulator {udid} did not come up within {_BOOT_TIMEOUT}s")

    @staticmethod
    def _responding(url: str) -> bool:
        try:
            return httpx.get(f"{url}/status", timeout=2).status_code == 200
        except httpx.HTTPError:
            return False

    def _build_once(self) -> None:
        """Build WDA for the simulator SDK unless a previous build is present."""
        project = wda_dir() / "WebDriverAgent.xcodeproj"
        if not project.is_dir():
            raise DeviceError(
                f"WebDriverAgent checkout not found at {wda_dir()} — "
                "clone https://github.com/appium/WebDriverAgent.git there "
                "(see docs/VIRTUAL_DEVICES.md)"
            )
        if list(self._derived_data().glob("Build/Products/*_iphonesimulator*.xctestrun")):
            return
        result = subprocess.run(
            [
                "xcodebuild",
                "-project",
                str(project),
                "-scheme",
                "WebDriverAgentRunner",
                "-sdk",
                "iphonesimulator",
                "-destination",
                "generic/platform=iOS Simulator",
                "-derivedDataPath",
                str(self._derived_data()),
                "CODE_SIGNING_ALLOWED=NO",
                "build-for-testing",
            ],
            capture_output=True,
            timeout=_BUILD_TIMEOUT,
        )
        if result.returncode != 0:
            tail = result.stdout.decode(errors="replace").strip().splitlines()[-15:]
            raise DeviceError("WDA simulator build failed: " + " | ".join(tail))

    def _derived_data(self) -> Path:
        return wda_dir() / "sim-build"

    def _spawn(self, udid: str, port: int) -> None:
        """Start the WDA test runner on a simulator, detached, on the given port."""
        process = subprocess.Popen(
            [
                "xcodebuild",
                "-project",
                str(wda_dir() / "WebDriverAgent.xcodeproj"),
                "-scheme",
                "WebDriverAgentRunner",
                "-destination",
                f"id={udid}",
                "-derivedDataPath",
                str(self._derived_data()),
                "CODE_SIGNING_ALLOWED=NO",
                "test-without-building",
            ],
            env={**os.environ, "TEST_RUNNER_USE_PORT": str(port)},
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self._procs[udid] = process

    def shutdown(self, udid: str | None = None) -> None:
        """Terminate tracked WDA runners (all of them when udid is None)."""
        udids = [udid] if udid is not None else list(self._procs)
        for key in udids:
            process = self._procs.pop(key, None)
            if process is not None and process.poll() is None:
                process.terminate()


registry = SimWdaRegistry()


class IosSimDevice(IosDevice):
    """A booted iOS Simulator: simctl fast paths + WDA (from the registry) for input."""

    def __init__(self, udid: str, name: str, wda_registry: SimWdaRegistry = registry) -> None:
        super().__init__(udid, name)
        self._registry = wda_registry
        self._pixel_size: tuple[int, int] | None = None

    @property
    def _wda(self) -> WdaClient:
        if self._wda_client is None:
            self._wda_client = WdaClient(base_url=self._registry.ensure_running(self.id))
        return self._wda_client

    @property
    def width(self) -> int:
        return self._screen_pixels()[0]

    @property
    def height(self) -> int:
        return self._screen_pixels()[1]

    def _screen_pixels(self) -> tuple[int, int]:
        """Pixel size from a simctl screenshot — no WDA needed just to list devices."""
        if self._pixel_size is None:
            self._pixel_size = parse_png_size(self.screenshot())
        return self._pixel_size

    def _screen_geometry(self) -> tuple[int, int, float]:
        """(width_px, height_px, scale); scale derived from WDA's point size."""
        if self._geometry is None:
            width, height = self._screen_pixels()
            window = self._wda.session_request("GET", "/window/size")
            if not isinstance(window, dict) or not window.get("width"):
                raise DeviceError(f"unexpected WDA window size: {window!r}")
            self._geometry = (width, height, width / window["width"])
        return self._geometry

    def screenshot(self) -> bytes:
        png = self._simctl("io", self.id, "screenshot", "--type=png", "-")
        if not png.startswith(b"\x89PNG"):
            raise DeviceError("simctl screenshot did not return a PNG")
        return png

    def install_app(self, path: str) -> None:
        self._simctl("install", self.id, path, timeout=300)

    def uninstall_app(self, package: str) -> None:
        self._simctl("uninstall", self.id, package, timeout=120)

    def list_apps(self) -> list[dict[str, str]]:
        import plistlib

        raw = self._simctl("listapps", self.id)
        converted = subprocess.run(
            ["plutil", "-convert", "xml1", "-o", "-", "--", "-"],
            input=raw,
            capture_output=True,
            timeout=_SIMCTL_TIMEOUT,
        )
        if converted.returncode != 0:
            raise DeviceError("could not parse simctl listapps output")
        apps = plistlib.loads(converted.stdout)
        return sorted(
            (
                {
                    "package": bundle_id,
                    "name": info.get("CFBundleDisplayName")
                    or info.get("CFBundleName")
                    or bundle_id,
                }
                for bundle_id, info in apps.items()
                if info.get("ApplicationType") == "User"
            ),
            key=lambda app: app["package"],
        )

    def launch_app(self, package: str) -> None:
        self._simctl("launch", self.id, package, timeout=60)

    def logs(self) -> str:
        raise DeviceError("simulator log capture is not supported yet")

    def _simctl(self, *args: str, timeout: float = _SIMCTL_TIMEOUT) -> bytes:
        cmd = ["xcrun", "simctl", *args]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except FileNotFoundError as exc:
            raise DeviceError("xcrun not found: install Xcode command line tools") from exc
        if result.returncode != 0:
            detail = result.stderr.decode(errors="replace").strip() or "unknown simctl error"
            raise DeviceError(f"simctl {args[0]} failed: {detail}")
        return result.stdout


def discover() -> list[IosSimDevice]:
    """Booted iOS Simulators as controllable devices."""
    try:
        simulators = list_simulators()
    except DeviceError:
        return []
    return [
        IosSimDevice(sim["udid"], sim["name"]) for sim in simulators if sim["state"] == "Booted"
    ]
