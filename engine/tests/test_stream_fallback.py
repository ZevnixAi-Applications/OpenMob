"""WebSocket stream route: video pipeline, poll fallback, and mode override."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from openmob import server
from openmob.device import DeviceError

JPEG_A = b"\xff\xd8frame-a\xff\xd9"
JPEG_B = b"\xff\xd8frame-b\xff\xd9"


def png_bytes() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, format="PNG")
    return buffer.getvalue()


class FakeAndroidDevice:
    """Minimal stand-in for AndroidDevice as used by the stream route."""

    id = "fake-android"
    name = "Fake"
    platform = "android"
    status = "online"

    def __init__(
        self,
        stream_error: Exception | None = None,
        frames: tuple[bytes, ...] = (JPEG_A, JPEG_B),
    ) -> None:
        self.stream_error = stream_error
        self.frames = frames
        self.stream_calls = 0
        self._png = png_bytes()

    def screenshot(self) -> bytes:
        return self._png

    def stream_frames(self):
        self.stream_calls += 1
        if self.stream_error is not None:
            raise self.stream_error
        return self._frames()

    def _frames(self):
        yield from self.frames


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("OPENMOB_ANDROID_STREAM", raising=False)
    return TestClient(server.app)


def install(monkeypatch, device) -> None:
    monkeypatch.setattr(server.manager, "_devices", {device.id: device})
    monkeypatch.setattr(server.manager, "refresh", lambda: list({device.id: device}.values()))


def test_video_frames_are_relayed(client, monkeypatch) -> None:
    device = FakeAndroidDevice()
    install(monkeypatch, device)
    with client.websocket_connect(f"/api/v1/devices/{device.id}/stream") as ws:
        primer = ws.receive_bytes()  # screencap-primed first frame
        assert primer.startswith(b"\xff\xd8")
        assert ws.receive_bytes() == JPEG_A
        assert ws.receive_bytes() == JPEG_B
    assert device.stream_calls == 1


def test_falls_back_to_poll_when_video_fails(client, monkeypatch) -> None:
    device = FakeAndroidDevice(stream_error=DeviceError("screenrecord not permitted"))
    install(monkeypatch, device)
    with client.websocket_connect(f"/api/v1/devices/{device.id}/stream") as ws:
        frame = ws.receive_bytes()
        assert frame.startswith(b"\xff\xd8") and frame.endswith(b"\xff\xd9")
    assert device.stream_calls == 1


def test_poll_mode_skips_video(client, monkeypatch) -> None:
    device = FakeAndroidDevice(stream_error=AssertionError("must not be called"))
    install(monkeypatch, device)
    monkeypatch.setenv("OPENMOB_ANDROID_STREAM", "poll")
    with client.websocket_connect(f"/api/v1/devices/{device.id}/stream") as ws:
        assert ws.receive_bytes().startswith(b"\xff\xd8")
    assert device.stream_calls == 0


def test_stale_tick_sends_screencap_refresh(client, monkeypatch) -> None:
    device = FakeAndroidDevice(frames=(b"", JPEG_A))  # b"" == videostream.STALE
    install(monkeypatch, device)
    with client.websocket_connect(f"/api/v1/devices/{device.id}/stream") as ws:
        assert ws.receive_bytes().startswith(b"\xff\xd8")  # primer
        refresh = ws.receive_bytes()  # stale tick -> fresh screencap JPEG
        assert refresh.startswith(b"\xff\xd8") and refresh != JPEG_A
        assert ws.receive_bytes() == JPEG_A
