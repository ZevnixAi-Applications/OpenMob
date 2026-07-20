"""iOS device backend.

Stub for now: discovery returns no devices and every action raises. A real
implementation over pymobiledevice3 + WebDriverAgent will slot in here in the
next milestone without changing the `Device` interface.
"""

from openmob.device import Device

_NOT_IMPLEMENTED = "iOS support coming in the next milestone"


class IosDevice(Device):
    """An iOS device (not yet implemented)."""

    def __init__(self, udid: str, name: str, status: str = "online") -> None:
        self._udid = udid
        self._name = name
        self._status = status

    @property
    def id(self) -> str:
        return self._udid

    @property
    def name(self) -> str:
        return self._name

    @property
    def platform(self) -> str:
        return "ios"

    @property
    def status(self) -> str:
        return self._status

    @property
    def width(self) -> int:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @property
    def height(self) -> int:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def screenshot(self) -> bytes:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def tap(self, x: int, y: int) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def input_text(self, text: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def press_key(self, key: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def install_app(self, path: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def uninstall_app(self, package: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def list_apps(self) -> list[dict[str, str]]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def launch_app(self, package: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def logs(self) -> str:
        raise NotImplementedError(_NOT_IMPLEMENTED)


def discover() -> list[IosDevice]:
    """Discover connected iOS devices (none until the iOS milestone)."""
    return []
