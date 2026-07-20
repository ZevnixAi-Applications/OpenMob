"""Unit tests for adb output parsing (no device required)."""

import pytest

from openmob.android import escape_text, parse_devices, parse_wm_size
from openmob.device import DeviceError

DEVICES_OUTPUT = """\
List of devices attached
1585dda1               device usb:2-1.2 product:xun_in model:23073RPBFG device:xun transport_id:2
192.168.1.22:5555      device product:xun_in model:23073RPBFG device:xun transport_id:3
emulator-5554          offline transport_id:4
"""


def test_parse_devices() -> None:
    devices = parse_devices(DEVICES_OUTPUT)
    assert devices == [
        ("1585dda1", "device", "23073RPBFG"),
        ("192.168.1.22:5555", "device", "23073RPBFG"),
        ("emulator-5554", "offline", "emulator-5554"),
    ]


def test_parse_devices_empty() -> None:
    assert parse_devices("List of devices attached\n\n") == []


def test_parse_wm_size_physical() -> None:
    assert parse_wm_size("Physical size: 1080x2400\n") == (1080, 2400)


def test_parse_wm_size_prefers_override() -> None:
    output = "Physical size: 1080x2400\nOverride size: 720x1600\n"
    assert parse_wm_size(output) == (720, 1600)


def test_parse_wm_size_garbage() -> None:
    with pytest.raises(DeviceError):
        parse_wm_size("no size here")


def test_escape_text_spaces() -> None:
    assert escape_text("hello world") == "hello%sworld"


def test_escape_text_specials() -> None:
    assert escape_text("a&b (c)") == "a\\&b%s\\(c\\)"
    assert escape_text('say "hi"') == 'say%s\\"hi\\"'


def test_escape_text_plain() -> None:
    assert escape_text("plain-text_123") == "plain-text_123"
