"""mDNS (Bonjour/zeroconf) advertisement of the engine on the local network."""

import logging
import socket

from zeroconf import ServiceInfo, Zeroconf

from openmob import __version__

SERVICE_TYPE = "_openmob._tcp.local."

logger = logging.getLogger(__name__)


def local_hostname() -> str:
    """This machine's hostname without any trailing `.local` suffix."""
    return socket.gethostname().removesuffix(".local")


def local_addresses() -> list[bytes]:
    """Best-effort LAN IPv4 address of this machine, packed for ServiceInfo.

    Opens a UDP socket towards a public address to learn the default route's
    source IP; no packets are actually sent. Falls back to loopback.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 53))
            return [socket.inet_aton(sock.getsockname()[0])]
    except OSError:
        return [socket.inet_aton("127.0.0.1")]


def build_service_info(port: int, hostname: str | None = None) -> ServiceInfo:
    """Describe this engine as an `_openmob._tcp.local.` service."""
    host = hostname or local_hostname()
    return ServiceInfo(
        type_=SERVICE_TYPE,
        name=f"OpenMob Engine on {host}.{SERVICE_TYPE}",
        port=port,
        addresses=local_addresses(),
        properties={"version": __version__},
        server=f"{host}.local.",
    )


class MdnsAdvertiser:
    """Registers the engine on the LAN; call stop() to unregister cleanly."""

    def __init__(self, port: int) -> None:
        self.info = build_service_info(port)
        self._zeroconf: Zeroconf | None = None

    def start(self) -> None:
        self._zeroconf = Zeroconf()
        self._zeroconf.register_service(self.info)
        logger.info("mDNS: registered %s on port %d", self.info.name, self.info.port)

    def stop(self) -> None:
        if self._zeroconf is None:
            return
        try:
            self._zeroconf.unregister_service(self.info)
        finally:
            self._zeroconf.close()
            self._zeroconf = None
        logger.info("mDNS: unregistered %s", self.info.name)
