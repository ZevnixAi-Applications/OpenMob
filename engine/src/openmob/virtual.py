"""Virtual device catalog: Android AVDs and iOS Simulators (list + launch).

A "virtual device" is a device *image* on this machine that can be booted:
an Android AVD (launched with the SDK `emulator`) or an iOS Simulator
(booted with `simctl`). Once booted it shows up in `/devices` like any
other device — AVDs through adb, simulators through the sim backend.
"""

import json
import os
import re
import shutil
import subprocess
from functools import cache
from pathlib import Path

from openmob.android import find_adb, parse_devices
from openmob.device import DeviceError

# AVD names are restricted to these characters (no spaces), which also lets us
# filter emulator log noise ("INFO    | ...") out of `emulator -list-avds`.
_AVD_NAME = re.compile(r"^[A-Za-z0-9._-]+$")

_LIST_TIMEOUT = 15


class VirtualDeviceNotFound(Exception):
    """Raised when no AVD or simulator matches the requested name."""

    def __init__(self, name: str) -> None:
        super().__init__(f"virtual device {name!r} not found")


@cache
def find_emulator() -> str:
    """Locate the Android SDK emulator binary, mirroring `android.find_adb`."""
    candidates = []
    if android_home := os.environ.get("ANDROID_HOME"):
        candidates.append(Path(android_home) / "emulator" / "emulator")
    candidates.append(Path.home() / "Library/Android/sdk/emulator/emulator")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    if on_path := shutil.which("emulator"):
        return on_path
    raise DeviceError("emulator not found: set ANDROID_HOME or add emulator to PATH")


def parse_avd_list(output: str) -> list[str]:
    """Parse `emulator -list-avds` output, dropping log lines the emulator mixes in."""
    return [line.strip() for line in output.splitlines() if _AVD_NAME.match(line.strip())]


def parse_emu_avd_name(output: str) -> str:
    """Parse `adb -s SERIAL emu avd name` output (AVD name, then an "OK" line)."""
    for line in output.splitlines():
        line = line.strip()
        if line and line != "OK":
            return line
    return ""


def parse_simctl_devices(payload: str) -> list[dict[str, str]]:
    """Parse `xcrun simctl list devices --json` into [{"name","udid","state"}].

    Unavailable devices (runtime deleted, unsupported) are skipped.
    """
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise DeviceError("simctl returned invalid JSON") from exc
    devices = []
    for runtime_devices in data.get("devices", {}).values():
        for device in runtime_devices:
            if not device.get("isAvailable", False):
                continue
            devices.append(
                {
                    "name": device.get("name", ""),
                    "udid": device.get("udid", ""),
                    "state": device.get("state", ""),
                }
            )
    return devices


def list_avds() -> list[str]:
    """Names of all Android AVDs defined on this machine."""
    try:
        emulator = find_emulator()
    except DeviceError:
        return []
    result = subprocess.run(
        [emulator, "-list-avds"], capture_output=True, text=True, timeout=_LIST_TIMEOUT
    )
    if result.returncode != 0:
        return []
    return parse_avd_list(result.stdout)


def running_avds() -> dict[str, str]:
    """Map AVD name -> adb serial for every currently running emulator."""
    try:
        adb = find_adb()
    except DeviceError:
        return {}
    result = subprocess.run(
        [adb, "devices", "-l"], capture_output=True, text=True, timeout=_LIST_TIMEOUT
    )
    if result.returncode != 0:
        return {}
    running: dict[str, str] = {}
    for serial, state, _model in parse_devices(result.stdout):
        if not serial.startswith("emulator-") or state != "device":
            continue
        query = subprocess.run(
            [adb, "-s", serial, "emu", "avd", "name"],
            capture_output=True,
            text=True,
            timeout=_LIST_TIMEOUT,
        )
        if query.returncode != 0:
            continue
        if name := parse_emu_avd_name(query.stdout):
            running[name] = serial
    return running


def list_simulators() -> list[dict[str, str]]:
    """Available iOS Simulators as [{"name","udid","state"}]."""
    try:
        result = subprocess.run(
            ["xcrun", "simctl", "list", "devices", "--json"],
            capture_output=True,
            text=True,
            timeout=_LIST_TIMEOUT,
        )
    except FileNotFoundError:
        return []
    if result.returncode != 0:
        return []
    return parse_simctl_devices(result.stdout)


def list_virtual_devices() -> list[dict[str, str | None]]:
    """All launchable virtual devices (see docs/VIRTUAL_DEVICES.md)."""
    running = running_avds()
    virtual: list[dict[str, str | None]] = [
        {
            "name": name,
            "platform": "android",
            "kind": "avd",
            "state": "running" if name in running else "stopped",
            "device_id": running.get(name),
        }
        for name in list_avds()
    ]
    virtual.extend(
        {
            "name": sim["name"],
            "platform": "ios",
            "kind": "simulator",
            "state": "running" if sim["state"] == "Booted" else "stopped",
            "device_id": sim["udid"],
        }
        for sim in list_simulators()
    )
    return virtual


def launch(name: str) -> dict[str, bool | str]:
    """Boot the named AVD or simulator. Idempotent: relaunching is a no-op."""
    if name in list_avds():
        return _launch_avd(name)
    for sim in list_simulators():
        if sim["name"] == name:
            return _launch_simulator(sim)
    raise VirtualDeviceNotFound(name)


def _launch_avd(name: str) -> dict[str, bool | str]:
    if name in running_avds():
        return {"ok": True, "note": "already running"}
    subprocess.Popen(
        [find_emulator(), "-avd", name],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"ok": True, "note": "booting"}


def _launch_simulator(sim: dict[str, str]) -> dict[str, bool | str]:
    note = "booting"
    if sim["state"] == "Booted":
        note = "already running"
    else:
        result = subprocess.run(
            ["xcrun", "simctl", "boot", sim["udid"]], capture_output=True, timeout=60
        )
        # `simctl boot` on an already-booted device fails with "current state: Booted".
        if result.returncode != 0 and b"current state: Booted" not in result.stderr:
            detail = result.stderr.decode(errors="replace").strip() or "unknown simctl error"
            raise DeviceError(f"simctl boot failed: {detail}")
    subprocess.run(["open", "-a", "Simulator"], capture_output=True, timeout=30)
    return {"ok": True, "note": note}
