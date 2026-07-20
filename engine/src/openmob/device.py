"""Abstract device interface shared by all platform backends."""

from abc import ABC, abstractmethod


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
    def logs(self) -> str:
        """Return recent device logs."""

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
