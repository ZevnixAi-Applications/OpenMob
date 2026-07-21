"""REST /api/v1/debug tests with the worker layer mocked (no lldb, no simulator)."""

import pytest
from fastapi.testclient import TestClient

from openmob import server
from openmob.debugger import DebugSessionManager

from .test_debugger import SIM_UDID, FakeWorker


@pytest.fixture
def client(monkeypatch):
    workers: list[FakeWorker] = []

    def worker_factory():
        worker = FakeWorker()
        workers.append(worker)
        return worker

    manager = DebugSessionManager(
        worker_factory=worker_factory,
        pid_resolver=lambda udid, bundle_id: 4711,
        simulator_probe=lambda udid: "Booted" if udid == SIM_UDID else None,
    )
    monkeypatch.setattr(server, "debug_manager", manager)
    test_client = TestClient(server.create_app())
    test_client.workers = workers
    return test_client


def create_session(client, **overrides) -> str:
    body = {"device_id": SIM_UDID, "bundle_id": "com.example.tb", **overrides}
    response = client.post("/api/v1/debug/sessions", json=body)
    assert response.status_code == 200, response.text
    return response.json()["session_id"]


def test_create_session_by_bundle_id(client):
    response = client.post(
        "/api/v1/debug/sessions",
        json={"device_id": SIM_UDID, "bundle_id": "com.example.tb", "breakpoints": ["main.m:5"]},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["pid"] == 4711
    assert payload["attach"]["state"] == "running"
    assert payload["attach"]["breakpoints"][0]["spec"] == "main.m:5"
    listed = client.get("/api/v1/debug/sessions").json()
    assert [s["session_id"] for s in listed] == [payload["session_id"]]


def test_create_session_requires_target(client):
    response = client.post("/api/v1/debug/sessions", json={"device_id": SIM_UDID})
    assert response.status_code == 400
    assert "pid or bundle_id" in response.json()["detail"]


def test_real_device_returns_409_with_commands(client, monkeypatch):
    monkeypatch.setattr("openmob.debugger.tunneld_devices", lambda url=None: None)
    response = client.post("/api/v1/debug/sessions", json={"device_id": "00008101-REAL", "pid": 1})
    assert response.status_code == 409
    payload = response.json()
    assert payload["error"] == "capability_missing"
    assert "sudo pymobiledevice3 remote tunneld" in payload["commands"][0]


def test_breakpoint_endpoints(client):
    session_id = create_session(client)
    added = client.post(
        f"/api/v1/debug/sessions/{session_id}/breakpoints",
        json={"spec": "-[ViewController viewDidAppear:]"},
    )
    assert added.status_code == 200
    bp_id = added.json()["id"]
    listed = client.get(f"/api/v1/debug/sessions/{session_id}/breakpoints").json()
    assert [bp["id"] for bp in listed] == [bp_id]
    deleted = client.delete(f"/api/v1/debug/sessions/{session_id}/breakpoints/{bp_id}")
    assert deleted.status_code == 200
    missing = client.delete(f"/api/v1/debug/sessions/{session_id}/breakpoints/999")
    assert missing.status_code == 400


def test_flow_endpoints(client):
    session_id = create_session(client)
    assert client.post(f"/api/v1/debug/sessions/{session_id}/pause").json()["state"] == "stopped"
    step = client.post(f"/api/v1/debug/sessions/{session_id}/step", json={"kind": "over"})
    assert step.json()["state"] == "stopped"
    bad = client.post(f"/api/v1/debug/sessions/{session_id}/step", json={"kind": "warp"})
    assert bad.status_code == 400
    resumed = client.post(f"/api/v1/debug/sessions/{session_id}/continue")
    assert resumed.json()["state"] == "running"


def test_eval_state_output(client):
    session_id = create_session(client)
    evaluated = client.post(f"/api/v1/debug/sessions/{session_id}/eval", json={"expr": "(int)1+2"})
    assert evaluated.json()["value"] == "3"
    state = client.get(f"/api/v1/debug/sessions/{session_id}/state")
    assert state.json()["state"] == "running"
    output = client.get(f"/api/v1/debug/sessions/{session_id}/output")
    assert output.json() == []


def test_detach_session(client):
    session_id = create_session(client)
    response = client.delete(f"/api/v1/debug/sessions/{session_id}")
    assert response.json()["detached"] is True
    assert client.workers[0].closed
    assert client.get(f"/api/v1/debug/sessions/{session_id}/state").status_code == 404


def test_unknown_session_is_404(client):
    assert client.get("/api/v1/debug/sessions/nope/state").status_code == 404
    assert client.delete("/api/v1/debug/sessions/nope").status_code == 404
