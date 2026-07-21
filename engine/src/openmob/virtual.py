"""Virtual device catalog: Android AVDs and iOS Simulators (list + launch).

A "virtual device" is a device *image* on this machine that can be booted:
an Android AVD (launched with the SDK `emulator`) or an iOS Simulator
(booted with `simctl`). Once booted it shows up in `/devices` like any
other device — AVDs through adb, simulators through the sim backend.
"""

import contextlib
import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from functools import cache
from pathlib import Path

from openmob.android import find_adb, parse_devices
from openmob.device import DeviceError

# AVD names are restricted to these characters (no spaces), which also lets us
# filter emulator log noise ("INFO    | ...") out of `emulator -list-avds`.
_AVD_NAME = re.compile(r"^[A-Za-z0-9._-]+$")

_LIST_TIMEOUT = 15
# `sdkmanager --list` fetches the remote catalog, so it is slower than the
# purely-local emulator/avdmanager queries.
_CATALOG_TIMEOUT = 90
_CREATE_TIMEOUT = 180
# System-image download can take minutes; the job streams progress meanwhile.
_INSTALL_TIMEOUT = 3600

# Most recent percentage sdkmanager/avdmanager printed on a progress line.
_PROGRESS_RE = re.compile(r"(\d{1,3})%")
# `avdmanager list device` id line: `id: 39 or "pixel_7"`.
_DEVICE_ID_RE = re.compile(r'^id:\s*\d+\s+or\s+"([^"]+)"')
_DEVICE_NAME_RE = re.compile(r"^Name:\s*(.+)$")
# How many trailing log lines a create-job snapshot exposes.
_JOB_LOG_TAIL = 25


class VirtualDeviceNotFound(Exception):
    """Raised when no AVD or simulator matches the requested name."""

    def __init__(self, name: str) -> None:
        super().__init__(f"virtual device {name!r} not found")


class CreateJobNotFound(Exception):
    """Raised when no create-job matches the requested id."""

    def __init__(self, job_id: str) -> None:
        super().__init__(f"create job {job_id!r} not found")


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


def _sdk_root() -> Path:
    """The Android SDK root (env `ANDROID_HOME`, default `~/Library/Android/sdk`)."""
    if android_home := os.environ.get("ANDROID_HOME"):
        return Path(android_home)
    return Path.home() / "Library/Android/sdk"


def _find_cmdline_tool(name: str) -> str:
    """Locate an SDK cmdline-tool (`sdkmanager`/`avdmanager`)."""
    candidates = [
        _sdk_root() / "cmdline-tools" / "latest" / "bin" / name,
        _sdk_root() / "tools" / "bin" / name,
    ]
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    if on_path := shutil.which(name):
        return on_path
    raise DeviceError(
        f"{name} not found: install the Android SDK command-line tools "
        "(Android Studio > SDK Manager > SDK Tools > 'Android SDK Command-line Tools'), "
        "then set ANDROID_HOME"
    )


@cache
def find_sdkmanager() -> str:
    """Locate the `sdkmanager` binary."""
    return _find_cmdline_tool("sdkmanager")


@cache
def find_avdmanager() -> str:
    """Locate the `avdmanager` binary."""
    return _find_cmdline_tool("avdmanager")


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


def parse_sdkmanager_images(output: str) -> list[dict[str, str | bool]]:
    """Parse `sdkmanager --list` into system-image entries, split installed vs available.

    Returns [{"id","api","tag","abi","installed"}]. `sdkmanager --list` prints an
    "Installed packages:" table and an "Available Packages:" table, each a
    `path | version | description | location` layout; installed wins for images
    that (unusually) appear in both.
    """
    section: str | None = None
    images: dict[str, dict[str, str | bool]] = {}
    for raw in output.splitlines():
        low = raw.strip().lower()
        if low.startswith("installed packages"):
            section = "installed"
            continue
        if low.startswith("available packages"):
            section = "available"
            continue
        if low.startswith("available updates"):
            section = None
            continue
        if section is None:
            continue
        cell = raw.split("|", 1)[0].strip()
        if not cell.startswith("system-images;"):
            continue
        parts = cell.split(";")
        if len(parts) < 4:
            continue
        installed = section == "installed"
        if cell in images and not installed:
            continue  # keep the installed record over a duplicate available one
        images[cell] = {
            "id": cell,
            "api": parts[1].removeprefix("android-"),
            "tag": parts[2],
            "abi": parts[3],
            "installed": installed,
        }
    return list(images.values())


def parse_avd_devices(output: str) -> list[dict[str, str]]:
    """Parse `avdmanager list device` into [{"id","name"}] hardware profiles."""
    devices: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw in output.splitlines():
        line = raw.strip()
        if match := _DEVICE_ID_RE.match(line):
            current = {"id": match.group(1), "name": match.group(1)}
            devices.append(current)
        elif current is not None and (match := _DEVICE_NAME_RE.match(line)):
            current["name"] = match.group(1).strip()
    return devices


def parse_simctl_devicetypes(payload: str) -> list[dict[str, str]]:
    """Parse `xcrun simctl list devicetypes --json` into [{"id","name"}]."""
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise DeviceError("simctl returned invalid JSON") from exc
    return [
        {"id": item.get("identifier", ""), "name": item.get("name", "")}
        for item in data.get("devicetypes", [])
        if item.get("identifier")
    ]


def parse_simctl_runtimes(payload: str) -> list[dict[str, str | bool]]:
    """Parse `xcrun simctl list runtimes --json` into [{"id","name","available"}]."""
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise DeviceError("simctl returned invalid JSON") from exc
    return [
        {
            "id": item.get("identifier", ""),
            "name": item.get("name", ""),
            "available": bool(item.get("isAvailable")),
        }
        for item in data.get("runtimes", [])
        if item.get("identifier")
    ]


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


def launch(name: str, windowed: bool = False) -> dict[str, bool | str]:
    """Boot the named AVD or simulator. Idempotent: relaunching is a no-op.

    By default the target boots *headless* — no native emulator/Simulator window —
    so OpenMob mirrors it inside its own UI. Pass ``windowed=True`` to also open
    the platform's own window (the emulator UI / Simulator.app).
    """
    if name in list_avds():
        return _launch_avd(name, windowed=windowed)
    for sim in list_simulators():
        if sim["name"] == name:
            return _launch_simulator(sim, windowed=windowed)
    raise VirtualDeviceNotFound(name)


def _launch_avd(name: str, windowed: bool = False) -> dict[str, bool | str]:
    if name in running_avds():
        return {"ok": True, "note": "already running"}
    # Headless by default: `-no-window`/`-no-boot-anim` boot the AVD with no native
    # emulator window; it still registers with adb and OpenMob mirrors it via its
    # screen stream. `windowed=True` restores the emulator's own window.
    command = [find_emulator(), "-avd", name]
    if not windowed:
        command += ["-no-window", "-no-boot-anim"]
    subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"ok": True, "note": "booting"}


def _launch_simulator(sim: dict[str, str], windowed: bool = False) -> dict[str, bool | str]:
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
    # Headless by default: `simctl boot` alone runs the sim with no Simulator.app
    # window — OpenMob drives it through WDA + `simctl io screenshot`. Only surface
    # the Simulator.app window when the caller explicitly asks for it.
    if windowed:
        subprocess.run(["open", "-a", "Simulator"], capture_output=True, timeout=30)
    return {"ok": True, "note": note}


# --- device creation --------------------------------------------------------


def create_options() -> dict[str, dict]:
    """Installable images and hardware profiles for creating new virtual devices.

    Each platform section carries an `available` flag and, when unavailable, a
    human `reason` (missing cmdline-tools, no Xcode, etc.) so the UI can guide the
    user instead of showing an empty picker.
    """
    return {"android": _android_create_options(), "ios": _ios_create_options()}


def _android_create_options() -> dict:
    try:
        sdkmanager = find_sdkmanager()
        avdmanager = find_avdmanager()
    except DeviceError as exc:
        return {"available": False, "reason": str(exc), "device_profiles": [], "system_images": []}
    try:
        listing = subprocess.run(
            [sdkmanager, "--list"],
            capture_output=True,
            text=True,
            timeout=_CATALOG_TIMEOUT,
            env={**os.environ, "ANDROID_HOME": str(_sdk_root())},
        )
        devices = subprocess.run(
            [avdmanager, "list", "device"],
            capture_output=True,
            text=True,
            timeout=_LIST_TIMEOUT,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return {
            "available": False,
            "reason": f"could not query the Android SDK: {exc}",
            "device_profiles": [],
            "system_images": [],
        }
    return {
        "available": True,
        "reason": None,
        "device_profiles": parse_avd_devices(devices.stdout),
        "system_images": parse_sdkmanager_images(listing.stdout),
    }


def _ios_create_options() -> dict:
    try:
        types = subprocess.run(
            ["xcrun", "simctl", "list", "devicetypes", "--json"],
            capture_output=True,
            text=True,
            timeout=_LIST_TIMEOUT,
        )
        runtimes = subprocess.run(
            ["xcrun", "simctl", "list", "runtimes", "--json"],
            capture_output=True,
            text=True,
            timeout=_LIST_TIMEOUT,
        )
    except FileNotFoundError:
        return {
            "available": False,
            "reason": "xcrun not found: install Xcode to create iOS simulators",
            "device_types": [],
            "runtimes": [],
        }
    except (subprocess.SubprocessError, OSError) as exc:
        return {"available": False, "reason": str(exc), "device_types": [], "runtimes": []}
    if types.returncode != 0 or runtimes.returncode != 0:
        return {
            "available": False,
            "reason": "simctl failed: is Xcode installed and selected (xcode-select)?",
            "device_types": [],
            "runtimes": [],
        }
    parsed_runtimes = parse_simctl_runtimes(runtimes.stdout)
    reason = None if any(r["available"] for r in parsed_runtimes) else "no iOS runtimes installed"
    return {
        "available": reason is None,
        "reason": reason,
        "device_types": parse_simctl_devicetypes(types.stdout),
        "runtimes": parsed_runtimes,
    }


def _image_installed(system_image: str) -> bool:
    """True if a `system-images;...` package is already unpacked in the SDK."""
    parts = system_image.split(";")
    if len(parts) < 4:
        return False
    return (_sdk_root() / Path(parts[0], *parts[1:])).exists()


class CreateJob:
    """A tracked device-creation job (thread-safe snapshot for polling)."""

    def __init__(self, platform: str, name: str) -> None:
        self.id = uuid.uuid4().hex
        self.platform = platform
        self.name = name
        self._status = "queued"  # queued | running | succeeded | failed
        self._progress: int | None = None
        self._log: list[str] = []
        self._error: str | None = None
        self._device_id: str | None = None
        self._lock = threading.Lock()

    def append_log(self, line: str) -> None:
        with self._lock:
            self._log.append(line)

    def set_progress(self, percent: int) -> None:
        with self._lock:
            self._progress = percent

    def set_status(self, status: str, error: str | None = None) -> None:
        with self._lock:
            self._status = status
            if error is not None:
                self._error = error

    def set_device_id(self, device_id: str) -> None:
        with self._lock:
            self._device_id = device_id

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "id": self.id,
                "platform": self.platform,
                "name": self.name,
                "status": self._status,
                "progress": self._progress,
                "log": self._log[-_JOB_LOG_TAIL:],
                "error": self._error,
                "device_id": self._device_id,
            }


class CreateJobManager:
    """Runs device-creation jobs on background threads and tracks their state."""

    def __init__(self) -> None:
        self._jobs: dict[str, CreateJob] = {}
        self._lock = threading.Lock()

    def get(self, job_id: str) -> CreateJob:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise CreateJobNotFound(job_id)
        return job

    def start(self, platform: str, name: str, work) -> CreateJob:
        job = CreateJob(platform, name)
        with self._lock:
            self._jobs[job.id] = job
        thread = threading.Thread(target=self._run, args=(job, work), daemon=True)
        thread.start()
        return job

    @staticmethod
    def _run(job: CreateJob, work) -> None:
        job.set_status("running")
        try:
            work(job)
        except DeviceError as exc:
            job.append_log(f"error: {exc}")
            job.set_status("failed", error=str(exc))
        except Exception as exc:  # unexpected — still surface it to the UI
            job.append_log(f"error: {exc}")
            job.set_status("failed", error=str(exc))
        else:
            job.set_status("succeeded")


_job_manager = CreateJobManager()


def _stream_process(job: CreateJob, process: subprocess.Popen) -> int:
    """Drain a subprocess's output into the job log, tracking `NN%` progress.

    sdkmanager rewrites its progress bar in place with carriage returns, so the
    stream is split on both `\\r` and `\\n` rather than read line by line.
    """
    assert process.stdout is not None
    buffer = ""
    while True:
        chunk = process.stdout.read(256)
        if not chunk:
            break
        buffer += chunk
        pieces = re.split(r"[\r\n]", buffer)
        buffer = pieces.pop()
        for piece in pieces:
            text = piece.strip()
            if not text:
                continue
            job.append_log(text)
            if match := _PROGRESS_RE.search(text):
                job.set_progress(min(100, int(match.group(1))))
    if tail := buffer.strip():
        job.append_log(tail)
    return process.wait()


def _create_avd_job(name: str, device_profile: str, system_image: str):
    def work(job: CreateJob) -> None:
        sdkmanager = find_sdkmanager()
        avdmanager = find_avdmanager()
        env = {**os.environ, "ANDROID_HOME": str(_sdk_root())}
        if not _image_installed(system_image):
            job.append_log(f"Installing system image {system_image} …")
            process = subprocess.Popen(
                [sdkmanager, system_image],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
            # Auto-accept any license prompts, then let it run to completion.
            with contextlib.suppress(BrokenPipeError, OSError, ValueError):
                process.stdin.write("y\n" * 30)  # type: ignore[union-attr]
                process.stdin.flush()  # type: ignore[union-attr]
                process.stdin.close()  # type: ignore[union-attr]
            code = _stream_process(job, process)
            if code != 0:
                raise DeviceError(f"sdkmanager failed to install {system_image} (exit {code})")
            job.set_progress(100)
        else:
            job.append_log(f"System image {system_image} already installed.")
        job.append_log(f"Creating AVD {name} …")
        result = subprocess.run(
            [avdmanager, "create", "avd", "-n", name, "-k", system_image, "-d", device_profile,
             "--force"],
            input="no\n",  # decline the "custom hardware profile?" prompt
            capture_output=True,
            text=True,
            timeout=_CREATE_TIMEOUT,
            env=env,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip() or "unknown avdmanager error"
            raise DeviceError(f"avdmanager create failed: {detail}")
        job.set_device_id(name)
        job.append_log(f"AVD {name} created.")

    return work


def _create_simulator_job(name: str, device_type: str, runtime: str):
    def work(job: CreateJob) -> None:
        job.append_log(f"Creating simulator {name} …")
        try:
            result = subprocess.run(
                ["xcrun", "simctl", "create", name, device_type, runtime],
                capture_output=True,
                text=True,
                timeout=_CREATE_TIMEOUT,
            )
        except FileNotFoundError as exc:
            raise DeviceError("xcrun not found: install Xcode command line tools") from exc
        if result.returncode != 0:
            detail = result.stderr.strip() or "unknown simctl error"
            raise DeviceError(f"simctl create failed: {detail}")
        udid = result.stdout.strip()
        job.set_device_id(udid)
        job.append_log(f"Simulator {name} created ({udid}).")

    return work


def create_virtual_device(
    platform: str,
    name: str,
    device_profile: str | None = None,
    system_image: str | None = None,
    device_type: str | None = None,
    runtime: str | None = None,
) -> dict:
    """Validate a creation request and start a tracked job; returns the job snapshot."""
    name = (name or "").strip()
    if not name:
        raise DeviceError("a device name is required")
    if platform == "android":
        if not _AVD_NAME.match(name):
            raise DeviceError(
                "AVD name may contain only letters, numbers, '.', '_' and '-' (no spaces)"
            )
        if not system_image:
            raise DeviceError("system_image is required to create an Android AVD")
        if not device_profile:
            raise DeviceError("device_profile is required to create an Android AVD")
        work = _create_avd_job(name, device_profile, system_image)
    elif platform == "ios":
        if not device_type:
            raise DeviceError("device_type is required to create an iOS simulator")
        if not runtime:
            raise DeviceError("runtime is required to create an iOS simulator")
        work = _create_simulator_job(name, device_type, runtime)
    else:
        raise DeviceError(f"unknown platform {platform!r} (expected 'android' or 'ios')")
    return _job_manager.start(platform, name, work).snapshot()


def get_create_job(job_id: str) -> dict:
    """Snapshot of a create-job's status/progress/log for polling."""
    return _job_manager.get(job_id).snapshot()
