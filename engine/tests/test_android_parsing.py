"""Unit tests for adb output parsing (no device required)."""

import pytest

from openmob.android import escape_text, parse_devices, parse_launcher_labels, parse_wm_size
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


# Trimmed from real `adb shell cmd package query-activities -a android.intent.action.MAIN
# -c android.intent.category.LAUNCHER` output (Android 16 emulator).
QUERY_ACTIVITIES_OUTPUT = """\
  Activity Resolver Table:
      ActivityInfo:
        name=lawgenie.com.MainActivity
        packageName=lawgenie.com
        labelRes=0x0 nonLocalizedLabel=NyayX icon=0x7f0c0001 banner=0x0
        ApplicationInfo:
          name=android.app.Application
          packageName=lawgenie.com
          labelRes=0x0 nonLocalizedLabel=NyayX icon=0x7f0c0001 banner=0x0
      ActivityInfo:
        name=com.android.chrome/.Main
        packageName=com.android.chrome
        labelRes=0x7f140350 nonLocalizedLabel=null icon=0x7f090378 banner=0x0
      ActivityInfo:
        name=com.example.spaces.MainActivity
        packageName=com.example.spaces
        labelRes=0x0 nonLocalizedLabel=My Cool App icon=0x0 banner=0x0
"""


def test_parse_launcher_labels() -> None:
    labels = parse_launcher_labels(QUERY_ACTIVITIES_OUTPUT)
    assert labels == {
        "lawgenie.com": "NyayX",
        "com.example.spaces": "My Cool App",
    }


def test_parse_launcher_labels_skips_null() -> None:
    labels = parse_launcher_labels(QUERY_ACTIVITIES_OUTPUT)
    assert "com.android.chrome" not in labels


def test_parse_launcher_labels_first_non_null_wins() -> None:
    output = """\
      ActivityInfo:
        packageName=com.example.app
        labelRes=0x0 nonLocalizedLabel=Activity Label icon=0x0 banner=0x0
        ApplicationInfo:
          packageName=com.example.app
          labelRes=0x0 nonLocalizedLabel=App Label icon=0x0 banner=0x0
    """
    assert parse_launcher_labels(output) == {"com.example.app": "Activity Label"}


def test_parse_launcher_labels_activity_null_application_set() -> None:
    output = """\
      ActivityInfo:
        packageName=com.example.app
        labelRes=0x7f0f0019 nonLocalizedLabel=null icon=0x0 banner=0x0
        ApplicationInfo:
          packageName=com.example.app
          labelRes=0x0 nonLocalizedLabel=App Label icon=0x7f0d0001 banner=0x0
    """
    assert parse_launcher_labels(output) == {"com.example.app": "App Label"}


def test_parse_launcher_labels_empty() -> None:
    assert parse_launcher_labels("") == {}
    assert parse_launcher_labels("no labels here\n") == {}
