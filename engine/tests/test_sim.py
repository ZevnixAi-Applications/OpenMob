"""Unit tests for the simulator backend and WDA port registry (no simulator required)."""

import pytest

from openmob import sim
from openmob.sim import SIM_WDA_BASE_PORT, IosSimDevice, SimWdaRegistry

FAKE_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + b"\x00\x00\x00\x0dIHDR"
    + (1179).to_bytes(4, "big")
    + (2556).to_bytes(4, "big")
)


def test_registry_allocates_sequential_ports() -> None:
    registry = SimWdaRegistry(port_is_free=lambda port: True)
    assert registry.port_for("SIM-A") == SIM_WDA_BASE_PORT
    assert registry.port_for("SIM-B") == SIM_WDA_BASE_PORT + 1
    assert registry.port_for("SIM-C") == SIM_WDA_BASE_PORT + 2


def test_registry_ports_are_stable_per_udid() -> None:
    registry = SimWdaRegistry(port_is_free=lambda port: True)
    first = registry.port_for("SIM-A")
    registry.port_for("SIM-B")
    assert registry.port_for("SIM-A") == first


def test_registry_skips_busy_ports() -> None:
    busy = {SIM_WDA_BASE_PORT, SIM_WDA_BASE_PORT + 2}
    registry = SimWdaRegistry(port_is_free=lambda port: port not in busy)
    assert registry.port_for("SIM-A") == SIM_WDA_BASE_PORT + 1
    assert registry.port_for("SIM-B") == SIM_WDA_BASE_PORT + 3


def test_registry_url_for() -> None:
    registry = SimWdaRegistry(port_is_free=lambda port: True)
    assert registry.url_for("SIM-A") == f"http://127.0.0.1:{SIM_WDA_BASE_PORT}"


def test_registry_spawn_passes_port_via_test_runner_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """WDA reads USE_PORT; xcodebuild forwards TEST_RUNNER_USE_PORT with prefix stripped."""
    spawned: list[tuple[list[str], dict[str, str]]] = []

    class FakeProcess:
        def poll(self) -> None:
            return None

    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProcess:
        spawned.append((cmd, kwargs["env"]))
        assert kwargs.get("start_new_session") is True
        return FakeProcess()

    monkeypatch.setattr(sim.subprocess, "Popen", fake_popen)
    registry = SimWdaRegistry(port_is_free=lambda port: True)
    registry._spawn("SIM-A", 8105)
    ((cmd, env),) = spawned
    assert env["TEST_RUNNER_USE_PORT"] == "8105"
    assert "test-without-building" in cmd
    assert "id=SIM-A" in cmd
    assert registry._procs["SIM-A"] is not None


def test_sim_device_screen_size_uses_simctl_not_wda(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = IosSimDevice("SIM-A", "iPhone 17", wda_registry=SimWdaRegistry())
    monkeypatch.setattr(device, "_simctl", lambda *args, **kwargs: FAKE_PNG)
    assert (device.width, device.height) == (1179, 2556)
    assert device._wda_client is None  # sizing must not have started WDA


def test_sim_device_screenshot_via_simctl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_simctl(*args: str, **kwargs: object) -> bytes:
        calls.append(args)
        return FAKE_PNG

    device = IosSimDevice("SIM-A", "iPhone 17", wda_registry=SimWdaRegistry())
    monkeypatch.setattr(device, "_simctl", fake_simctl)
    assert device.screenshot() == FAKE_PNG
    assert calls == [("io", "SIM-A", "screenshot", "--type=png", "-")]


def test_discover_returns_only_booted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sim,
        "list_simulators",
        lambda: [
            {"name": "iPhone 17", "udid": "AAAA-1111", "state": "Booted"},
            {"name": "iPhone Air", "udid": "BBBB-2222", "state": "Shutdown"},
        ],
    )
    devices = sim.discover()
    assert [(d.id, d.name, d.platform, d.status) for d in devices] == [
        ("AAAA-1111", "iPhone 17", "ios", "online")
    ]
