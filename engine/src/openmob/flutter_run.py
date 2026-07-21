"""OpenMob-managed ``flutter run`` sessions (the `--machine` daemon protocol).

Hot reload only works when the Flutter tool itself owns the running app: it keeps
the kernel compiler alive and knows how to push incremental sources. Talking to a
plain installed APK over the Dart VM service fails with "Error while starting Kernel
isolate task". So instead of poking an app someone else launched, OpenMob launches
the app for you with ``flutter run --machine`` and drives it over that daemon.

``flutter run --machine`` speaks a line-oriented JSON protocol on stdout/stdin. Each
line is a JSON *array* holding one message object:

    <- [{"event":"daemon.connected","params":{"version":"0.6.1","pid":123}}]
    <- [{"event":"app.start","params":{"appId":"…","supportsRestart":true}}]
    <- [{"event":"app.debugPort","params":{"appId":"…","wsUri":"ws://…/ws"}}]
    <- [{"event":"app.started","params":{"appId":"…"}}]
    -> [{"id":1,"method":"app.restart","params":{"appId":"…","fullRestart":false}}]
    <- [{"id":1,"result":{"code":0,"message":null}}]   # code 0 == reload succeeded

``app.restart`` with ``fullRestart:false`` is a hot reload; ``true`` is a hot restart.
Because the command travels the SAME channel the tool built the app on, the reload is
real — not the VM-service ``reloadSources`` fallback that an installed APK rejects.
"""

import collections
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from openmob.device import Device, DeviceError

# The first build (cold) can take minutes; later runs are quick. Generous ceiling.
STARTUP_TIMEOUT = 300.0
COMMAND_TIMEOUT = 120.0
STOP_TIMEOUT = 15.0
DEVTOOLS_TIMEOUT = 30.0
LOG_RING = 500


def find_flutter() -> str:
    """Locate the flutter binary (OPENMOB_FLUTTER overrides PATH lookup)."""
    if override := os.environ.get("OPENMOB_FLUTTER"):
        return override
    if on_path := shutil.which("flutter"):
        return on_path
    raise DeviceError("flutter not found: add flutter to PATH or set OPENMOB_FLUTTER")


def find_dart() -> str:
    """Locate the dart binary (used to serve DevTools)."""
    if override := os.environ.get("OPENMOB_DART"):
        return override
    if on_path := shutil.which("dart"):
        return on_path
    raise DeviceError("dart not found: add dart to PATH or set OPENMOB_DART")


def validate_project(project_path: str) -> Path:
    """Return the resolved project dir, or raise if it is not a Flutter project."""
    path = Path(project_path).expanduser()
    if not path.is_dir():
        raise DeviceError(f"project path not found or not a directory: {project_path}")
    if not (path / "pubspec.yaml").is_file():
        raise DeviceError(f"not a Flutter project (no pubspec.yaml): {project_path}")
    return path


def build_run_command(flutter: str, device_id: str, mode: str = "debug") -> list[str]:
    """Construct the ``flutter run --machine`` argv for a device and mode."""
    normalized = (mode or "debug").lower()
    if normalized not in {"debug", "profile"}:
        raise DeviceError(f"unsupported run mode {mode!r} (expected 'debug' or 'profile')")
    return [flutter, "run", "--machine", "-d", device_id, f"--{normalized}"]


def parse_daemon_messages(line: str) -> list[dict]:
    """Decode one ``flutter run --machine`` stdout line into message dicts.

    Protocol lines are a JSON array of message objects; anything else (compiler
    chatter, a bare app print) yields an empty list so the caller can treat it as
    plain log output.
    """
    stripped = line.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return []
    try:
        decoded = json.loads(stripped)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [message for message in decoded if isinstance(message, dict)]


def build_command_line(request_id: int, method: str, params: dict) -> str:
    """Serialize a daemon command to the exact line written to the tool's stdin."""
    return json.dumps([{"id": request_id, "method": method, "params": params}])


def restart_outcome(result: dict) -> dict:
    """Interpret an ``app.restart`` result. ``code == 0`` means the reload worked."""
    code = result.get("code", 0)
    outcome: dict[str, object] = {"success": code == 0, "code": code}
    if message := result.get("message"):
        outcome["message"] = message
    return outcome


class _LogSubscriber:
    """A blocking readline()/close() view over a session's live log lines."""

    def __init__(self, session: "FlutterRunSession") -> None:
        self._queue: queue.Queue[str | None] = queue.Queue()
        self._session = session
        self.closed = False

    def put(self, line: str) -> None:
        if not self.closed:
            self._queue.put(line)

    def readline(self) -> str | None:
        if self.closed:
            return None
        return self._queue.get()

    def close(self) -> None:
        self.closed = True
        self._session._unsubscribe(self)
        self._queue.put(None)


@dataclass
class _Pending:
    event: threading.Event = field(default_factory=threading.Event)
    response: dict | None = None


class FlutterRunSession:
    """One ``flutter run --machine`` subprocess and the state parsed from its daemon."""

    def __init__(self, device_id: str, project_path: str, mode: str = "debug") -> None:
        self.device_id = device_id
        self.project_path = project_path
        self.mode = mode
        self.session_id = f"flrun-{device_id}-{int(time.time() * 1000)}"

        self.app_id: str | None = None
        self.vm_service_uri: str | None = None
        self.base_uri: str | None = None
        self.supports_restart = True
        self.started = False
        self.stopped = False
        self.exit_reason: str | None = None
        self.last_reload: dict | None = None

        self._proc: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._next_id = 0
        self._pending: dict[int, _Pending] = {}
        self._logs: collections.deque[str] = collections.deque(maxlen=LOG_RING)
        self._subscribers: set[_LogSubscriber] = set()
        self._lock = threading.Lock()
        self._started_event = threading.Event()
        self._start_error: str | None = None

    # --- lifecycle ---------------------------------------------------------

    def start(self, timeout: float = STARTUP_TIMEOUT) -> dict:
        """Spawn the tool and block until the app starts (or a build failure)."""
        cmd = build_run_command(find_flutter(), self.device_id, self.mode)
        try:
            self._proc = subprocess.Popen(  # noqa: S603 — args built from validated inputs
                cmd,
                cwd=self.project_path,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={**os.environ},
            )
        except OSError as exc:
            raise DeviceError(f"could not launch flutter run: {exc}") from exc
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        if not self._started_event.wait(timeout):
            self.stop(force=True)
            raise DeviceError(
                f"flutter run did not start within {int(timeout)}s. Last output:\n{self._tail()}"
            )
        if self._start_error:
            raise DeviceError(self._start_error)
        return self.info()

    def _read_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for raw in proc.stdout:
            line = raw.rstrip("\n")
            messages = parse_daemon_messages(line)
            if not messages:
                if line.strip():
                    self._emit_log(line)
                continue
            for message in messages:
                self._handle_message(message)
        self._on_exit()

    def _handle_message(self, message: dict) -> None:
        if "event" in message:
            self._handle_event(message["event"], message.get("params") or {})
        elif "id" in message:
            self._resolve(message)

    def _handle_event(self, event: str, params: dict) -> None:
        if event == "app.start":
            self.app_id = params.get("appId") or self.app_id
            self.supports_restart = bool(params.get("supportsRestart", True))
        elif event == "app.debugPort":
            self.app_id = params.get("appId") or self.app_id
            self.vm_service_uri = params.get("wsUri") or self.vm_service_uri
            self.base_uri = params.get("baseUri") or self.base_uri
        elif event == "app.started":
            self.app_id = params.get("appId") or self.app_id
            self.started = True
            self._started_event.set()
        elif event == "app.log":
            log = params.get("log")
            if log is not None:
                self._emit_log(str(log).rstrip("\n"))
        elif event == "app.progress":
            text = params.get("message")
            if text and not params.get("finished"):
                self._emit_log(f"[build] {text}")
        elif event == "daemon.logMessage":
            text = params.get("message")
            if text:
                self._emit_log(f"[daemon] {text}")
        elif event == "app.stop":
            self.stopped = True

    def _resolve(self, message: dict) -> None:
        with self._lock:
            pending = self._pending.get(message.get("id"))
        if pending is not None:
            pending.response = message
            pending.event.set()

    def _on_exit(self) -> None:
        code = self._proc.poll() if self._proc else None
        self.stopped = True
        self.exit_reason = f"process exited with code {code}"
        if not self.started:
            self._start_error = (
                f"flutter run exited before the app started (code {code}). "
                f"Last output:\n{self._tail()}"
            )
            self._started_event.set()
        with self._lock:
            pending = list(self._pending.values())
            self._pending.clear()
        for entry in pending:
            entry.event.set()  # unblock callers; response stays None -> DeviceError
        self._close_subscribers()

    # --- commands ----------------------------------------------------------

    def _send(self, method: str, params: dict, timeout: float = COMMAND_TIMEOUT) -> dict:
        proc = self._proc
        if proc is None or proc.poll() is not None or proc.stdin is None:
            raise DeviceError("flutter run session is not running")
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            pending = _Pending()
            self._pending[request_id] = pending
        try:
            proc.stdin.write(build_command_line(request_id, method, params) + "\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            with self._lock:
                self._pending.pop(request_id, None)
            raise DeviceError(f"could not send {method} to flutter run: {exc}") from exc
        if not pending.event.wait(timeout):
            with self._lock:
                self._pending.pop(request_id, None)
            raise DeviceError(f"flutter {method} timed out after {int(timeout)}s")
        with self._lock:
            self._pending.pop(request_id, None)
        response = pending.response
        if response is None:
            raise DeviceError(f"flutter run ended before {method} completed")
        if "error" in response:
            raise DeviceError(f"flutter {method} failed: {response['error']}")
        result = response.get("result")
        return result if isinstance(result, dict) else {}

    def reload(self, full_restart: bool = False) -> dict:
        """Hot reload (or hot restart) over the daemon; returns the real outcome."""
        if self.app_id is None:
            raise DeviceError("flutter run session has no app id yet")
        result = self._send(
            "app.restart",
            {"appId": self.app_id, "fullRestart": full_restart, "pause": False, "reason": "manual"},
        )
        outcome = restart_outcome(result)
        outcome["kind"] = "hot-restart" if full_restart else "hot-reload"
        self.last_reload = outcome
        return outcome

    def stop(self, force: bool = False) -> dict:
        proc = self._proc
        if proc is None:
            self.stopped = True
            return {"stopped": True}
        if not force and self.app_id and proc.poll() is None:
            try:
                self._send("app.stop", {"appId": self.app_id}, timeout=STOP_TIMEOUT)
            except DeviceError:
                pass  # fall through to terminate
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=10)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                proc.kill()
        self.stopped = True
        self._close_subscribers()
        return {"stopped": True, "session_id": self.session_id}

    # --- logs --------------------------------------------------------------

    def _emit_log(self, line: str) -> None:
        self._logs.append(line)
        with self._lock:
            subscribers = list(self._subscribers)
        for subscriber in subscribers:
            subscriber.put(line)

    def _tail(self, count: int = 25) -> str:
        return "\n".join(list(self._logs)[-count:])

    def stream(self) -> _LogSubscriber:
        """Return a live log view, primed with recent history."""
        subscriber = _LogSubscriber(self)
        with self._lock:
            self._subscribers.add(subscriber)
            history = list(self._logs)
        for line in history:
            subscriber.put(line)
        return subscriber

    def _unsubscribe(self, subscriber: _LogSubscriber) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def _close_subscribers(self) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
            self._subscribers.clear()
        for subscriber in subscribers:
            subscriber.closed = True
            subscriber._queue.put(None)

    # --- reporting ---------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None and not self.stopped

    def recent_logs(self, count: int = 50) -> list[str]:
        return list(self._logs)[-count:]

    def info(self) -> dict:
        return {
            "session_id": self.session_id,
            "device_id": self.device_id,
            "project_path": self.project_path,
            "mode": self.mode,
            "app_id": self.app_id,
            "vm_service_uri": self.vm_service_uri,
            "base_uri": self.base_uri,
            "running": self.running,
            "supports_restart": self.supports_restart,
            "last_reload": self.last_reload,
            "exit_reason": None if self.running else self.exit_reason,
        }


class DevToolsServer:
    """A shared ``dart devtools --machine`` server; one serves every app by ?uri=."""

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self.host: str | None = None
        self.port: int | None = None
        self._lock = threading.Lock()

    def _ensure(self) -> None:
        with self._lock:
            if self._proc is not None and self._proc.poll() is None and self.port:
                return
            proc = subprocess.Popen(  # noqa: S603
                [find_dart(), "devtools", "--machine", "--no-launch-browser"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )
            deadline = time.monotonic() + DEVTOOLS_TIMEOUT
            assert proc.stdout is not None
            while time.monotonic() < deadline:
                line = proc.stdout.readline()
                if line == "":
                    break
                try:
                    message = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                if message.get("event") == "server.started":
                    params = message.get("params") or {}
                    self.host = params.get("host", "127.0.0.1")
                    self.port = params.get("port")
                    self._proc = proc
                    threading.Thread(target=self._drain, args=(proc,), daemon=True).start()
                    return
            proc.kill()
            raise DeviceError("could not start `dart devtools` (no server.started event)")

    def _drain(self, proc: subprocess.Popen) -> None:
        if proc.stdout is None:
            return
        for _ in proc.stdout:  # keep the pipe from filling once we have the port
            pass

    def url_for(self, vm_service_uri: str) -> str:
        self._ensure()
        return f"http://{self.host}:{self.port}/?uri={vm_service_uri}"


class FlutterRunManager:
    """Tracks one managed run session per device, plus a shared DevTools server."""

    def __init__(self) -> None:
        self._sessions: dict[str, FlutterRunSession] = {}
        self._devtools: DevToolsServer | None = None
        self._lock = threading.Lock()

    def start(self, device: Device, project_path: str, mode: str = "debug") -> FlutterRunSession:
        resolved = validate_project(project_path)
        with self._lock:
            existing = self._sessions.get(device.id)
        if existing is not None and existing.running:
            raise DeviceError(
                f"a flutter run session is already active for {device.id}; stop it first"
            )
        session = FlutterRunSession(device.id, str(resolved), mode)
        session.start()
        with self._lock:
            self._sessions[device.id] = session
        return session

    def get(self, device_id: str) -> FlutterRunSession | None:
        with self._lock:
            return self._sessions.get(device_id)

    def stop(self, device_id: str) -> dict:
        with self._lock:
            session = self._sessions.pop(device_id, None)
        if session is None:
            raise DeviceError(f"no flutter run session for {device_id}")
        return session.stop()

    def devtools_url(self, session: FlutterRunSession) -> dict:
        if not session.vm_service_uri:
            raise DeviceError("the run session has no VM service URI yet")
        with self._lock:
            if self._devtools is None:
                self._devtools = DevToolsServer()
            server = self._devtools
        try:
            url = server.url_for(session.vm_service_uri)
        except DeviceError as exc:
            # DevTools couldn't be served; still hand back the VM service so tooling
            # can point its own inspector at the app.
            return {"vm_service_uri": session.vm_service_uri, "note": str(exc)}
        return {"devtools_url": url, "vm_service_uri": session.vm_service_uri}
