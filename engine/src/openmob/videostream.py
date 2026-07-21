"""Low-latency Android screen streaming via screenrecord H.264 piped through ffmpeg.

Pipeline:

    adb -s SERIAL exec-out screenrecord --output-format=h264 --size WxH -
        | ffmpeg -f h264 -i - -f image2pipe -c:v mjpeg -

A background thread pumps ffmpeg's MJPEG output through :class:`JpegStreamParser`
and keeps only the newest decoded JPEG (latency over completeness). screenrecord
stops after 180 s, so the pump restarts the pipe on EOF; :class:`RestartGuard`
aborts after repeated fruitless restarts so callers can fall back to screencap
polling.

Note that screenrecord encodes only when the display updates: on a static screen
no new frames arrive. :class:`FrameStream` therefore re-yields the previous frame
(same object, so callers can identity-compare) after ``keepalive`` seconds of
silence, letting callers detect staleness and refresh by other means.
"""

import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from functools import cache
from pathlib import Path

from openmob.device import DeviceError
from openmob.osinfo import is_windows

logger = logging.getLogger(__name__)

SOI = b"\xff\xd8"
EOI = b"\xff\xd9"

# Yielded by FrameStream when the pipeline has decoded nothing within the
# keepalive window and there is no previous frame to repeat. Callers should
# treat it (and identity-repeats of the previous frame) as "stale, refresh
# by other means if you need liveness".
STALE = b""

MAX_WIDTH = 720  # cap the streamed width; height scales to keep aspect
JPEG_QUALITY = 7  # ffmpeg -q:v scale (2-31, lower is better)
BIT_RATE = "8M"
READ_SIZE = 65536
MAX_CONSECUTIVE_FAILURES = 3
KEEPALIVE_SECONDS = 1.0
FAILURE_RESTART_DELAY = 0.3


@cache
def find_ffmpeg() -> str:
    """Locate the ffmpeg binary; PATH lookup everywhere, plus Homebrew paths on Unix."""
    if not is_windows():
        # Homebrew installs GUI apps do not see on their PATH; probe them first.
        for candidate in (Path("/opt/homebrew/bin/ffmpeg"), Path("/usr/local/bin/ffmpeg")):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    if on_path := shutil.which("ffmpeg"):
        return on_path
    raise DeviceError("ffmpeg not found: install it and add it to PATH (macOS: `brew install ffmpeg`)")


def capped_size(width: int, height: int, max_width: int = MAX_WIDTH) -> tuple[int, int]:
    """Scale (width, height) down so width <= max_width, rounded to even numbers."""
    scale = min(1.0, max_width / width)
    return (
        max(2, int(width * scale) // 2 * 2),
        max(2, int(height * scale) // 2 * 2),
    )


class JpegStreamParser:
    """Extract complete JPEG images from an arbitrarily chunked byte stream.

    Scans for SOI/EOI markers; frames may be split across chunks and garbage
    between frames is discarded.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        """Add bytes and return all JPEG frames completed so far (oldest first)."""
        self._buffer.extend(chunk)
        frames: list[bytes] = []
        while True:
            start = self._buffer.find(SOI)
            if start < 0:
                # No frame start yet: drop garbage, keeping a trailing 0xFF that
                # could be the first half of an SOI split across chunks.
                keep = 1 if self._buffer.endswith(SOI[:1]) else 0
                del self._buffer[: len(self._buffer) - keep]
                break
            if start:
                del self._buffer[:start]
            end = self._buffer.find(EOI, len(SOI))
            if end < 0:
                break
            frames.append(bytes(self._buffer[: end + len(EOI)]))
            del self._buffer[: end + len(EOI)]
        return frames


class RestartGuard:
    """Track consecutive failed pipeline runs and cap how many are tolerated."""

    def __init__(self, max_failures: int = MAX_CONSECUTIVE_FAILURES) -> None:
        self.max_failures = max_failures
        self.failures = 0

    def record_success(self) -> None:
        self.failures = 0

    def record_failure(self) -> None:
        self.failures += 1

    @property
    def exhausted(self) -> bool:
        return self.failures >= self.max_failures


class _FrameSlot:
    """Thread-safe holder for the newest frame; stale frames are overwritten."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._frame: bytes | None = None
        self._seq = 0
        self._done = False
        self._error: DeviceError | None = None

    def put(self, frame: bytes) -> None:
        with self._cond:
            self._frame = frame
            self._seq += 1
            self._cond.notify_all()

    def finish(self, error: DeviceError | None = None) -> None:
        with self._cond:
            self._done = True
            if error is not None and self._error is None:
                self._error = error
            self._cond.notify_all()

    def get(self, last_seq: int, keepalive: float) -> tuple[bytes | None, int]:
        """Return (frame, seq) newer than last_seq; after `keepalive` seconds of
        silence return the previous frame again (or STALE if there is none yet);
        return (None, last_seq) when the pipeline has finished."""
        with self._cond:
            while True:
                if self._seq > last_seq:
                    return self._frame, self._seq
                if self._done:
                    if self._error is not None:
                        raise self._error
                    return None, last_seq
                if not self._cond.wait(timeout=keepalive):
                    return (self._frame if self._frame is not None else STALE), self._seq


class _ProcSupervisor:
    """Track the pipeline's current subprocesses so any thread can kill them."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: tuple[subprocess.Popen, ...] = ()
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    def adopt(self, *procs: subprocess.Popen) -> bool:
        """Register the current subprocesses; kill them and return False if closed."""
        with self._lock:
            self._procs = procs
            if self._closed:
                self._kill_locked()
                return False
            return True

    def kill_current(self) -> None:
        with self._lock:
            self._kill_locked()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._kill_locked()

    def _kill_locked(self) -> None:
        for proc in self._procs:
            if proc.poll() is None:
                try:
                    if is_windows():
                        # No process groups / SIGKILL on Windows; kill the process.
                        proc.kill()
                    else:
                        # start_new_session=True makes each proc a group leader.
                        os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
        for proc in self._procs:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:  # pragma: no cover
                pass
        self._procs = ()


def _run_pipeline_once(
    adb: str,
    ffmpeg: str,
    serial: str,
    size: tuple[int, int],
    slot: _FrameSlot,
    supervisor: _ProcSupervisor,
) -> bool:
    """Run one screenrecord->ffmpeg pass until EOF; return True if frames came out."""
    width, height = size
    record = subprocess.Popen(
        [
            adb, "-s", serial, "exec-out", "screenrecord",
            "--output-format=h264", f"--size={width}x{height}", f"--bit-rate={BIT_RATE}", "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    decode = subprocess.Popen(
        [
            ffmpeg, "-loglevel", "error",
            # Minimal input probing keeps startup latency low. Do NOT add
            # `-fflags nobuffer`: with raw H.264 input, ffmpeg 8 then emits nothing.
            "-probesize", "32", "-analyzeduration", "0", "-flags", "low_delay",
            "-f", "h264", "-i", "-",
            "-f", "image2pipe", "-c:v", "mjpeg", "-pix_fmt", "yuvj420p",
            "-q:v", str(JPEG_QUALITY), "-",
        ],
        stdin=record.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    assert record.stdout is not None and decode.stdout is not None
    record.stdout.close()  # ffmpeg owns the read end now
    try:
        if not supervisor.adopt(record, decode):
            return False
        parser = JpegStreamParser()
        produced = False
        while True:
            chunk = decode.stdout.read1(READ_SIZE)
            if not chunk:
                break
            if frames := parser.feed(chunk):
                produced = True
                slot.put(frames[-1])  # newest only; older frames in the chunk are stale
        return produced
    finally:
        supervisor.kill_current()


def _pump(
    adb: str,
    ffmpeg: str,
    serial: str,
    size: tuple[int, int],
    slot: _FrameSlot,
    supervisor: _ProcSupervisor,
) -> None:
    """Keep the pipeline running (screenrecord stops after 180 s) until closed."""
    guard = RestartGuard()
    try:
        while not supervisor.closed:
            produced = _run_pipeline_once(adb, ffmpeg, serial, size, slot, supervisor)
            if supervisor.closed:
                break
            if produced:
                guard.record_success()
            else:
                guard.record_failure()
                if guard.exhausted:
                    raise DeviceError(
                        f"video pipeline for {serial} produced no frames "
                        f"in {guard.failures} consecutive runs"
                    )
                time.sleep(FAILURE_RESTART_DELAY)
        slot.finish()
    except DeviceError as exc:
        slot.finish(exc)
    except Exception as exc:  # pragma: no cover - defensive
        slot.finish(DeviceError(f"video pipeline for {serial} crashed: {exc}"))


class FrameStream:
    """Iterator of JPEG frames mirroring an Android screen, newest frame only.

    ``next()`` blocks until a new frame is decoded; after ``keepalive`` seconds
    of silence it returns the previous frame again (the identical object, so
    callers can detect the repeat with ``is``), or ``STALE`` if nothing has been
    decoded yet. ``close()`` is safe to call from any thread and kills both
    subprocess groups.
    """

    def __init__(
        self,
        adb: str,
        serial: str,
        size: tuple[int, int],
        keepalive: float = KEEPALIVE_SECONDS,
    ) -> None:
        ffmpeg = find_ffmpeg()  # raises DeviceError early so callers can fall back
        self._slot = _FrameSlot()
        self._supervisor = _ProcSupervisor()
        self._keepalive = keepalive
        self._last_seq = 0
        self._thread = threading.Thread(
            target=_pump,
            args=(adb, ffmpeg, serial, capped_size(*size), self._slot, self._supervisor),
            name=f"openmob-video-{serial}",
            daemon=True,
        )
        self._thread.start()

    def __iter__(self) -> "FrameStream":
        return self

    def __next__(self) -> bytes:
        frame, self._last_seq = self._slot.get(self._last_seq, self._keepalive)
        if frame is None:
            raise StopIteration
        return frame

    def close(self) -> None:
        """Tear down the pipeline: kill subprocess groups and wake any reader."""
        self._supervisor.close()
        self._slot.finish()
        self._thread.join(timeout=5)
