"""Unit tests for the virtual device catalog (no emulator/simulator required)."""

import io
import json

import pytest

from openmob import virtual
from openmob.device import DeviceError
from openmob.virtual import (
    CreateJob,
    CreateJobNotFound,
    VirtualDeviceNotFound,
    parse_avd_devices,
    parse_avd_list,
    parse_emu_avd_name,
    parse_sdkmanager_images,
    parse_simctl_devices,
    parse_simctl_devicetypes,
    parse_simctl_runtimes,
)

SIMCTL_JSON = json.dumps(
    {
        "devices": {
            "com.apple.CoreSimulator.SimRuntime.iOS-26-3": [
                {
                    "name": "iPhone 17",
                    "udid": "AAAA-1111",
                    "state": "Booted",
                    "isAvailable": True,
                },
                {
                    "name": "iPhone Air",
                    "udid": "BBBB-2222",
                    "state": "Shutdown",
                    "isAvailable": True,
                },
            ],
            "com.apple.CoreSimulator.SimRuntime.iOS-17-0": [
                {
                    "name": "Old iPhone",
                    "udid": "CCCC-3333",
                    "state": "Shutdown",
                    "isAvailable": False,
                    "availabilityError": "runtime profile not found",
                },
            ],
        }
    }
)


def test_parse_avd_list() -> None:
    assert parse_avd_list("Pixel_7\nPixel_Tablet_API_34\n") == ["Pixel_7", "Pixel_Tablet_API_34"]


def test_parse_avd_list_drops_log_noise() -> None:
    output = "INFO    | Storing crashdata in: /tmp/emu.db\nPixel_7\n\n"
    assert parse_avd_list(output) == ["Pixel_7"]


def test_parse_avd_list_empty() -> None:
    assert parse_avd_list("") == []


def test_parse_emu_avd_name() -> None:
    assert parse_emu_avd_name("Pixel_7\r\nOK\r\n") == "Pixel_7"
    assert parse_emu_avd_name("Pixel_7\nOK\n") == "Pixel_7"
    assert parse_emu_avd_name("OK\n") == ""
    assert parse_emu_avd_name("") == ""


def test_parse_simctl_devices_skips_unavailable() -> None:
    devices = parse_simctl_devices(SIMCTL_JSON)
    assert devices == [
        {"name": "iPhone 17", "udid": "AAAA-1111", "state": "Booted"},
        {"name": "iPhone Air", "udid": "BBBB-2222", "state": "Shutdown"},
    ]


def test_parse_simctl_devices_rejects_garbage() -> None:
    with pytest.raises(DeviceError):
        parse_simctl_devices("not json")


def test_running_avds_matches_serials(monkeypatch: pytest.MonkeyPatch) -> None:
    """`adb devices` serials are matched to AVD names via `adb -s S emu avd name`."""
    avd_by_serial = {"emulator-5554": "Pixel_7\nOK\n", "emulator-5556": "Pixel_Tablet\nOK\n"}

    class Result:
        def __init__(self, stdout: str) -> None:
            self.returncode = 0
            self.stdout = stdout

    def fake_run(cmd: list[str], **kwargs: object) -> Result:
        if cmd[1:] == ["devices", "-l"]:
            return Result(
                "List of devices attached\n"
                "emulator-5554          device product:sdk model:sdk device:emu\n"
                "emulator-5556          device product:sdk model:sdk device:emu\n"
                "emulator-5558          offline\n"
                "1585dda1               device model:23073RPBFG\n"
            )
        assert cmd[1] == "-s" and cmd[3:] == ["emu", "avd", "name"]
        return Result(avd_by_serial[cmd[2]])

    monkeypatch.setattr(virtual, "find_adb", lambda: "adb")
    monkeypatch.setattr(virtual.subprocess, "run", fake_run)
    assert virtual.running_avds() == {
        "Pixel_7": "emulator-5554",
        "Pixel_Tablet": "emulator-5556",
    }


def test_list_virtual_devices_combines_backends(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(virtual, "list_avds", lambda: ["Pixel_7", "Pixel_Tablet"])
    monkeypatch.setattr(virtual, "running_avds", lambda: {"Pixel_7": "emulator-5554"})
    monkeypatch.setattr(virtual, "list_simulators", lambda: parse_simctl_devices(SIMCTL_JSON))
    assert virtual.list_virtual_devices() == [
        {
            "name": "Pixel_7",
            "platform": "android",
            "kind": "avd",
            "state": "running",
            "device_id": "emulator-5554",
        },
        {
            "name": "Pixel_Tablet",
            "platform": "android",
            "kind": "avd",
            "state": "stopped",
            "device_id": None,
        },
        {
            "name": "iPhone 17",
            "platform": "ios",
            "kind": "simulator",
            "state": "running",
            "device_id": "AAAA-1111",
        },
        {
            "name": "iPhone Air",
            "platform": "ios",
            "kind": "simulator",
            "state": "stopped",
            "device_id": "BBBB-2222",
        },
    ]


def test_launch_unknown_name_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(virtual, "list_avds", lambda: [])
    monkeypatch.setattr(virtual, "list_simulators", lambda: [])
    with pytest.raises(VirtualDeviceNotFound):
        virtual.launch("Nope")


def test_launch_avd_spawns_detached(monkeypatch: pytest.MonkeyPatch) -> None:
    spawned: list[list[str]] = []

    def fake_popen(cmd: list[str], **kwargs: object) -> object:
        spawned.append(cmd)
        assert kwargs.get("start_new_session") is True
        return object()

    monkeypatch.setattr(virtual, "list_avds", lambda: ["Pixel_7"])
    monkeypatch.setattr(virtual, "running_avds", lambda: {})
    monkeypatch.setattr(virtual, "find_emulator", lambda: "emulator")
    monkeypatch.setattr(virtual.subprocess, "Popen", fake_popen)
    # Headless by default: no native emulator window.
    assert virtual.launch("Pixel_7") == {"ok": True, "note": "booting"}
    assert spawned == [["emulator", "-avd", "Pixel_7", "-no-window", "-no-boot-anim"]]


def test_launch_avd_windowed_opens_native_window(monkeypatch: pytest.MonkeyPatch) -> None:
    spawned: list[list[str]] = []

    def fake_popen(cmd: list[str], **kwargs: object) -> object:
        spawned.append(cmd)
        return object()

    monkeypatch.setattr(virtual, "list_avds", lambda: ["Pixel_7"])
    monkeypatch.setattr(virtual, "running_avds", lambda: {})
    monkeypatch.setattr(virtual, "find_emulator", lambda: "emulator")
    monkeypatch.setattr(virtual.subprocess, "Popen", fake_popen)
    assert virtual.launch("Pixel_7", windowed=True) == {"ok": True, "note": "booting"}
    assert spawned == [["emulator", "-avd", "Pixel_7"]]


def test_launch_avd_already_running_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(virtual, "list_avds", lambda: ["Pixel_7"])
    monkeypatch.setattr(virtual, "running_avds", lambda: {"Pixel_7": "emulator-5554"})
    monkeypatch.setattr(virtual.subprocess, "Popen", lambda *a, **k: pytest.fail("must not spawn"))
    assert virtual.launch("Pixel_7") == {"ok": True, "note": "already running"}


def test_launch_simulator_boots_and_opens(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[list[str]] = []

    class Result:
        returncode = 0
        stderr = b""

    def fake_run(cmd: list[str], **kwargs: object) -> Result:
        ran.append(cmd)
        return Result()

    monkeypatch.setattr(virtual, "list_avds", lambda: [])
    monkeypatch.setattr(
        virtual,
        "list_simulators",
        lambda: [{"name": "iPhone 17", "udid": "AAAA-1111", "state": "Shutdown"}],
    )
    monkeypatch.setattr(virtual.subprocess, "run", fake_run)
    # Headless by default: boots the sim but does not open Simulator.app.
    assert virtual.launch("iPhone 17") == {"ok": True, "note": "booting"}
    assert ran == [["xcrun", "simctl", "boot", "AAAA-1111"]]


def test_launch_simulator_windowed_opens_app(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[list[str]] = []

    class Result:
        returncode = 0
        stderr = b""

    def fake_run(cmd: list[str], **kwargs: object) -> Result:
        ran.append(cmd)
        return Result()

    monkeypatch.setattr(virtual, "list_avds", lambda: [])
    monkeypatch.setattr(
        virtual,
        "list_simulators",
        lambda: [{"name": "iPhone 17", "udid": "AAAA-1111", "state": "Shutdown"}],
    )
    monkeypatch.setattr(virtual.subprocess, "run", fake_run)
    assert virtual.launch("iPhone 17", windowed=True) == {"ok": True, "note": "booting"}
    assert ran == [
        ["xcrun", "simctl", "boot", "AAAA-1111"],
        ["open", "-a", "Simulator"],
    ]


def test_launch_simulator_already_booted(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[list[str]] = []

    class Result:
        returncode = 0
        stderr = b""

    def fake_run(cmd: list[str], **kwargs: object) -> Result:
        ran.append(cmd)
        return Result()

    monkeypatch.setattr(virtual, "list_avds", lambda: [])
    monkeypatch.setattr(
        virtual,
        "list_simulators",
        lambda: [{"name": "iPhone 17", "udid": "AAAA-1111", "state": "Booted"}],
    )
    monkeypatch.setattr(virtual.subprocess, "run", fake_run)
    # Already booted + headless default: nothing runs (no boot, no window).
    assert virtual.launch("iPhone 17") == {"ok": True, "note": "already running"}
    assert ran == []


# --- creation: parsers ------------------------------------------------------

SDKMANAGER_LIST = """\
Loading package information...
Installed packages:
  Path                                                             | Version | Description         | Location
  -------                                                          | ------- | -------             | -------
  emulator                                                         | 36.1.9  | Android Emulator    | emulator
  system-images;android-37.0;google_apis_playstore_ps16k;arm64-v8a | 5       | Play ARM 64 v8a     | system-images/android-37.0/google_apis_playstore_ps16k/arm64-v8a

Available Packages:
  Path                                             | Version | Description
  -------                                          | ------- | -------
  build-tools;35.0.0                               | 35.0.0  | Android SDK Build-Tools 35
  system-images;android-35;google_apis;arm64-v8a   | 12      | Google APIs ARM 64 v8a System Image
  system-images;android-34;default;x86_64          | 3       | Intel x86_64 Atom System Image
"""


def test_parse_sdkmanager_images_splits_installed_and_available() -> None:
    images = parse_sdkmanager_images(SDKMANAGER_LIST)
    assert images == [
        {
            "id": "system-images;android-37.0;google_apis_playstore_ps16k;arm64-v8a",
            "api": "37.0",
            "tag": "google_apis_playstore_ps16k",
            "abi": "arm64-v8a",
            "installed": True,
        },
        {
            "id": "system-images;android-35;google_apis;arm64-v8a",
            "api": "35",
            "tag": "google_apis",
            "abi": "arm64-v8a",
            "installed": False,
        },
        {
            "id": "system-images;android-34;default;x86_64",
            "api": "34",
            "tag": "default",
            "abi": "x86_64",
            "installed": False,
        },
    ]


def test_parse_sdkmanager_images_installed_wins_over_available() -> None:
    listing = (
        "Installed packages:\n"
        "  system-images;android-35;google_apis;arm64-v8a | 1 | x | y\n"
        "Available Packages:\n"
        "  system-images;android-35;google_apis;arm64-v8a | 2 | x\n"
    )
    images = parse_sdkmanager_images(listing)
    assert len(images) == 1
    assert images[0]["installed"] is True


def test_parse_sdkmanager_images_empty() -> None:
    assert parse_sdkmanager_images("") == []


AVDMANAGER_DEVICES = """\
Available devices definitions:
id: 0 or "automotive_1024p_landscape"
    Name: Automotive (1024p landscape)
    OEM : Google
    Tag : android-automotive-playstore
---------
id: 39 or "pixel_7"
    Name: Pixel 7
    OEM : Google
---------
id: 9 or "Galaxy Nexus"
    Name: Galaxy Nexus
    OEM : Google
"""


def test_parse_avd_devices() -> None:
    devices = parse_avd_devices(AVDMANAGER_DEVICES)
    assert devices == [
        {"id": "automotive_1024p_landscape", "name": "Automotive (1024p landscape)"},
        {"id": "pixel_7", "name": "Pixel 7"},
        {"id": "Galaxy Nexus", "name": "Galaxy Nexus"},
    ]


def test_parse_avd_devices_empty() -> None:
    assert parse_avd_devices("Available devices definitions:\n") == []


DEVICETYPES_JSON = json.dumps(
    {
        "devicetypes": [
            {
                "name": "iPhone 17 Pro",
                "identifier": "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro",
                "productFamily": "iPhone",
            },
            {
                "name": "iPad Pro 11-inch",
                "identifier": "com.apple.CoreSimulator.SimDeviceType.iPad-Pro-11",
                "productFamily": "iPad",
            },
            {"name": "no identifier"},
        ]
    }
)

RUNTIMES_JSON = json.dumps(
    {
        "runtimes": [
            {
                "name": "iOS 26.3",
                "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-3",
                "isAvailable": True,
            },
            {
                "name": "iOS 17.0",
                "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-17-0",
                "isAvailable": False,
            },
        ]
    }
)


def test_parse_simctl_devicetypes() -> None:
    assert parse_simctl_devicetypes(DEVICETYPES_JSON) == [
        {"id": "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro", "name": "iPhone 17 Pro"},
        {"id": "com.apple.CoreSimulator.SimDeviceType.iPad-Pro-11", "name": "iPad Pro 11-inch"},
    ]


def test_parse_simctl_runtimes() -> None:
    assert parse_simctl_runtimes(RUNTIMES_JSON) == [
        {"id": "com.apple.CoreSimulator.SimRuntime.iOS-26-3", "name": "iOS 26.3", "available": True},
        {
            "id": "com.apple.CoreSimulator.SimRuntime.iOS-17-0",
            "name": "iOS 17.0",
            "available": False,
        },
    ]


def test_parse_simctl_runtimes_rejects_garbage() -> None:
    with pytest.raises(DeviceError):
        parse_simctl_runtimes("not json")


# --- creation: validation ---------------------------------------------------


def test_create_rejects_unknown_platform() -> None:
    with pytest.raises(DeviceError, match="unknown platform"):
        virtual.create_virtual_device(platform="symbian", name="x")


def test_create_requires_name() -> None:
    with pytest.raises(DeviceError, match="name is required"):
        virtual.create_virtual_device(platform="android", name="   ")


def test_create_android_rejects_spaces_in_name() -> None:
    with pytest.raises(DeviceError, match="AVD name"):
        virtual.create_virtual_device(
            platform="android",
            name="my avd",
            device_profile="pixel_7",
            system_image="system-images;android-35;google_apis;arm64-v8a",
        )


def test_create_android_requires_image_and_profile() -> None:
    with pytest.raises(DeviceError, match="system_image is required"):
        virtual.create_virtual_device(platform="android", name="Test", device_profile="pixel_7")
    with pytest.raises(DeviceError, match="device_profile is required"):
        virtual.create_virtual_device(
            platform="android",
            name="Test",
            system_image="system-images;android-35;google_apis;arm64-v8a",
        )


def test_create_ios_requires_type_and_runtime() -> None:
    with pytest.raises(DeviceError, match="device_type is required"):
        virtual.create_virtual_device(platform="ios", name="My iPhone", runtime="rt")
    with pytest.raises(DeviceError, match="runtime is required"):
        virtual.create_virtual_device(platform="ios", name="My iPhone", device_type="dt")


# --- creation: command construction + job lifecycle -------------------------


def _wait_for(job_id: str, status: str, timeout: float = 5.0) -> dict:
    import time

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = virtual.get_create_job(job_id)
        if snapshot["status"] == status:
            return snapshot
        time.sleep(0.01)
    raise AssertionError(f"job never reached {status!r}: {virtual.get_create_job(job_id)}")


def test_create_simulator_command_and_success(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = "NEW-UDID-1234\n"
        stderr = ""

    def fake_run(cmd: list[str], **kwargs: object) -> Result:
        ran.append(cmd)
        return Result()

    monkeypatch.setattr(virtual.subprocess, "run", fake_run)
    snapshot = virtual.create_virtual_device(
        platform="ios",
        name="My iPhone",
        device_type="com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro",
        runtime="com.apple.CoreSimulator.SimRuntime.iOS-26-3",
    )
    assert snapshot["status"] in {"queued", "running", "succeeded"}
    final = _wait_for(snapshot["id"], "succeeded")
    assert final["device_id"] == "NEW-UDID-1234"
    assert ran == [
        [
            "xcrun",
            "simctl",
            "create",
            "My iPhone",
            "com.apple.CoreSimulator.SimDeviceType.iPhone-17-Pro",
            "com.apple.CoreSimulator.SimRuntime.iOS-26-3",
        ]
    ]


def test_create_simulator_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 1
        stdout = ""
        stderr = "Invalid runtime"

    monkeypatch.setattr(virtual.subprocess, "run", lambda *a, **k: Result())
    snapshot = virtual.create_virtual_device(
        platform="ios", name="Bad", device_type="dt", runtime="rt"
    )
    final = _wait_for(snapshot["id"], "failed")
    assert "Invalid runtime" in final["error"]


def test_create_avd_installs_missing_image_then_creates(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[list[str]] = []

    monkeypatch.setattr(virtual, "find_sdkmanager", lambda: "sdkmanager")
    monkeypatch.setattr(virtual, "find_avdmanager", lambda: "avdmanager")
    monkeypatch.setattr(virtual, "_image_installed", lambda image: False)

    class FakePopen:
        def __init__(self, cmd: list[str], **kwargs: object) -> None:
            created.append(cmd)
            self.stdin = io.StringIO()
            self.stdout = io.StringIO("Downloading...  [====   ] 50%\nDone\n")

        def wait(self) -> int:
            return 0

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd: list[str], **kwargs: object) -> Result:
        created.append(cmd)
        return Result()

    monkeypatch.setattr(virtual.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(virtual.subprocess, "run", fake_run)

    snapshot = virtual.create_virtual_device(
        platform="android",
        name="Test_AVD",
        device_profile="pixel_7",
        system_image="system-images;android-35;google_apis;arm64-v8a",
    )
    final = _wait_for(snapshot["id"], "succeeded")
    assert final["device_id"] == "Test_AVD"
    assert final["progress"] == 100
    # sdkmanager install (Popen) first, then avdmanager create (run).
    assert created[0] == ["sdkmanager", "system-images;android-35;google_apis;arm64-v8a"]
    assert created[1] == [
        "avdmanager",
        "create",
        "avd",
        "-n",
        "Test_AVD",
        "-k",
        "system-images;android-35;google_apis;arm64-v8a",
        "-d",
        "pixel_7",
        "--force",
    ]


def test_create_avd_skips_install_when_image_present(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(virtual, "find_sdkmanager", lambda: "sdkmanager")
    monkeypatch.setattr(virtual, "find_avdmanager", lambda: "avdmanager")
    monkeypatch.setattr(virtual, "_image_installed", lambda image: True)

    def no_popen(*a: object, **k: object) -> object:
        raise AssertionError("must not download an already-installed image")

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(cmd: list[str], **kwargs: object) -> Result:
        calls.append(cmd[0])
        return Result()

    monkeypatch.setattr(virtual.subprocess, "Popen", no_popen)
    monkeypatch.setattr(virtual.subprocess, "run", fake_run)

    snapshot = virtual.create_virtual_device(
        platform="android",
        name="Fast_AVD",
        device_profile="pixel_7",
        system_image="system-images;android-37.0;google_apis_playstore_ps16k;arm64-v8a",
    )
    final = _wait_for(snapshot["id"], "succeeded")
    assert calls == ["avdmanager"]
    assert final["device_id"] == "Fast_AVD"


def test_create_avd_failure_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(virtual, "find_sdkmanager", lambda: "sdkmanager")
    monkeypatch.setattr(virtual, "find_avdmanager", lambda: "avdmanager")
    monkeypatch.setattr(virtual, "_image_installed", lambda image: True)

    class Result:
        returncode = 1
        stdout = ""
        stderr = "Package path is not valid"

    monkeypatch.setattr(virtual.subprocess, "run", lambda *a, **k: Result())
    snapshot = virtual.create_virtual_device(
        platform="android",
        name="Broken",
        device_profile="pixel_7",
        system_image="system-images;bogus",
    )
    final = _wait_for(snapshot["id"], "failed")
    assert "Package path is not valid" in final["error"]


def test_get_create_job_unknown_raises() -> None:
    with pytest.raises(CreateJobNotFound):
        virtual.get_create_job("does-not-exist")


def test_stream_process_tracks_progress_and_log() -> None:
    job = CreateJob("android", "X")

    class FakeProc:
        def __init__(self) -> None:
            self.stdout = io.StringIO("fetch  [==   ] 20%\rfetch  [=====] 80%\rDone downloading\n")

        def wait(self) -> int:
            return 0

    code = virtual._stream_process(job, FakeProc())
    snapshot = job.snapshot()
    assert code == 0
    assert snapshot["progress"] == 80
    assert "Done downloading" in snapshot["log"]
