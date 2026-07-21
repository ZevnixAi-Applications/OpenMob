"""Android device backend implemented over adb subprocess calls."""

import os
import re
import shutil
import subprocess
from functools import cache
from pathlib import Path

from openmob import videostream
from openmob.device import Device, DeviceError
from openmob.logstream import LogStream, apply_filter

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


def parse_dropbox_crashes(output: str) -> list[dict[str, str]]:
    """Parse `dumpsys dropbox --print data_app_crash` output into crash summaries.

    Each entry starts with a `====...` separator followed by a
    `YYYY-MM-DD HH:MM:SS data_app_crash (text, N bytes)` line, key/value headers
    (Process, Package, ...), a blank line, then the exception + stack trace.
    """
    crashes = []
    entries = re.split(r"^={10,}\s*$", output, flags=re.MULTILINE)
    for entry in entries[1:]:
        lines = entry.strip().splitlines()
        if not lines:
            continue
        header = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) data_app_crash", lines[0])
        if header is None:
            continue
        crash = {"date": header.group(1), "process": "", "exception": ""}
        in_headers = True
        for line in lines[1:]:
            if in_headers:
                if line.startswith("Process:"):
                    crash["process"] = line.removeprefix("Process:").strip()
                elif not line.strip():
                    in_headers = False
            elif line.strip():
                crash["exception"] = line.strip()  # first line of the exception block
                break
        crashes.append(crash)
    crashes.reverse()  # dropbox prints oldest first; we want newest first
    return crashes


def parse_crash_buffer(output: str) -> list[dict[str, str]]:
    """Parse `logcat -d -b crash` output into crash summaries.

    Crashes appear as AndroidRuntime blocks:
        07-21 10:57:41.225  5776  5776 E AndroidRuntime: FATAL EXCEPTION: main
        ... E AndroidRuntime: Process: com.example.app, PID: 5776
        ... E AndroidRuntime: java.lang.RuntimeException: boom
    """
    prefix = re.compile(
        r"^(?P<date>\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+\s+\d+\s+\d+\s+[EF] AndroidRuntime:\s?"
        r"(?P<msg>.*)$"
    )
    crashes: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in output.splitlines():
        match = prefix.match(line)
        if match is None:
            continue
        msg = match.group("msg")
        if msg.startswith("FATAL EXCEPTION"):
            current = {"date": match.group("date"), "process": "", "exception": ""}
            crashes.append(current)
        elif current is not None:
            if msg.startswith("Process:"):
                current["process"] = msg.removeprefix("Process:").split(",")[0].strip()
            elif not current["exception"] and not msg.startswith(("\t", "at ")):
                current["exception"] = msg.strip()
    crashes.reverse()
    return crashes


def parse_battery_level(output: str) -> int | None:
    """Parse the `level:` line from `dumpsys battery` output."""
    if match := re.search(r"^\s*level:\s*(\d+)\s*$", output, flags=re.MULTILINE):
        return int(match.group(1))
    return None


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

    def stream_frames(self) -> videostream.FrameStream:
        """Stream JPEG frames of the live screen via a screenrecord+ffmpeg pipeline.

        Yields the newest frame only (stale frames are dropped) and re-yields the
        previous frame after ~1 s of no display updates. Call ``close()`` on the
        returned stream to tear the pipeline down. Raises DeviceError if ffmpeg
        is missing or the pipeline cannot produce frames.
        """
        return videostream.FrameStream(find_adb(), self._serial, self._screen_size())

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
        output = self._shell("monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
        if "No activities found" in output or "monkey aborted" in output:
            raise DeviceError(f"could not launch {package!r}")

    def logs(self, lines: int = 200, filter_str: str | None = None) -> str:
        # Over-fetch when filtering so `lines` matching lines usually survive the filter.
        fetch = lines if not filter_str else max(lines * 10, 2000)
        output = self._shell("logcat", "-d", "-t", str(fetch), timeout=60)
        return apply_filter(output, filter_str, lines)

    def stream_logs(self) -> LogStream:
        # -T 1: start from the most recent line instead of replaying the whole buffer.
        return LogStream([find_adb(), "-s", self._serial, "logcat", "-T", "1"])

    def crash_reports(self, limit: int = 5) -> list[dict[str, str]]:
        crashes = parse_dropbox_crashes(
            self._shell("dumpsys", "dropbox", "--print", "data_app_crash", timeout=60)
        )
        if not crashes:  # dropbox can be empty/pruned; fall back to the crash log buffer
            crashes = parse_crash_buffer(self._shell("logcat", "-d", "-b", "crash", timeout=60))
        return crashes[:limit]

    def open_url(self, url: str) -> None:
        output = self._shell("am", "start", "-a", "android.intent.action.VIEW", "-d", url)
        if "Error" in output or "does not exist" in output:
            raise DeviceError(f"could not open {url!r}: {output.strip()}")

    def clear_app_data(self, package: str) -> None:
        output = self._shell("pm", "clear", package, timeout=60)
        if "Success" not in output:
            raise DeviceError(f"pm clear failed: {output.strip()}")

    def force_stop(self, package: str) -> None:
        self._shell("am", "force-stop", package)

    def push_file(self, local_path: str, device_path: str) -> None:
        if not Path(local_path).is_file():
            raise DeviceError(f"local file not found: {local_path}")
        self._run("push", local_path, device_path, timeout=300)

    def pull_file(self, device_path: str, local_path: str) -> None:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        self._run("pull", device_path, local_path, timeout=300)

    def system_info(self) -> dict[str, str | int]:
        info: dict[str, str | int] = {
            "os_version": self._shell("getprop", "ro.build.version.release").strip(),
            "sdk": self._shell("getprop", "ro.build.version.sdk").strip(),
            "model": self._shell("getprop", "ro.product.model").strip(),
            "manufacturer": self._shell("getprop", "ro.product.manufacturer").strip(),
        }
        if (level := parse_battery_level(self._shell("dumpsys", "battery"))) is not None:
            info["battery_percent"] = level
        return info

    def forward_tcp(self, remote_port: int) -> int:
        """Forward a free local TCP port to `remote_port` on the device; return the local port."""
        output = self._run("forward", "tcp:0", f"tcp:{remote_port}").decode().strip()
        try:
            return int(output)
        except ValueError as exc:
            raise DeviceError(f"unexpected adb forward output: {output!r}") from exc


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
