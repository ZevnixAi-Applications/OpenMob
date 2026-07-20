"""Unit tests for the iOS backend against a mocked WDA (no device required)."""

import base64
import json

import httpx
import pytest

from openmob.device import DeviceError
from openmob.ios import IosDevice, WdaClient, parse_png_size, pixels_to_points

# iPhone 12: 390x844 points, scale 3 -> 1170x2532 pixels.
POINT_WIDTH, POINT_HEIGHT, SCALE = 390, 844, 3
PIXEL_WIDTH, PIXEL_HEIGHT = 1170, 2532

# Minimal PNG header: magic + IHDR chunk length/type + width + height.
FAKE_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + b"\x00\x00\x00\x0dIHDR"
    + PIXEL_WIDTH.to_bytes(4, "big")
    + PIXEL_HEIGHT.to_bytes(4, "big")
)


class FakeWda:
    """Handler for httpx.MockTransport emulating the WDA endpoints we use."""

    def __init__(self, screen_endpoint: bool = True) -> None:
        self.requests: list[tuple[str, str, dict | None]] = []
        self.sessions_created = 0
        self.invalid_session_ids: set[str] = set()
        self.screen_endpoint = screen_endpoint

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, path, body))
        if path == "/session" and request.method == "POST":
            self.sessions_created += 1
            session_id = f"SESSION-{self.sessions_created}"
            return self._value({"sessionId": session_id, "capabilities": {}})
        if path == "/screenshot":
            return self._value(base64.b64encode(FAKE_PNG).decode())
        if path == "/wda/homescreen":
            return self._value(None)
        if path.startswith("/session/"):
            session_id = path.split("/")[2]
            if session_id in self.invalid_session_ids:
                return httpx.Response(
                    404,
                    json={"value": {"error": "invalid session id", "message": "stale"}},
                )
            suffix = path.removeprefix(f"/session/{session_id}")
            if suffix == "/window/size":
                return self._value({"width": POINT_WIDTH, "height": POINT_HEIGHT})
            if suffix == "/wda/screen":
                if not self.screen_endpoint:
                    return httpx.Response(
                        404, json={"value": {"error": "unknown command", "message": "no"}}
                    )
                return self._value({"scale": SCALE, "statusBarSize": {}})
            return self._value(None)
        return httpx.Response(404, json={"value": {"error": "unknown command", "message": path}})

    @staticmethod
    def _value(value: object) -> httpx.Response:
        return httpx.Response(200, json={"value": value})

    def sent(self, method: str, suffix: str) -> list[dict | None]:
        """Bodies of recorded requests whose path ends with the given suffix."""
        return [body for m, path, body in self.requests if m == method and path.endswith(suffix)]


def make_device(wda: FakeWda) -> IosDevice:
    client = httpx.Client(base_url="http://wda.test", transport=httpx.MockTransport(wda))
    return IosDevice("FAKE-UDID", "Fake iPhone", wda=WdaClient(client=client))


def test_pixels_to_points() -> None:
    assert pixels_to_points(585, 3) == 195
    assert pixels_to_points(1170, 3) == 390
    assert pixels_to_points(100, 3) == 33.33
    assert pixels_to_points(400, 2) == 200


def test_parse_png_size() -> None:
    assert parse_png_size(FAKE_PNG) == (PIXEL_WIDTH, PIXEL_HEIGHT)


def test_parse_png_size_rejects_garbage() -> None:
    with pytest.raises(DeviceError):
        parse_png_size(b"JFIF not a png")


def test_reports_pixel_size() -> None:
    device = make_device(FakeWda())
    assert (device.width, device.height) == (PIXEL_WIDTH, PIXEL_HEIGHT)


def test_pixel_size_fallback_via_screenshot() -> None:
    wda = FakeWda(screen_endpoint=False)
    device = make_device(wda)
    assert (device.width, device.height) == (PIXEL_WIDTH, PIXEL_HEIGHT)
    assert wda.sent("GET", "/screenshot")  # scale derived from screenshot pixels


def test_screenshot_decodes_base64_png() -> None:
    device = make_device(FakeWda())
    assert device.screenshot() == FAKE_PNG


def test_tap_converts_pixels_to_points() -> None:
    wda = FakeWda()
    device = make_device(wda)
    device.tap(585, 780)
    assert wda.sent("POST", "/wda/tap") == [{"x": 195, "y": 260}]


def test_swipe_converts_coords_and_duration() -> None:
    wda = FakeWda()
    device = make_device(wda)
    device.swipe(585, 2100, 585, 300, duration_ms=500)
    assert wda.sent("POST", "/wda/dragfromtoforduration") == [
        {"fromX": 195, "fromY": 700, "toX": 195, "toY": 100, "duration": 0.5}
    ]


def test_session_created_lazily_and_cached() -> None:
    wda = FakeWda()
    device = make_device(wda)
    device.tap(10, 10)
    device.tap(20, 20)
    assert wda.sessions_created == 1


def test_session_recreated_on_invalid_session() -> None:
    wda = FakeWda()
    device = make_device(wda)
    device.tap(10, 10)
    wda.invalid_session_ids.add("SESSION-1")  # emulate a WDA restart
    device.tap(585, 780)
    assert wda.sessions_created == 2
    assert wda.sent("POST", "/wda/tap")[-1] == {"x": 195, "y": 260}


def test_input_text_sends_chars() -> None:
    wda = FakeWda()
    device = make_device(wda)
    device.input_text("hi!")
    assert wda.sent("POST", "/wda/keys") == [{"value": ["h", "i", "!"]}]


def test_press_key_mappings() -> None:
    wda = FakeWda()
    device = make_device(wda)
    device.press_key("home")
    device.press_key("power")
    device.press_key("volume_up")
    device.press_key("volume_down")
    device.press_key("enter")
    assert wda.sent("POST", "/wda/homescreen") == [None]
    assert wda.sent("POST", "/wda/lock") == [None]
    assert wda.sent("POST", "/wda/pressButton") == [{"name": "volumeUp"}, {"name": "volumeDown"}]
    assert wda.sent("POST", "/wda/keys") == [{"value": ["\n"]}]


def test_press_key_unknown() -> None:
    device = make_device(FakeWda())
    with pytest.raises(DeviceError, match="unknown key"):
        device.press_key("back")


def test_launch_app_posts_bundle_id() -> None:
    wda = FakeWda()
    device = make_device(wda)
    device.launch_app("com.apple.Preferences")
    assert wda.sent("POST", "/wda/apps/launch") == [{"bundleId": "com.apple.Preferences"}]


def test_wda_unreachable_raises_device_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = httpx.Client(base_url="http://wda.test", transport=httpx.MockTransport(refuse))
    device = IosDevice("FAKE-UDID", "Fake iPhone", wda=WdaClient(client=client))
    with pytest.raises(DeviceError, match="WDA not running"):
        device.screenshot()
    with pytest.raises(DeviceError, match="WDA not running"):
        device.tap(10, 10)


def test_install_and_uninstall_use_devicectl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stderr = b""

    def fake_run(cmd: list[str], **kwargs: object) -> Result:
        calls.append(cmd)
        return Result()

    monkeypatch.setattr("openmob.ios.subprocess.run", fake_run)
    device = IosDevice("FAKE-UDID", "Fake iPhone")
    device.install_app("/tmp/app.ipa")
    device.uninstall_app("com.example.app")
    assert calls == [
        ["xcrun", "devicectl", "device", "install", "app", "--device", "FAKE-UDID", "/tmp/app.ipa"],
        [
            "xcrun",
            "devicectl",
            "device",
            "uninstall",
            "app",
            "--device",
            "FAKE-UDID",
            "com.example.app",
        ],
    ]


def test_devicectl_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    class Result:
        returncode = 1
        stderr = b"no such device"

    monkeypatch.setattr("openmob.ios.subprocess.run", lambda cmd, **kwargs: Result())
    device = IosDevice("FAKE-UDID", "Fake iPhone")
    with pytest.raises(DeviceError, match="no such device"):
        device.uninstall_app("com.example.app")


def test_info_serializes_pixel_geometry() -> None:
    device = make_device(FakeWda())
    assert device.info() == {
        "id": "FAKE-UDID",
        "name": "Fake iPhone",
        "platform": "ios",
        "status": "online",
        "width": PIXEL_WIDTH,
        "height": PIXEL_HEIGHT,
    }
