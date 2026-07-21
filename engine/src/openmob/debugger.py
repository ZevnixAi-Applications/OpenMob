"""Interactive lldb debug sessions for iOS apps (simulator first, real device gated).

Architecture: lldb's Python module only loads under Xcode's own CPython (3.9),
not the engine's uv-managed 3.12, so each session spawns `openmob/lldb_worker.py`
via `xcrun python3` and talks JSON-lines over stdin/stdout (see that file for the
protocol). Simulator processes are plain macOS processes, so lldb attaches
directly — no tunnel, no sudo, no pairing.

Real devices (iOS 17+) additionally need a usermode tunnel and a debugserver;
`check_real_device_support` probes for them and raises CapabilityError with the
exact commands to run when they are missing.
"""

import json
import queue
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections import deque

import httpx

IDLE_TIMEOUT = 600.0  # seconds without a request before a session is reaped
DEFAULT_TIMEOUT = 20.0
ATTACH_TIMEOUT = 45.0
TUNNELD_URL = "http://127.0.0.1:49151"

TUNNELD_COMMAND = "sudo pymobiledevice3 remote tunneld"
DEBUGSERVER_COMMAND = "pymobiledevice3 developer debugserver start-server"


class DebugError(Exception):
    """A debug operation failed; message is safe to surface to the client."""


class SessionNotFound(DebugError):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"debug session {session_id!r} not found")


class CapabilityError(DebugError):
    """The requested target needs setup the host does not have; carries next steps."""

    def __init__(self, message: str, commands: list[str]) -> None:
        super().__init__(message)
        self.commands = commands


# --- target resolution (simulator) -----------------------------------------


def _run(cmd: list[str], timeout: float = 15.0) -> str:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise DebugError(f"{cmd[0]} not found: install Xcode command line tools") from exc
    except subprocess.TimeoutExpired as exc:
        raise DebugError(f"{' '.join(cmd[:3])} timed out") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise DebugError(f"{' '.join(cmd[:4])} failed: {detail}")
    return result.stdout


def simulator_state(udid: str) -> str | None:
    """Return the simctl state ("Booted", "Shutdown", ...) or None if not a simulator."""
    out = _run(["xcrun", "simctl", "list", "devices", "-j"])
    for devices in json.loads(out).get("devices", {}).values():
        for device in devices:
            if device.get("udid") == udid:
                return device.get("state", "Shutdown")
    return None


def parse_launchctl_pid(output: str, bundle_id: str) -> int | None:
    """Find the pid of `UIKitApplication:<bundle_id>[...]` in `launchctl list` output."""
    pattern = re.compile(
        r"^\s*(\d+)\s+\S+\s+.*UIKitApplication:" + re.escape(bundle_id) + r"(\[|$|\s)"
    )
    for line in output.splitlines():
        match = pattern.match(line)
        if match:
            return int(match.group(1))
    return None


def resolve_simulator_pid(udid: str, bundle_id: str) -> int:
    """Resolve a foreground app's pid inside a booted simulator."""
    out = _run(["xcrun", "simctl", "spawn", udid, "launchctl", "list"])
    pid = parse_launchctl_pid(out, bundle_id)
    if pid is None:
        raise DebugError(
            f"app {bundle_id!r} is not running in simulator {udid} — launch it first "
            f"(xcrun simctl launch {udid} {bundle_id})"
        )
    return pid


# --- real-device capability check ------------------------------------------


def tunneld_devices(url: str = TUNNELD_URL) -> dict | None:
    """Return tunneld's device map, or None when tunneld is not running."""
    try:
        response = httpx.get(f"{url}/", timeout=2.0)
        return response.json()
    except (httpx.HTTPError, ValueError):
        return None


def check_real_device_support(udid: str, debugserver_url: str | None = None) -> str:
    """Validate the real-device debug prerequisites; return the debugserver URL.

    Raises CapabilityError with the exact commands to run when something is missing.
    """
    tunnels = tunneld_devices()
    if tunnels is None:
        raise CapabilityError(
            f"device {udid} is a real device: debugging it requires a usermode tunnel, "
            "and tunneld is not running on this machine",
            commands=[TUNNELD_COMMAND, f"{DEBUGSERVER_COMMAND}  # then retry with its URL"],
        )
    if udid not in tunnels:
        raise CapabilityError(
            f"tunneld is running but has no tunnel for device {udid} "
            "(is it connected and unlocked?)",
            commands=[TUNNELD_COMMAND],
        )
    if not debugserver_url:
        raise CapabilityError(
            f"tunnel to {udid} is up, but a debugserver is required: run the command "
            "below and retry with debugserver_url set to the connect URL it prints",
            commands=[DEBUGSERVER_COMMAND],
        )
    return debugserver_url


# --- worker transport -------------------------------------------------------

_lldb_python_path_cache: str | None = None


def lldb_python_path() -> str:
    global _lldb_python_path_cache
    if _lldb_python_path_cache is None:
        _lldb_python_path_cache = _run(["xcrun", "lldb", "-P"]).strip()
    return _lldb_python_path_cache


class LldbWorker:
    """One lldb worker subprocess; serialized request/response with timeouts."""

    def __init__(self) -> None:
        if shutil.which("xcrun") is None:
            raise DebugError("xcrun not found: install Xcode command line tools")
        worker_path = __file__.replace("debugger.py", "lldb_worker.py")
        self._proc = subprocess.Popen(
            ["xcrun", "python3", worker_path, "--lldb-python-path", lldb_python_path()],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._responses: queue.Queue[dict] = queue.Queue()
        self._stderr_tail: deque[str] = deque(maxlen=40)
        self._next_id = 0
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            try:
                self._responses.put(json.loads(line))
            except ValueError:
                continue  # stray non-protocol output (lldb chatter)

    def _read_stderr(self) -> None:
        assert self._proc.stderr is not None
        for line in self._proc.stderr:
            self._stderr_tail.append(line.rstrip())

    def request(self, cmd: str, timeout: float = DEFAULT_TIMEOUT, **args: object) -> dict:
        if self._proc.poll() is not None:
            raise DebugError(self._death_message())
        self._next_id += 1
        request_id = self._next_id
        message = json.dumps({"id": request_id, "cmd": cmd, **args})
        assert self._proc.stdin is not None
        try:
            self._proc.stdin.write(message + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise DebugError(self._death_message()) from exc
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DebugError(f"lldb worker timed out on {cmd!r} after {timeout}s")
            try:
                response = self._responses.get(timeout=min(remaining, 0.5))
            except queue.Empty:
                if self._proc.poll() is not None:
                    raise DebugError(self._death_message()) from None
                continue
            if response.get("id") != request_id:
                continue  # stale response from a timed-out predecessor
            if not response.get("ok"):
                raise DebugError(response.get("error") or "unknown lldb worker error")
            return response.get("result") or {}

    def _death_message(self) -> str:
        tail = "\n".join(self._stderr_tail).strip()
        return "lldb worker exited unexpectedly" + (f":\n{tail}" if tail else "")

    def close(self) -> None:
        if self._proc.poll() is None:
            try:
                if self._proc.stdin:
                    self._proc.stdin.close()
                self._proc.terminate()
                self._proc.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                self._proc.kill()


# --- sessions ----------------------------------------------------------------


class DebugSession:
    """A live lldb session bound to one process; safe for concurrent callers."""

    def __init__(
        self,
        session_id: str,
        device_id: str,
        worker: LldbWorker,
        pid: int,
        bundle_id: str | None = None,
    ) -> None:
        self.id = session_id
        self.device_id = device_id
        self.pid = pid
        self.bundle_id = bundle_id
        self.created_at = time.time()
        self.last_used = time.monotonic()
        self._worker = worker
        self._lock = threading.Lock()

    def _request(self, cmd: str, timeout: float = DEFAULT_TIMEOUT, **args: object) -> dict:
        with self._lock:
            self.last_used = time.monotonic()
            return self._worker.request(cmd, timeout=timeout, **args)

    def info(self) -> dict:
        return {
            "session_id": self.id,
            "device_id": self.device_id,
            "pid": self.pid,
            "bundle_id": self.bundle_id,
            "created_at": self.created_at,
        }

    def breakpoint_set(self, spec: str) -> dict:
        return self._request("bp_set", spec=spec)

    def breakpoint_list(self) -> list[dict]:
        return self._request("bp_list")["breakpoints"]

    def breakpoint_delete(self, bp_id: int) -> dict:
        return self._request("bp_delete", bp_id=bp_id)

    def cont(self) -> dict:
        return self._request("continue")

    def pause(self) -> dict:
        return self._request("pause")

    def step(self, kind: str) -> dict:
        if kind == "continue":  # MCP debug_step also routes continue/pause here
            return self.cont()
        if kind == "pause":
            return self.pause()
        if kind not in ("in", "over", "out"):
            raise DebugError(f"unknown step kind {kind!r} (expected in/over/out/continue/pause)")
        return self._request("step", kind=kind, timeout=30.0)

    def eval(self, expr: str, frame_id: int | None = None) -> dict:
        return self._request("eval", expr=expr, frame_id=frame_id, timeout=30.0)

    def state(self, stack: bool = True, variables: bool = True, threads: bool = False) -> dict:
        return self._request("state", stack=stack, vars=variables, threads=threads)

    def output(self) -> list[dict]:
        return self._request("output")["chunks"]

    def detach(self, kill: bool = False) -> dict:
        try:
            return self._request("detach", kill=kill)
        finally:
            self.close()

    def close(self) -> None:
        self._worker.close()

    def idle_for(self) -> float:
        return time.monotonic() - self.last_used


class DebugSessionManager:
    """Creates, indexes, and reaps debug sessions (idle timeout 10 min)."""

    def __init__(
        self,
        worker_factory=LldbWorker,
        pid_resolver=resolve_simulator_pid,
        simulator_probe=simulator_state,
        idle_timeout: float = IDLE_TIMEOUT,
    ) -> None:
        self._sessions: dict[str, DebugSession] = {}
        self._lock = threading.Lock()
        self._worker_factory = worker_factory
        self._pid_resolver = pid_resolver
        self._simulator_probe = simulator_probe
        self._idle_timeout = idle_timeout

    def create(
        self,
        device_id: str,
        pid: int | None = None,
        bundle_id: str | None = None,
        breakpoints: list[str] | None = None,
        debugserver_url: str | None = None,
    ) -> tuple[DebugSession, dict]:
        """Attach and return (session, attach state). One session per device."""
        self.reap_idle()
        if pid is None and not bundle_id:
            raise DebugError("either pid or bundle_id is required")
        with self._lock:
            existing = self._find_by_device(device_id)
        if existing is not None:
            raise DebugError(
                f"device {device_id} already has debug session {existing.id!r} — detach it first"
            )

        sim_state = self._simulator_probe(device_id)
        if sim_state is None:
            # Real device: verify tunnel + debugserver prerequisites (raises CapabilityError).
            connect_url = check_real_device_support(device_id, debugserver_url)
            worker = self._worker_factory()
            try:
                result = worker.request("connect", url=connect_url, timeout=ATTACH_TIMEOUT)
            except DebugError:
                worker.close()
                raise
            pid = int(result.get("pid") or pid or 0)
        else:
            if sim_state != "Booted":
                raise DebugError(f"simulator {device_id} is not booted (state: {sim_state})")
            if pid is None:
                assert bundle_id is not None
                pid = self._pid_resolver(device_id, bundle_id)
            worker = self._worker_factory()
            try:
                result = worker.request("attach", pid=pid, timeout=ATTACH_TIMEOUT)
            except DebugError:
                worker.close()
                raise

        session = DebugSession(uuid.uuid4().hex[:12], device_id, worker, pid, bundle_id)
        armed = []
        try:
            for spec in breakpoints or []:
                armed.append(session.breakpoint_set(spec))
            resume = session.cont()  # attach leaves the process stopped; keep the app live
        except DebugError:
            session.close()
            raise
        with self._lock:
            self._sessions[session.id] = session
        return session, {**result, "state": resume["state"], "breakpoints": armed}

    def get(self, session_id: str) -> DebugSession:
        self.reap_idle()
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            raise SessionNotFound(session_id)
        return session

    def get_by_device(self, device_id: str) -> DebugSession:
        self.reap_idle()
        with self._lock:
            session = self._find_by_device(device_id)
        if session is None:
            raise SessionNotFound(f"device:{device_id}")
        return session

    def _find_by_device(self, device_id: str) -> DebugSession | None:
        for session in self._sessions.values():
            if session.device_id == device_id:
                return session
        return None

    def list(self) -> list[dict]:
        self.reap_idle()
        with self._lock:
            return [session.info() for session in self._sessions.values()]

    def remove(self, session_id: str, kill: bool = False) -> dict:
        session = self.get(session_id)
        with self._lock:
            self._sessions.pop(session_id, None)
        try:
            return session.detach(kill=kill)
        except DebugError:
            session.close()  # worker already dead or detach failed; drop it regardless
            return {"detached": True, "killed": kill, "note": "worker was not responsive"}

    def reap_idle(self) -> None:
        with self._lock:
            expired = [s for s in self._sessions.values() if s.idle_for() > self._idle_timeout]
            for session in expired:
                self._sessions.pop(session.id, None)
        for session in expired:
            try:
                session.detach(kill=False)
            except DebugError:
                session.close()
