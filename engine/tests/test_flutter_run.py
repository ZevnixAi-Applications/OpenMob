"""Unit tests for the OpenMob-managed `flutter run --machine` session layer."""

import io
import threading
import time

import pytest
from fastapi.testclient import TestClient

from openmob import server
from openmob.device import DeviceError
from openmob.flutter_run import (
    FlutterRunSession,
    build_command_line,
    build_run_command,
    parse_daemon_messages,
    restart_outcome,
    validate_project,
)


# --- daemon JSON-event parser -------------------------------------------------


def test_parse_event_message() -> None:
    line = '[{"event":"app.started","params":{"appId":"a1"}}]'
    assert parse_daemon_messages(line) == [{"event": "app.started", "params": {"appId": "a1"}}]


def test_parse_debug_port_message() -> None:
    line = '[{"event":"app.debugPort","params":{"appId":"a1","wsUri":"ws://127.0.0.1:5/ws"}}]'
    assert parse_daemon_messages(line)[0]["params"]["wsUri"] == "ws://127.0.0.1:5/ws"


def test_parse_command_response() -> None:
    assert parse_daemon_messages('[{"id":3,"result":{"code":0}}]') == [
        {"id": 3, "result": {"code": 0}}
    ]


def test_parse_progress_and_stop() -> None:
    progress = '[{"event":"app.progress","params":{"message":"Building","finished":false}}]'
    assert parse_daemon_messages(progress)[0]["event"] == "app.progress"
    assert parse_daemon_messages('[{"event":"app.stop","params":{"appId":"a1"}}]')[0][
        "event"
    ] == "app.stop"


def test_parse_plain_lines_are_not_protocol() -> None:
    assert parse_daemon_messages("Launching lib/main.dart on emulator...") == []
    assert parse_daemon_messages("") == []


def test_parse_ignores_malformed_or_non_array() -> None:
    assert parse_daemon_messages("[not json]") == []
    assert parse_daemon_messages('{"event":"x"}') == []  # object, not the array wrapper


def test_parse_filters_non_dict_array_items() -> None:
    assert parse_daemon_messages('[1, {"event":"app.stop"}, "x"]') == [{"event": "app.stop"}]


# --- command construction -----------------------------------------------------


def test_build_run_command_debug() -> None:
    assert build_run_command("flutter", "emulator-5554", "debug") == [
        "flutter", "run", "--machine", "-d", "emulator-5554", "--debug",
    ]


def test_build_run_command_profile_and_default() -> None:
    assert build_run_command("flutter", "dev", "profile")[-1] == "--profile"
    assert build_run_command("flutter", "dev", "")[-1] == "--debug"


def test_build_run_command_rejects_bad_mode() -> None:
    with pytest.raises(DeviceError, match="unsupported run mode"):
        build_run_command("flutter", "dev", "release")


def test_build_command_line_shape() -> None:
    line = build_command_line(7, "app.restart", {"appId": "a1", "fullRestart": False})
    assert line == '[{"id": 7, "method": "app.restart", "params": {"appId": "a1", ' \
                   '"fullRestart": false}}]'


def test_restart_outcome_success_and_failure() -> None:
    assert restart_outcome({"code": 0}) == {"success": True, "code": 0}
    assert restart_outcome({"code": 1, "message": "boom"}) == {
        "success": False, "code": 1, "message": "boom",
    }


# --- project validation -------------------------------------------------------


def test_validate_project_missing_dir(tmp_path) -> None:
    with pytest.raises(DeviceError, match="not found"):
        validate_project(str(tmp_path / "nope"))


def test_validate_project_not_flutter(tmp_path) -> None:
    with pytest.raises(DeviceError, match="not a Flutter project"):
        validate_project(str(tmp_path))


def test_validate_project_ok(tmp_path) -> None:
    (tmp_path / "pubspec.yaml").write_text("name: demo\n")
    assert validate_project(str(tmp_path)) == tmp_path


# --- session state machine (no real subprocess) -------------------------------


def test_daemon_events_drive_session_state() -> None:
    session = FlutterRunSession("dev", "/proj")
    session._handle_message({"event": "app.start", "params": {"appId": "a1", "supportsRestart": True}})
    assert session.app_id == "a1"
    session._handle_message(
        {"event": "app.debugPort", "params": {"appId": "a1", "wsUri": "ws://127.0.0.1:5/ws"}}
    )
    assert session.vm_service_uri == "ws://127.0.0.1:5/ws"
    assert not session.started and not session._started_event.is_set()
    session._handle_message({"event": "app.started", "params": {"appId": "a1"}})
    assert session.started and session._started_event.is_set()


def test_app_log_events_are_captured() -> None:
    session = FlutterRunSession("dev", "/proj")
    session._handle_message({"event": "app.log", "params": {"log": "hello from app\n"}})
    assert session.recent_logs() == ["hello from app"]


class FakeProc:
    """Minimal Popen stand-in: an in-memory stdin and an 'alive' poll()."""

    def __init__(self) -> None:
        self.stdin = io.StringIO()
        self._alive = True

    def poll(self) -> int | None:
        return None if self._alive else 0


def test_reload_sends_daemon_command_and_returns_outcome() -> None:
    session = FlutterRunSession("dev", "/proj")
    session._proc = FakeProc()  # type: ignore[assignment]
    session.app_id = "a1"
    result: dict = {}

    worker = threading.Thread(target=lambda: result.update(session.reload(full_restart=False)))
    worker.start()
    deadline = time.monotonic() + 5
    while session._next_id == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    session._resolve({"id": session._next_id, "result": {"code": 0}})
    worker.join(timeout=5)

    assert result == {"success": True, "code": 0, "kind": "hot-reload"}
    assert session.last_reload == result
    payload = session._proc.stdin.getvalue()  # type: ignore[attr-defined]
    assert '"app.restart"' in payload and '"fullRestart": false' in payload


def test_hot_restart_sets_full_restart_flag() -> None:
    session = FlutterRunSession("dev", "/proj")
    session._proc = FakeProc()  # type: ignore[assignment]
    session.app_id = "a1"
    result: dict = {}

    worker = threading.Thread(target=lambda: result.update(session.reload(full_restart=True)))
    worker.start()
    deadline = time.monotonic() + 5
    while session._next_id == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    session._resolve({"id": session._next_id, "result": {"code": 0}})
    worker.join(timeout=5)

    assert result["kind"] == "hot-restart"
    assert '"fullRestart": true' in session._proc.stdin.getvalue()  # type: ignore[attr-defined]


def test_reload_surfaces_daemon_error() -> None:
    session = FlutterRunSession("dev", "/proj")
    session._proc = FakeProc()  # type: ignore[assignment]
    session.app_id = "a1"
    error: dict = {}

    def run() -> None:
        try:
            session.reload()
        except DeviceError as exc:
            error["message"] = str(exc)

    worker = threading.Thread(target=run)
    worker.start()
    deadline = time.monotonic() + 5
    while session._next_id == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    session._resolve({"id": session._next_id, "error": "compile failed"})
    worker.join(timeout=5)
    assert "compile failed" in error["message"]


def test_process_exit_before_start_records_error() -> None:
    session = FlutterRunSession("dev", "/proj")
    session._proc = FakeProc()  # type: ignore[assignment]
    session._proc._alive = False  # type: ignore[attr-defined]
    session._emit_log("Error: something broke")
    session._on_exit()
    assert session.stopped
    assert session._start_error is not None and "before the app started" in session._start_error
    assert session._started_event.is_set()


def test_log_subscriber_receives_history_and_live_lines() -> None:
    session = FlutterRunSession("dev", "/proj")
    session._emit_log("earlier line")
    sub = session.stream()
    assert sub.readline() == "earlier line"  # primed from history
    session._emit_log("live line")
    assert sub.readline() == "live line"
    sub.close()
    assert sub.readline() is None


# --- fallback vs. managed selection (route level) -----------------------------


def test_hot_reload_prefers_managed_session(monkeypatch) -> None:
    class FakeSession:
        running = True

        def reload(self, full_restart: bool = False) -> dict:
            return {"success": True, "code": 0, "kind": "hot-reload"}

    monkeypatch.setattr(server.flutter_manager, "get", lambda device_id: FakeSession())
    client = TestClient(server.app)
    body = client.post("/api/v1/devices/dev/flutter/hot-reload").json()
    assert body["managed"] is True and body["success"] is True


def test_hot_reload_falls_back_without_session(monkeypatch) -> None:
    monkeypatch.setattr(server.flutter_manager, "get", lambda device_id: None)
    monkeypatch.setattr(server.manager, "get", lambda device_id: object())
    monkeypatch.setattr(
        server.flutter, "hot_reload", lambda device: {"success": True, "isolates": []}
    )
    client = TestClient(server.app)
    body = client.post("/api/v1/devices/dev/flutter/hot-reload").json()
    assert body["managed"] is False and body["success"] is True


def test_hot_restart_requires_managed_session(monkeypatch) -> None:
    monkeypatch.setattr(server.flutter_manager, "get", lambda device_id: None)
    client = TestClient(server.app)
    res = client.post("/api/v1/devices/dev/flutter/hot-restart")
    assert res.status_code == 502
    assert "managed" in res.json()["detail"]
