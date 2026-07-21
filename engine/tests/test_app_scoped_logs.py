"""App-scoped log tests: pid resolution, logcat/syslog/simctl command construction,
and the re-resolve-on-restart logic of ScopedLogStream (no device required)."""

import queue
import threading
import time

from openmob import sim
from openmob.android import (
    build_logcat_args,
    filter_lines_by_pids,
    parse_foreground_package,
    parse_logcat_pid,
    parse_pidof,
)
from openmob.ios import IosDevice, ios_process_name
from openmob.logstream import LogScope, ScopedLogStream

# --- Android: pidof parsing ------------------------------------------------


def test_parse_pidof_running_single() -> None:
    assert parse_pidof("10489\n") == [10489]


def test_parse_pidof_not_running_is_empty() -> None:
    assert parse_pidof("") == []
    assert parse_pidof("  \n") == []


def test_parse_pidof_multiple_pids() -> None:
    assert parse_pidof("100 200 300\n") == [100, 200, 300]


def test_parse_pidof_ignores_non_numeric() -> None:
    assert parse_pidof("no process found") == []


# --- Android: foreground package parsing -----------------------------------


def test_parse_foreground_top_resumed() -> None:
    line = "  topResumedActivity=ActivityRecord{135057427 u0 ai.zevnix.openmob_testbed/.MainActivity t15}"
    assert parse_foreground_package(line) == "ai.zevnix.openmob_testbed"


def test_parse_foreground_m_resumed_legacy() -> None:
    line = "    mResumedActivity: ActivityRecord{abc u0 com.example.app/.Main t42}"
    assert parse_foreground_package(line) == "com.example.app"


def test_parse_foreground_none_when_absent() -> None:
    assert parse_foreground_package("no activity here") is None


# --- Android: logcat command construction ----------------------------------


def test_build_logcat_snapshot_modern_multi_pid() -> None:
    assert build_logcat_args([100, 200], tail=50) == [
        "logcat", "-d", "-t", "50", "--pid=100", "--pid=200",
    ]


def test_build_logcat_stream_modern_flutter() -> None:
    assert build_logcat_args([100], flutter=True) == [
        "logcat", "-T", "1", "--pid=100", "flutter:V", "*:S",
    ]


def test_build_logcat_fallback_omits_pid_flag() -> None:
    # Old devices: no --pid; caller greps the pid column instead.
    assert build_logcat_args([100], tail=50, modern=False) == ["logcat", "-d", "-t", "50"]


def test_build_logcat_whole_device_unscoped() -> None:
    assert build_logcat_args([], tail=50) == ["logcat", "-d", "-t", "50"]


# --- Android: pid-column fallback filtering --------------------------------


def test_parse_logcat_pid_threadtime() -> None:
    line = "07-21 10:57:41.225  5776  5788 I flutter : counter=3"
    assert parse_logcat_pid(line) == 5776


def test_parse_logcat_pid_non_matching() -> None:
    assert parse_logcat_pid("--------- beginning of main") is None


def test_filter_lines_by_pids_keeps_only_matching() -> None:
    text = "\n".join(
        [
            "07-21 10:57:41.225  5776  5788 I flutter : mine",
            "07-21 10:57:41.226  1234  1234 I System  : not mine",
            "07-21 10:57:41.227  5776  5788 I flutter : mine too",
        ]
    )
    assert filter_lines_by_pids(text, [5776]) == (
        "07-21 10:57:41.225  5776  5788 I flutter : mine\n"
        "07-21 10:57:41.227  5776  5788 I flutter : mine too"
    )


# --- LogScope ---------------------------------------------------------------


def test_log_scope_is_app_scoped() -> None:
    assert LogScope(package="com.x").is_app_scoped
    assert LogScope(pid=7).is_app_scoped
    assert LogScope(foreground=True).is_app_scoped
    assert not LogScope().is_app_scoped
    assert not LogScope(flutter=True).is_app_scoped  # flutter alone is not app-scoped


# --- ScopedLogStream: re-resolve on restart --------------------------------


class _FakeSource:
    """A spawnable line source backed by a queue (stands in for a logcat subprocess)."""

    def __init__(self, pids: list[int]) -> None:
        self.pids = pids
        self.closed = False
        self._q: queue.Queue[str | None] = queue.Queue()

    def emit(self, line: str) -> None:
        self._q.put(line)

    def readline(self) -> str | None:
        return self._q.get()

    def close(self) -> None:
        self.closed = True
        self._q.put(None)


def _wait_until(predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met within timeout")


def test_scoped_stream_restarts_tail_when_pid_changes() -> None:
    # App runs as pid 100, then restarts as pid 200.
    states = [[100], [100], [200]]
    idx = {"i": 0}
    lock = threading.Lock()

    def resolve() -> list[int]:
        with lock:
            i = min(idx["i"], len(states) - 1)
            idx["i"] += 1
            return states[i]

    spawned: list[_FakeSource] = []

    def spawn(pids: list[int]) -> _FakeSource:
        source = _FakeSource(list(pids))
        spawned.append(source)
        return source

    stream = ScopedLogStream(resolve, spawn, poll_interval=0.02)
    try:
        _wait_until(lambda: len(spawned) >= 1)
        assert spawned[0].pids == [100]
        spawned[0].emit("line from pid 100")
        assert stream.readline() == "line from pid 100"

        # After the app restarts, a fresh tail is spawned for the new pid and the
        # old one is torn down.
        _wait_until(lambda: len(spawned) >= 2)
        assert spawned[1].pids == [200]
        _wait_until(lambda: spawned[0].closed)
        spawned[1].emit("line from pid 200")
        assert stream.readline() == "line from pid 200"
    finally:
        stream.close()
    assert stream.readline() is None


def test_scoped_stream_spawns_nothing_while_app_not_running() -> None:
    spawned: list[_FakeSource] = []

    def spawn(pids: list[int]) -> _FakeSource:
        source = _FakeSource(list(pids))
        spawned.append(source)
        return source

    stream = ScopedLogStream(lambda: [], spawn, poll_interval=0.02)
    time.sleep(0.1)
    assert spawned == []  # nothing to tail until the app comes up
    stream.close()
    assert stream.readline() is None


# --- iOS: syslog process scoping -------------------------------------------


def test_ios_process_name_from_bundle() -> None:
    assert ios_process_name("ai.zevnix.openmob_testbed") == "openmob_testbed"
    assert ios_process_name("Runner") == "Runner"


def test_ios_syslog_args_unscoped() -> None:
    device = IosDevice("UDID", "iPhone")
    assert device._syslog_args(None) == ["syslog", "live"]


def test_ios_syslog_args_by_package() -> None:
    device = IosDevice("UDID", "iPhone")
    assert device._syslog_args(LogScope(package="com.acme.MyApp")) == [
        "syslog", "live", "--process-name", "MyApp",
    ]


def test_ios_syslog_args_by_pid() -> None:
    device = IosDevice("UDID", "iPhone")
    assert device._syslog_args(LogScope(pid=42)) == ["syslog", "live", "--pid", "42"]


# --- iOS Simulator: simctl log scoping -------------------------------------


def test_sim_predicate_none_when_unscoped() -> None:
    assert sim.sim_log_predicate(None) is None
    assert sim.sim_log_predicate(LogScope(foreground=True)) is None  # unsupported on sim


def test_sim_predicate_by_pid() -> None:
    assert sim.sim_log_predicate(LogScope(pid=42)) == "processID == 42"


def test_sim_predicate_by_package_uses_process_name() -> None:
    assert sim.sim_log_predicate(LogScope(package="com.acme.Runner")) == 'process == "Runner"'


def test_build_sim_log_show_args_with_predicate() -> None:
    assert sim.build_sim_log_show_args("UDID", "30s", 'process == "Runner"') == [
        "spawn", "UDID", "log", "show", "--last", "30s", "--style", "compact",
        "--predicate", 'process == "Runner"',
    ]


def test_build_sim_log_stream_args_unscoped() -> None:
    assert sim.build_sim_log_stream_args("UDID", None) == [
        "spawn", "UDID", "log", "stream", "--level", "debug", "--style", "compact",
    ]


def test_parse_sim_log_strips_preamble() -> None:
    raw = "\n".join(
        [
            'Filtering the log data using "process == \\"Runner\\""',
            "Timestamp                       Thread     Type        Activity  PID    TTL",
            "2026-07-21 12:00:00.123 Df Runner[1234:5678] flutter: counter=1",
            "",
            "2026-07-21 12:00:01.124 Df Runner[1234:5678] flutter: counter=2",
        ]
    )
    assert sim.parse_sim_log(raw) == (
        "2026-07-21 12:00:00.123 Df Runner[1234:5678] flutter: counter=1\n"
        "2026-07-21 12:00:01.124 Df Runner[1234:5678] flutter: counter=2"
    )
