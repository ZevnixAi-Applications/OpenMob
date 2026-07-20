"""Android device backend implemented over adb subprocess calls."""

import os
import re
import shutil
import subprocess
from functools import cache
from pathlib import Path

from openmob.device import Device, DeviceError

KEYCODES: dict[str, int] = {
    "home": 3,
    "back": 4,
    "power": 26,
    "volume_up": 24,
    "volume_down": 25,
    "enter": 66,
}

# Characters that must be backslash-escaped for `adb shell input text`.
_SHELL_SPECIALS = set("\\\"'`$&|;<>()*?~#[]{}!")


@cache
def find_adb() -> str:
    """Locate the adb binary, preferring the Android SDK install."""
    candidates = []
    if android_home := os.environ.get("ANDROID_HOME"):
        candidates.append(Path(android_home) / "platform-tools" / "adb")
    candidates.append(Path.home() / "Library/Android/sdk/platform-tools/adb")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    if on_path := shutil.which("adb"):
        return on_path
    raise DeviceError("adb not found: set ANDROID_HOME or add adb to PATH")


def escape_text(text: str) -> str:
    """Escape text for `adb shell input text` (spaces become %s)."""
    escaped = []
    for char in text:
        if char == " ":
            escaped.append("%s")
        elif char in _SHELL_SPECIALS:
            escaped.append("\\" + char)
        else:
            escaped.append(char)
    return "".join(escaped)


def parse_devices(output: str) -> list[tuple[str, str, str]]:
    """Parse `adb devices -l` output into (serial, state, model) tuples."""
    devices = []
    for line in output.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        serial, state = parts[0], parts[1]
        model = serial
        for part in parts[2:]:
            if part.startswith("model:"):
                model = part.removeprefix("model:").replace("_", " ")
        devices.append((serial, state, model))
    return devices


def parse_wm_size(output: str) -> tuple[int, int]:
    """Parse `adb shell wm size` output, preferring the override size."""
    sizes: dict[str, tuple[int, int]] = {}
    for match in re.finditer(r"(Physical|Override) size:\s*(\d+)x(\d+)", output):
        sizes[match.group(1)] = (int(match.group(2)), int(match.group(3)))
    if size := sizes.get("Override") or sizes.get("Physical"):
        return size
    raise DeviceError(f"could not parse wm size output: {output!r}")


class AndroidDevice(Device):
    """An Android device controlled via adb."""

    def __init__(self, serial: str, name: str, status: str = "online") -> None:
        self._serial = serial
        self._name = name
        self._status = status
        self._size: tuple[int, int] | None = None

    def _run(self, *args: str, timeout: float = 30) -> bytes:
        cmd = [find_adb(), "-s", self._serial, *args]
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        if result.returncode != 0:
            detail = result.stderr.decode(errors="replace").strip() or "unknown adb error"
            raise DeviceError(f"adb {' '.join(args)} failed: {detail}")
        return result.stdout

    def _shell(self, *args: str, timeout: float = 30) -> str:
        return self._run("shell", *args, timeout=timeout).decode(errors="replace")

    @property
    def id(self) -> str:
        return self._serial

    @property
    def name(self) -> str:
        return self._name

    @property
    def platform(self) -> str:
        return "android"

    @property
    def status(self) -> str:
        return self._status

    @property
    def width(self) -> int:
        return self._screen_size()[0]

    @property
    def height(self) -> int:
        return self._screen_size()[1]

    def _screen_size(self) -> tuple[int, int]:
        if self._size is None:
            self._size = parse_wm_size(self._shell("wm", "size"))
        return self._size

    def screenshot(self) -> bytes:
        png = self._run("exec-out", "screencap", "-p")
        if not png.startswith(b"\x89PNG"):
            raise DeviceError("screencap did not return a PNG")
        return png

    def tap(self, x: int, y: int) -> None:
        self._shell("input", "tap", str(x), str(y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._shell("input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms))

    def input_text(self, text: str) -> None:
        self._shell("input", "text", escape_text(text))

    def press_key(self, key: str) -> None:
        keycode = KEYCODES.get(key)
        if keycode is None:
            raise DeviceError(f"unknown key {key!r}, expected one of: {', '.join(KEYCODES)}")
        self._shell("input", "keyevent", str(keycode))

    def install_app(self, path: str) -> None:
        self._run("install", "-r", path, timeout=300)

    def uninstall_app(self, package: str) -> None:
        output = self._run("uninstall", package, timeout=120).decode(errors="replace")
        if "Success" not in output:
            raise DeviceError(f"uninstall failed: {output.strip()}")

    def list_apps(self) -> list[dict[str, str]]:
        output = self._shell("pm", "list", "packages", "-3")
        packages = sorted(
            line.removeprefix("package:").strip()
            for line in output.splitlines()
            if line.startswith("package:")
        )
        return [{"package": package, "name": package} for package in packages]

    def launch_app(self, package: str) -> None:
        output = self._shell(
            "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1"
        )
        if "No activities found" in output or "monkey aborted" in output:
            raise DeviceError(f"could not launch {package!r}")

    def logs(self) -> str:
        return self._shell("logcat", "-d", "-t", "500", timeout=60)


def discover() -> list[AndroidDevice]:
    """Discover connected Android devices via `adb devices -l`."""
    try:
        adb = find_adb()
    except DeviceError:
        return []
    result = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return []
    return [
        AndroidDevice(serial, model, "online" if state == "device" else "offline")
        for serial, state, model in parse_devices(result.stdout)
    ]
