"""Unit tests for mDNS advertisement (zeroconf mocked, no network required)."""

import socket
import sys
from unittest.mock import MagicMock

import pytest

from openmob import __version__, mdns, server
from openmob.mdns import SERVICE_TYPE, MdnsAdvertiser, build_service_info


def test_build_service_info_fields() -> None:
    info = build_service_info(8935, hostname="testhost")
    assert info.type == SERVICE_TYPE
    assert info.name == f"OpenMob Engine on testhost.{SERVICE_TYPE}"
    assert info.port == 8935
    assert info.server == "testhost.local."
    assert info.properties[b"version"] == __version__.encode()
    assert len(info.addresses) == 1


def test_build_service_info_strips_local_suffix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "gethostname", lambda: "mymac.local")
    info = build_service_info(8930)
    assert info.name == f"OpenMob Engine on mymac.{SERVICE_TYPE}"


def test_advertiser_registers_and_unregisters(monkeypatch: pytest.MonkeyPatch) -> None:
    zc = MagicMock()
    monkeypatch.setattr(mdns, "Zeroconf", lambda: zc)

    advertiser = MdnsAdvertiser(8935)
    advertiser.start()
    zc.register_service.assert_called_once_with(advertiser.info)
    assert advertiser.info.port == 8935
    assert advertiser.info.type == SERVICE_TYPE

    advertiser.stop()
    zc.unregister_service.assert_called_once_with(advertiser.info)
    zc.close.assert_called_once()


def test_advertiser_stop_without_start_is_noop() -> None:
    MdnsAdvertiser(8935).stop()  # must not raise


def test_serve_advertises_and_unregisters(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, int] | str] = []

    class FakeAdvertiser:
        def __init__(self, port: int) -> None:
            calls.append(("init", port))

        def start(self) -> None:
            calls.append("start")

        def stop(self) -> None:
            calls.append("stop")

    monkeypatch.setattr(mdns, "MdnsAdvertiser", FakeAdvertiser)
    monkeypatch.setitem(sys.modules, "uvicorn", MagicMock())
    hooks_before = len(server.app.router.on_shutdown)
    try:
        server.serve(port=8935, mdns=True)
    finally:
        del server.app.router.on_shutdown[hooks_before:]
    assert ("init", 8935) in calls
    assert "start" in calls
    assert "stop" in calls  # via the finally fallback (uvicorn mocked out)


def test_serve_no_mdns(monkeypatch: pytest.MonkeyPatch) -> None:
    advertiser = MagicMock()
    monkeypatch.setattr(mdns, "MdnsAdvertiser", advertiser)
    monkeypatch.setitem(sys.modules, "uvicorn", MagicMock())
    server.serve(port=8935, mdns=False)
    advertiser.assert_not_called()


def test_advertiser_stop_closes_even_if_unregister_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    zc = MagicMock()
    zc.unregister_service.side_effect = OSError("socket gone")
    monkeypatch.setattr(mdns, "Zeroconf", lambda: zc)

    advertiser = MdnsAdvertiser(8935)
    advertiser.start()
    with pytest.raises(OSError):
        advertiser.stop()
    zc.close.assert_called_once()
