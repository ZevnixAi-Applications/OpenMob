"""Unit tests for the debug session layer against a mocked lldb worker."""

import pytest

from openmob.debugger import (
    CapabilityError,
    DebugError,
    DebugSessionManager,
    SessionNotFound,
    check_real_device_support,
    parse_launchctl_pid,
)
from openmob.lldb_worker import classify_spec

# --- pure helpers -----------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("Main.swift:42", ("file", "Main.swift", 42)),
        ("Sources/App/View.swift:7", ("file", "Sources/App/View.swift", 7)),
        ("main.m:12", ("file", "main.m", 12)),
        ("-[ViewController viewDidAppear:]", ("symbol", "-[ViewController viewDidAppear:]", None)),
        ("MyApp.ContentView.body", ("symbol", "MyApp.ContentView.body", None)),
        ("viewDidAppear", ("symbol", "viewDidAppear", None)),
        # trailing digits but no file extension -> symbol, not file:line
        ("operator:42gibberish", ("symbol", "operator:42gibberish", None)),
    ],
)
def test_classify_spec(spec, expected):
    assert classify_spec(spec) == expected


LAUNCHCTL_OUTPUT = """\
PID\tStatus\tLabel
312\t0\tcom.apple.SpringBoard
-\t0\tcom.apple.somedaemon
4711\t0\tUIKitApplication:com.example.tb[9c1a][rb-legacy]
4922\t0\tUIKitApplication:com.example.tb.extra[1111][rb-legacy]
"""


def test_parse_launchctl_pid_finds_exact_bundle():
    assert parse_launchctl_pid(LAUNCHCTL_OUTPUT, "com.example.tb") == 4711


def test_parse_launchctl_pid_missing():
    assert parse_launchctl_pid(LAUNCHCTL_OUTPUT, "com.example.other") is None


def test_parse_launchctl_pid_does_not_prefix_match():
    assert parse_launchctl_pid(LAUNCHCTL_OUTPUT, "com.example.t") is None


# --- capability check -------------------------------------------------------


def test_capability_no_tunneld(monkeypatch):
    monkeypatch.setattr("openmob.debugger.tunneld_devices", lambda url=None: None)
    with pytest.raises(CapabilityError) as exc_info:
        check_real_device_support("00008101-FAKE")
    assert "sudo pymobiledevice3 remote tunneld" in exc_info.value.commands


def test_capability_tunnel_missing_device(monkeypatch):
    monkeypatch.setattr("openmob.debugger.tunneld_devices", lambda url=None: {"OTHER-UDID": []})
    with pytest.raises(CapabilityError) as exc_info:
        check_real_device_support("00008101-FAKE")
    assert "no tunnel" in str(exc_info.value)


def test_capability_no_debugserver(monkeypatch):
    monkeypatch.setattr(
        "openmob.debugger.tunneld_devices", lambda url=None: {"00008101-FAKE": [{}]}
    )
    with pytest.raises(CapabilityError) as exc_info:
        check_real_device_support("00008101-FAKE")
    assert any("debugserver" in cmd for cmd in exc_info.value.commands)


def test_capability_satisfied(monkeypatch):
    monkeypatch.setattr(
        "openmob.debugger.tunneld_devices", lambda url=None: {"00008101-FAKE": [{}]}
    )
    url = check_real_device_support("00008101-FAKE", "connect://[fd12::1]:1234")
    assert url == "connect://[fd12::1]:1234"


def test_capability_trusts_url_without_tunneld(monkeypatch):
    """A supplied debugserver_url is authoritative even when tunneld is not running.

    This is the no-sudo userspace path: `debugserver start-server --userspace
    --local-port` forwards a debugserver to a local port without ever registering with
    tunneld, so requiring tunneld here would wrongly reject a valid setup.
    """
    called = False

    def _fail(url=None):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr("openmob.debugger.tunneld_devices", _fail)
    url = check_real_device_support("00008101-FAKE", "connect://[127.0.0.1]:10011")
    assert url == "connect://[127.0.0.1]:10011"
    assert not called  # tunneld is never probed when a URL is provided


def test_capability_no_url_offers_no_sudo_command(monkeypatch):
    """Guidance for the no-url case includes the verified no-sudo userspace command."""
    monkeypatch.setattr("openmob.debugger.tunneld_devices", lambda url=None: None)
    with pytest.raises(CapabilityError) as exc_info:
        check_real_device_support("00008101-FAKE")
    assert any("--userspace" in cmd for cmd in exc_info.value.commands)


# --- session manager with a fake worker -------------------------------------

SIM_UDID = "B8354FBC-0000-0000-0000-000000000000"


class FakeWorker:
    """Scripted stand-in for debugger.LldbWorker."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, dict]] = []
        self.closed = False
        self.state = "running"
        self.breakpoints: dict[int, dict] = {}
        self.next_bp = 0
        self.fail_on: set[str] = set()

    def request(self, cmd: str, timeout: float = 20.0, **args) -> dict:
        self.requests.append((cmd, args))
        if cmd in self.fail_on:
            raise DebugError(f"scripted failure for {cmd}")
        if cmd == "attach":
            self.state = "stopped"
            return {"pid": args["pid"], "state": "stopped", "executable": "tb"}
        if cmd == "connect":
            self.state = "stopped"
            return {"pid": 999, "state": "stopped"}
        if cmd == "bp_set":
            self.next_bp += 1
            info = {
                "id": self.next_bp,
                "spec": args["spec"],
                "locations": 1,
                "resolved": True,
                "hit_count": 0,
                "enabled": True,
            }
            self.breakpoints[self.next_bp] = info
            return info
        if cmd == "bp_list":
            return {"breakpoints": list(self.breakpoints.values())}
        if cmd == "bp_delete":
            if args["bp_id"] not in self.breakpoints:
                raise DebugError(f"no breakpoint with id {args['bp_id']}")
            del self.breakpoints[args["bp_id"]]
            return {"deleted": args["bp_id"]}
        if cmd == "continue":
            self.state = "running"
            return {"state": "running"}
        if cmd == "pause":
            self.state = "stopped"
            return {"state": "stopped"}
        if cmd == "step":
            return {"state": "stopped", "frame": {"function": "next()"}}
        if cmd == "eval":
            return {"value": "3", "summary": None, "type": "int", "description": None}
        if cmd == "state":
            return {"state": self.state, "breakpoints": list(self.breakpoints.values())}
        if cmd == "output":
            return {"chunks": []}
        if cmd == "detach":
            self.state = "detached"
            return {"detached": True, "killed": args.get("kill", False)}
        raise DebugError(f"unexpected cmd {cmd}")

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def make_manager():
    workers: list[FakeWorker] = []

    def factory(**kwargs) -> tuple[DebugSessionManager, list[FakeWorker]]:
        def worker_factory():
            worker = FakeWorker()
            workers.append(worker)
            return worker

        manager = DebugSessionManager(
            worker_factory=worker_factory,
            pid_resolver=lambda udid, bundle_id: 4711,
            simulator_probe=lambda udid: "Booted" if udid == SIM_UDID else None,
            **kwargs,
        )
        return manager, workers

    return factory


def test_create_by_bundle_id_resolves_pid_and_resumes(make_manager):
    manager, workers = make_manager()
    session, attach = manager.create(SIM_UDID, bundle_id="com.example.tb")
    assert session.pid == 4711
    assert attach["state"] == "running"  # auto-continued after attach
    assert [cmd for cmd, _ in workers[0].requests] == ["attach", "continue"]


def test_create_arms_initial_breakpoints_before_resume(make_manager):
    manager, workers = make_manager()
    _, attach = manager.create(SIM_UDID, pid=123, breakpoints=["main.m:10", "handleTick:"])
    assert [bp["spec"] for bp in attach["breakpoints"]] == ["main.m:10", "handleTick:"]
    assert [cmd for cmd, _ in workers[0].requests] == ["attach", "bp_set", "bp_set", "continue"]


def test_create_requires_target(make_manager):
    manager, _ = make_manager()
    with pytest.raises(DebugError, match="pid or bundle_id"):
        manager.create(SIM_UDID)


def test_create_rejects_second_session_per_device(make_manager):
    manager, _ = make_manager()
    manager.create(SIM_UDID, pid=1)
    with pytest.raises(DebugError, match="already has debug session"):
        manager.create(SIM_UDID, pid=2)


def test_create_unbooted_simulator(make_manager):
    manager, _ = make_manager()
    manager._simulator_probe = lambda udid: "Shutdown"
    with pytest.raises(DebugError, match="not booted"):
        manager.create(SIM_UDID, pid=1)


def test_attach_failure_closes_worker(make_manager):
    manager, workers = make_manager()

    def bad_factory():
        worker = FakeWorker()
        worker.fail_on.add("attach")
        workers.append(worker)
        return worker

    manager._worker_factory = bad_factory
    with pytest.raises(DebugError, match="scripted failure"):
        manager.create(SIM_UDID, pid=1)
    assert workers[0].closed
    assert manager.list() == []


def test_breakpoint_lifecycle(make_manager):
    manager, _ = make_manager()
    session, _ = manager.create(SIM_UDID, pid=1)
    bp = session.breakpoint_set("-[ViewController viewDidAppear:]")
    assert bp["resolved"] is True
    assert [b["id"] for b in session.breakpoint_list()] == [bp["id"]]
    session.breakpoint_delete(bp["id"])
    assert session.breakpoint_list() == []
    with pytest.raises(DebugError, match="no breakpoint"):
        session.breakpoint_delete(999)


def test_step_kinds(make_manager):
    manager, workers = make_manager()
    session, _ = manager.create(SIM_UDID, pid=1)
    assert session.step("over")["state"] == "stopped"
    assert session.step("continue")["state"] == "running"
    assert session.step("pause")["state"] == "stopped"
    with pytest.raises(DebugError, match="unknown step kind"):
        session.step("sideways")
    kinds = [args for cmd, args in workers[0].requests if cmd == "step"]
    assert kinds == [{"kind": "over"}]


def test_eval_and_state(make_manager):
    manager, _ = make_manager()
    session, _ = manager.create(SIM_UDID, pid=1)
    assert session.eval("(int)1+2")["value"] == "3"
    assert session.state()["state"] == "running"


def test_detach_removes_session_and_closes_worker(make_manager):
    manager, workers = make_manager()
    session, _ = manager.create(SIM_UDID, pid=1)
    result = manager.remove(session.id, kill=False)
    assert result["detached"] is True
    assert workers[0].closed
    with pytest.raises(SessionNotFound):
        manager.get(session.id)


def test_detach_survives_dead_worker(make_manager):
    manager, workers = make_manager()
    session, _ = manager.create(SIM_UDID, pid=1)
    workers[0].fail_on.add("detach")
    result = manager.remove(session.id)
    assert result["detached"] is True
    assert workers[0].closed


def test_get_by_device(make_manager):
    manager, _ = make_manager()
    session, _ = manager.create(SIM_UDID, pid=1)
    assert manager.get_by_device(SIM_UDID).id == session.id
    with pytest.raises(SessionNotFound):
        manager.get_by_device("nope")


def test_idle_timeout_reaps_session(make_manager):
    manager, workers = make_manager(idle_timeout=0.0)
    session, _ = manager.create(SIM_UDID, pid=1)
    session.last_used -= 1.0  # pretend the last request was a second ago
    manager.reap_idle()
    assert workers[0].closed
    with pytest.raises(SessionNotFound):
        manager.get(session.id)


def test_fresh_session_survives_reap(make_manager):
    manager, workers = make_manager()  # default 10 min timeout
    session, _ = manager.create(SIM_UDID, pid=1)
    manager.reap_idle()
    assert not workers[0].closed
    assert manager.get(session.id).id == session.id


def test_real_device_without_tunnel_raises_capability(make_manager, monkeypatch):
    manager, _ = make_manager()
    monkeypatch.setattr("openmob.debugger.tunneld_devices", lambda url=None: None)
    with pytest.raises(CapabilityError) as exc_info:
        manager.create("00008101-REALPHONE", bundle_id="com.example.tb")
    assert exc_info.value.commands


def test_real_device_with_debugserver_url_connects(make_manager, monkeypatch):
    manager, workers = make_manager()
    monkeypatch.setattr(
        "openmob.debugger.tunneld_devices", lambda url=None: {"00008101-REALPHONE": [{}]}
    )
    session, attach = manager.create(
        "00008101-REALPHONE",
        bundle_id="com.example.tb",
        debugserver_url="connect://[fd12::1]:1234",
    )
    assert session.pid == 999
    assert workers[0].requests[0] == ("connect", {"url": "connect://[fd12::1]:1234"})
    assert attach["state"] == "running"
