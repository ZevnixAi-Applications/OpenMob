"""Route smoke tests against a fake in-memory device (no hardware required)."""

import queue
import time

import pytest
from fastapi.testclient import TestClient

from openmob import server
from openmob.device import Device, DeviceError

FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


class FakeLogStream:
    def __init__(self, lines: list[str]) -> None:
        self._queue: queue.Queue[str | None] = queue.Queue()
        for line in lines:
            self._queue.put(line)
        self.closed = False

    def readline(self) -> str | None:
        if self.closed:
            return None
        return self._queue.get(timeout=5)

    def close(self) -> None:
        self.closed = True
        self._queue.put(None)


class FakeDevice(Device):
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.log_stream = FakeLogStream(["line one", "boom happened", "line three"])

    @property
    def id(self) -> str:
        return "fake-1"

    @property
    def name(self) -> str:
        return "Fake Device"

    @property
    def platform(self) -> str:
        return "android"

    @property
    def status(self) -> str:
        return "online"

    @property
    def width(self) -> int:
        return 1080

    @property
    def height(self) -> int:
        return 2400

    def screenshot(self) -> bytes:
        return FAKE_PNG

    def tap(self, x: int, y: int) -> None:
        self.calls.append(("tap", x, y))

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self.calls.append(("swipe", x1, y1, x2, y2, duration_ms))

    def input_text(self, text: str) -> None:
        self.calls.append(("input_text", text))

    def press_key(self, key: str) -> None:
        self.calls.append(("press_key", key))

    def install_app(self, path: str) -> None:
        self.calls.append(("install_app", path))

    def uninstall_app(self, package: str) -> None:
        self.calls.append(("uninstall_app", package))

    def list_apps(self) -> list[dict[str, str]]:
        return [{"package": "com.example.app", "name": "Example"}]

    def launch_app(self, package: str) -> None:
        self.calls.append(("launch_app", package))

    def logs(self, lines: int = 200, filter_str: str | None = None, scope=None) -> str:
        self.calls.append(("logs", lines, filter_str, scope))
        return "log line 1\nlog line 2"

    def stream_logs(self, scope=None) -> FakeLogStream:
        self.calls.append(("stream_logs", scope))
        return self.log_stream

    def crash_reports(self, limit: int = 5) -> list[dict[str, str]]:
        return [{"date": "2026-07-21", "process": "com.example.app", "exception": "boom"}][:limit]

    def open_url(self, url: str) -> None:
        self.calls.append(("open_url", url))

    def clear_app_data(self, package: str) -> None:
        if package == "com.ios.unsupported":
            raise DeviceError("clearing app data is not supported on iOS")
        self.calls.append(("clear_app_data", package))

    def force_stop(self, package: str) -> None:
        self.calls.append(("force_stop", package))

    def push_file(self, local_path: str, device_path: str) -> None:
        self.calls.append(("push_file", local_path, device_path))

    def pull_file(self, device_path: str, local_path: str) -> None:
        self.calls.append(("pull_file", device_path, local_path))

    def system_info(self) -> dict[str, str | int]:
        return {"os_version": "17", "model": "Fake", "battery_percent": 88}


@pytest.fixture()
def fake_device(monkeypatch: pytest.MonkeyPatch) -> FakeDevice:
    device = FakeDevice()
    monkeypatch.setattr(server.manager, "_devices", {device.id: device})
    monkeypatch.setattr(server.manager, "refresh", lambda: [device])
    return device


@pytest.fixture()
def client(fake_device: FakeDevice) -> TestClient:
    return TestClient(server.app)


def test_get_logs(client: TestClient, fake_device: FakeDevice) -> None:
    response = client.get("/api/v1/devices/fake-1/logs?lines=50&filter=boom")
    assert response.status_code == 200
    assert response.json() == {"logs": "log line 1\nlog line 2"}
    assert ("logs", 50, "boom", None) in fake_device.calls


def test_get_logs_scoped_by_package(client: TestClient, fake_device: FakeDevice) -> None:
    response = client.get("/api/v1/devices/fake-1/logs?package=com.example.app&flutter=true")
    assert response.status_code == 200
    scope = next(call[3] for call in fake_device.calls if call[0] == "logs")
    assert scope is not None
    assert scope.package == "com.example.app"
    assert scope.flutter is True


def test_logs_stream_ws_passes_scope(client: TestClient, fake_device: FakeDevice) -> None:
    url = "/api/v1/devices/fake-1/logs/stream?package=com.example.app&scope=foreground"
    with client.websocket_connect(url):
        pass
    scope = next(call[1] for call in fake_device.calls if call[0] == "stream_logs")
    assert scope is not None
    assert scope.package == "com.example.app"
    assert scope.foreground is True


def test_save_screenshot_writes_png(client: TestClient, tmp_path) -> None:
    target = tmp_path / "shots" / "screen.png"
    response = client.post("/api/v1/devices/fake-1/screenshot/save", json={"path": str(target)})
    assert response.status_code == 200
    assert response.json() == {"ok": True, "path": str(target)}
    assert target.read_bytes() == FAKE_PNG


def test_save_screenshot_rejects_relative_path(client: TestClient) -> None:
    response = client.post("/api/v1/devices/fake-1/screenshot/save", json={"path": "relative.png"})
    assert response.status_code == 502


def test_crashes(client: TestClient) -> None:
    response = client.get("/api/v1/devices/fake-1/crashes?limit=1")
    assert response.status_code == 200
    assert response.json()[0]["process"] == "com.example.app"


def test_open_url(client: TestClient, fake_device: FakeDevice) -> None:
    response = client.post("/api/v1/devices/fake-1/open_url", json={"url": "myapp://profile/42"})
    assert response.status_code == 200
    assert ("open_url", "myapp://profile/42") in fake_device.calls


def test_clear_data_and_force_stop(client: TestClient, fake_device: FakeDevice) -> None:
    assert (
        client.post("/api/v1/devices/fake-1/clear_data", json={"package": "com.x"}).status_code
        == 200
    )
    assert (
        client.post("/api/v1/devices/fake-1/force_stop", json={"package": "com.x"}).status_code
        == 200
    )
    assert ("clear_app_data", "com.x") in fake_device.calls
    assert ("force_stop", "com.x") in fake_device.calls


def test_clear_data_unsupported_maps_to_502(client: TestClient) -> None:
    response = client.post(
        "/api/v1/devices/fake-1/clear_data", json={"package": "com.ios.unsupported"}
    )
    assert response.status_code == 502
    assert "not supported" in response.json()["detail"]


def test_push_and_pull(client: TestClient, fake_device: FakeDevice) -> None:
    response = client.post(
        "/api/v1/devices/fake-1/push",
        json={"local_path": "/tmp/a.txt", "device_path": "/sdcard/a.txt"},
    )
    assert response.status_code == 200
    response = client.post(
        "/api/v1/devices/fake-1/pull",
        json={"device_path": "/sdcard/a.txt", "local_path": "/tmp/b.txt"},
    )
    assert response.status_code == 200
    assert ("push_file", "/tmp/a.txt", "/sdcard/a.txt") in fake_device.calls
    assert ("pull_file", "/sdcard/a.txt", "/tmp/b.txt") in fake_device.calls


def test_info(client: TestClient) -> None:
    response = client.get("/api/v1/devices/fake-1/info")
    assert response.status_code == 200
    assert response.json() == {"os_version": "17", "model": "Fake", "battery_percent": 88}


def test_unknown_device_404(client: TestClient) -> None:
    response = client.get("/api/v1/devices/nope/logs")
    assert response.status_code == 404


def test_logs_stream_ws_filters_lines(client: TestClient, fake_device: FakeDevice) -> None:
    with client.websocket_connect("/api/v1/devices/fake-1/logs/stream?filter=boom") as ws:
        assert ws.receive_text() == "boom happened"
    deadline = time.monotonic() + 2  # server closes the stream shortly after disconnect
    while not fake_device.log_stream.closed and time.monotonic() < deadline:
        time.sleep(0.01)
    assert fake_device.log_stream.closed


def test_logs_stream_ws_all_lines(client: TestClient, fake_device: FakeDevice) -> None:
    with client.websocket_connect("/api/v1/devices/fake-1/logs/stream") as ws:
        assert ws.receive_text() == "line one"
        assert ws.receive_text() == "boom happened"
        assert ws.receive_text() == "line three"


def test_create_options_route(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "android": {"available": True, "reason": None, "device_profiles": [], "system_images": []},
        "ios": {"available": True, "reason": None, "device_types": [], "runtimes": []},
    }
    monkeypatch.setattr(server.virtual, "create_options", lambda: payload)
    response = client.get("/api/v1/virtual-devices/create-options")
    assert response.status_code == 200
    assert response.json() == payload


def test_create_route_starts_job(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def fake_create(**kwargs: object) -> dict:
        captured.update(kwargs)
        return {"id": "job-1", "status": "queued", "platform": "ios", "name": "My iPhone"}

    monkeypatch.setattr(server.virtual, "create_virtual_device", fake_create)
    response = client.post(
        "/api/v1/virtual-devices/create",
        json={"platform": "ios", "name": "My iPhone", "device_type": "dt", "runtime": "rt"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == "job-1"
    assert captured["platform"] == "ios" and captured["name"] == "My iPhone"


def test_create_job_route_404(client: TestClient) -> None:
    response = client.get("/api/v1/virtual-devices/create/jobs/nope")
    assert response.status_code == 404


def test_create_validation_error_maps_to_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = client.post(
        "/api/v1/virtual-devices/create", json={"platform": "symbian", "name": "x"}
    )
    assert response.status_code == 502  # DeviceError handler
    assert "unknown platform" in response.json()["detail"]
