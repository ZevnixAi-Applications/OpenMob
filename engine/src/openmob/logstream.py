"""Line-oriented log streaming over a tailing subprocess (adb logcat, syslog live)."""

import os
import signal
import subprocess


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
