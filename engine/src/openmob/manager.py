"""Device manager aggregating all platform backends."""

from openmob import android, ios
from openmob.device import Device


class DeviceNotFound(Exception):
    """Raised when no connected device matches the requested id."""

    def __init__(self, device_id: str) -> None:
        super().__init__(f"device {device_id!r} not found")


class DeviceManager:
    """Discovers devices across backends and caches them by id."""

    def __init__(self) -> None:
        self._devices: dict[str, Device] = {}

    def refresh(self) -> list[Device]:
        """Re-scan all backends, keeping cached objects for known ids."""
        found = [*android.discover(), *ios.discover()]
        devices: dict[str, Device] = {}
        for device in found:
            cached = self._devices.get(device.id)
            if cached is not None and cached.platform == device.platform:
                devices[device.id] = cached
            else:
                devices[device.id] = device
        self._devices = devices
        return list(devices.values())

    def get(self, device_id: str) -> Device:
        """Return a device by id, refreshing the list if it is unknown."""
        device = self._devices.get(device_id)
        if device is None:
            self.refresh()
            device = self._devices.get(device_id)
        if device is None:
            raise DeviceNotFound(device_id)
        return device
