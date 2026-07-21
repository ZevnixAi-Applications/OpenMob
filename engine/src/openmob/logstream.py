"""Line-oriented log streaming over a tailing subprocess (adb logcat, syslog live).

Logs can be *scoped* to a single app rather than the whole device. A ``LogScope``
describes what to scope to (a package, an explicit pid, or "the foreground app");
backends resolve it to a concrete set of process ids and filter the log tail to them.
Because an app's pid changes every time it restarts, scoped Android streaming uses
``ScopedLogStream``, which periodically re-resolves the pids and transparently
restarts the underlying ``logcat`` when they change.
"""

import os
import queue
import signal
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class LogScope:
    """What to scope a log tail to.

    - ``package``: resolve the app's live pid(s) and filter to them.
    - ``pid``: filter to an explicit pid (takes precedence over ``package``).
    - ``foreground``: resolve whatever app is currently foreground (Android only).
    - ``flutter``: narrow to Flutter framework output (``flutter`` logcat tag).

    An empty scope (all falsy) means "whole device" — the historical behaviour.
    """

    package: str | None = None
    pid: int | None = None
    foreground: bool = False
    flutter: bool = False

    @property
    def is_app_scoped(self) -> bool:
        """True when the scope targets a single app (not the whole device)."""
        return bool(self.package or self.pid is not None or self.foreground)


class LogStream:
    """Wraps a tailing subprocess; readline() blocks, close() kills the process."""

    def __init__(self, cmd: list[str], env: dict[str, str] | None = None) -> None:
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
            env={**os.environ, **(env or {})},
        )

    def readline(self) -> str | None:
        """Return the next log line (without newline), or None when the stream ends."""
        stdout = self._proc.stdout
        if stdout is None:
            return None
        line = stdout.readline()
        if line == "":
            return None
        return line.rstrip("\n")

    def close(self) -> None:
        """Terminate the subprocess; pending readline() calls return None."""
        if self._proc.poll() is None:
            try:
                self._proc.send_signal(signal.SIGTERM)
                self._proc.wait(timeout=2)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                self._proc.kill()
        if self._proc.stdout is not None:
            self._proc.stdout.close()


class ScopedLogStream:
    """A log tail scoped to a set of pids that re-resolves as the app restarts.

    A supervisor thread polls ``resolve_pids()`` every ``poll_interval`` seconds. When
    the pid set changes — the app started, stopped, or restarted with a fresh pid — the
    underlying tail subprocess is torn down and (if any pids resolved) a new one is
    spawned via ``spawn(pids)``. While no pids resolve (app not running) the stream
    simply produces nothing; ``readline()`` keeps blocking so the client stays connected
    and starts receiving lines the moment the app comes up.

    ``spawn`` returns any object with blocking ``readline() -> str | None`` and
    ``close()`` methods (a ``LogStream`` by default), which keeps the restart logic
    unit-testable without real subprocesses.
    """

    def __init__(
        self,
        resolve_pids: Callable[[], list[int]],
        spawn: Callable[[list[int]], LogStream],
        poll_interval: float = 2.0,
    ) -> None:
        self._resolve = resolve_pids
        self._spawn = spawn
        self._poll_interval = poll_interval
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._closed = threading.Event()
        self._lock = threading.Lock()
        self._source: LogStream | None = None
        self._current_pids: list[int] | None = None
        self._supervisor = threading.Thread(target=self._supervise, daemon=True)
        self._supervisor.start()

    def _supervise(self) -> None:
        while not self._closed.is_set():
            try:
                pids = sorted(set(self._resolve()))
            except Exception:
                pids = []
            if pids != self._current_pids:
                self._swap(pids)
            self._closed.wait(self._poll_interval)
        self._stop_source()

    def _swap(self, pids: list[int]) -> None:
        self._stop_source()
        self._current_pids = pids
        if not pids or self._closed.is_set():
            return  # app not running (or shutting down): tail nothing until it starts
        source = self._spawn(pids)
        with self._lock:
            if self._closed.is_set():
                source.close()
                return
            self._source = source
        threading.Thread(target=self._drain, args=(source,), daemon=True).start()

    def _drain(self, source: LogStream) -> None:
        while not self._closed.is_set():
            line = source.readline()
            if line is None:
                return  # this tail ended (killed on swap, or process gone)
            self._queue.put(line)

    def _stop_source(self) -> None:
        with self._lock:
            source, self._source = self._source, None
        if source is not None:
            source.close()

    def readline(self) -> str | None:
        """Block for the next scoped log line; returns None only after ``close()``."""
        while not self._closed.is_set():
            try:
                return self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
        return None

    def close(self) -> None:
        """Stop supervising and tear down the current tail; readline() returns None."""
        self._closed.set()
        self._stop_source()
        self._queue.put(None)  # unblock a parked readline()


def matches_filter(line: str, filter_str: str | None) -> bool:
    """Case-insensitive substring filter; no filter matches everything."""
    if not filter_str:
        return True
    return filter_str.lower() in line.lower()


def apply_filter(text: str, filter_str: str | None, lines: int | None = None) -> str:
    """Keep matching lines, optionally trimming to the last `lines` lines."""
    kept = [line for line in text.splitlines() if matches_filter(line, filter_str)]
    if lines is not None and lines > 0:
        kept = kept[-lines:]
    return "\n".join(kept)
