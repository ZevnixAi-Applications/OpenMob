"""Abstract device interface shared by all platform backends."""

from abc import ABC, abstractmethod

from openmob.logstream import LogScope, LogStream


class DeviceError(Exception):
    """Raised when a device command fails."""


class Device(ABC):
    """A connected mobile device that can be inspected and controlled."""

    @property
    @abstractmethod
    def id(self) -> str:
        """Stable identifier (adb serial, iOS UDID)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable device name (e.g. model)."""

    @property
    @abstractmethod
    def platform(self) -> str:
        """Either "android" or "ios"."""

    @property
    @abstractmethod
    def status(self) -> str:
        """Either "online" or "offline"."""

    @property
    @abstractmethod
    def width(self) -> int:
        """Screen width in device pixels."""

    @property
    @abstractmethod
    def height(self) -> int:
        """Screen height in device pixels."""

    @abstractmethod
    def screenshot(self) -> bytes:
        """Capture the screen and return PNG bytes."""

    @abstractmethod
    def tap(self, x: int, y: int) -> None:
        """Tap at device pixel coordinates."""

    @abstractmethod
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        """Swipe between two points over the given duration."""

    @abstractmethod
    def input_text(self, text: str) -> None:
        """Type text into the focused field."""

    @abstractmethod
    def press_key(self, key: str) -> None:
        """Press a named key: home, back, power, volume_up, volume_down, enter."""

    @abstractmethod
    def install_app(self, path: str) -> None:
        """Install an app from a local package file (.apk / .ipa)."""

    @abstractmethod
    def uninstall_app(self, package: str) -> None:
        """Uninstall an app by package/bundle identifier."""

    @abstractmethod
    def list_apps(self) -> list[dict[str, str]]:
        """List installed third-party apps as [{"package", "name"}]."""

    @abstractmethod
    def launch_app(self, package: str) -> None:
        """Launch an app by package/bundle identifier."""

    @abstractmethod
    def logs(
        self,
        lines: int = 200,
        filter_str: str | None = None,
        scope: LogScope | None = None,
    ) -> str:
        """Return recent logs, filtered to lines containing `filter_str`.

        When `scope` targets a single app, the tail is restricted to that app's
        process(es); an app that is not running yields an empty result.
        """

    @abstractmethod
    def stream_logs(self, scope: LogScope | None = None) -> LogStream:
        """Start a live log tail; caller must close() the returned stream.

        When `scope` targets a single app, only that app's log output is streamed.
        """

    @abstractmethod
    def crash_reports(self, limit: int = 5) -> list[dict[str, str]]:
        """Return the most recent app crash reports, newest first."""

    @abstractmethod
    def open_url(self, url: str) -> None:
        """Open a URL / deep link on the device."""

    @abstractmethod
    def clear_app_data(self, package: str) -> None:
        """Clear an app's data and cache."""

    @abstractmethod
    def force_stop(self, package: str) -> None:
        """Force-stop a running app."""

    @abstractmethod
    def push_file(self, local_path: str, device_path: str) -> None:
        """Copy a file from the engine host to the device."""

    @abstractmethod
    def pull_file(self, device_path: str, local_path: str) -> None:
        """Copy a file from the device to the engine host."""

    @abstractmethod
    def system_info(self) -> dict[str, str | int]:
        """Return battery level, OS version, and model details."""

    def info(self) -> dict[str, str | int]:
        """Serializable summary used by the REST and MCP layers."""
        return {
            "id": self.id,
            "name": self.name,
            "platform": self.platform,
            "status": self.status,
            "width": self.width,
            "height": self.height,
        }
