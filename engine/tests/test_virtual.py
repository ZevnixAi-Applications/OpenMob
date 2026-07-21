"""Unit tests for the virtual device catalog (no emulator/simulator required)."""

import json

import pytest

from openmob import virtual
from openmob.device import DeviceError
from openmob.virtual import (
    VirtualDeviceNotFound,
    parse_avd_list,
    parse_emu_avd_name,
    parse_simctl_devices,
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
    assert virtual.launch("Pixel_7") == {"ok": True, "note": "booting"}
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
    assert virtual.launch("iPhone 17") == {"ok": True, "note": "booting"}
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
    assert virtual.launch("iPhone 17") == {"ok": True, "note": "already running"}
    assert ran == [["open", "-a", "Simulator"]]  # no boot, still surfaces the window
