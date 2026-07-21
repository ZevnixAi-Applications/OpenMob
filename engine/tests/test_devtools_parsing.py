"""Unit tests for developer-tools parsers (crash reports, logs, VM service)."""

import json

import pytest

from openmob.android import parse_battery_level, parse_crash_buffer, parse_dropbox_crashes
from openmob.device import DeviceError
from openmob.flutter import parse_vm_service_url, ws_endpoint
from openmob.ios import _split_container_path, crash_sort_key, parse_ips_headline
from openmob.logstream import apply_filter, matches_filter

# Captured from `adb shell dumpsys dropbox --print data_app_crash` on an API-35 emulator.
DROPBOX_OUTPUT = """\
Drop box contents: 4 entries
Max entries: 1000
Searching for: data_app_crash

========================================
2026-07-20 09:00:00 data_app_crash (text, 1200 bytes)
SystemUptimeMs: 1000
Process: com.example.older
PID: 1111
Package: com.example.older v1 (1.0.0)
Timestamp: 2026-07-20 09:00:00.000+0530

java.lang.IllegalStateException: older crash
\tat com.example.Older.main(Older.java:1)
========================================
2026-07-21 10:57:41 data_app_crash (text, 1302 bytes)
SystemUptimeMs: 62331177
Process: ai.zevnix.openmob_testbed
PID: 5776
UID: 10227
Flags: 0x2089be46
Package: ai.zevnix.openmob_testbed v1 (1.0.0)
Foreground: Yes
Build: google/sdk_gphone16k_arm64/emu64a16k:17/CP21.260330.012/15545953:user/dev-keys

android.app.RemoteServiceException$CrashedByAdbException: shell-induced crash
\tat android.app.ActivityThread.throwRemoteServiceException(ActivityThread.java:2581)
\tat android.os.Looper.loop(Looper.java:397)
"""

# Captured from `adb logcat -d -b crash` on the same emulator.
CRASH_BUFFER_OUTPUT = """\
--------- beginning of crash
07-21 10:57:41.225  5776  5776 E AndroidRuntime: FATAL EXCEPTION: main
07-21 10:57:41.225  5776  5776 E AndroidRuntime: Process: ai.zevnix.openmob_testbed, PID: 5776
07-21 10:57:41.225  5776  5776 E AndroidRuntime: android.app.RemoteServiceException$CrashedByAdbException: shell-induced crash
07-21 10:57:41.225  5776  5776 E AndroidRuntime: \tat android.app.ActivityThread.throwRemoteServiceException(ActivityThread.java:2581)
07-21 10:57:41.225  5776  5776 E AndroidRuntime: \tat android.os.Looper.loop(Looper.java:397)
07-21 11:02:03.000  6001  6001 E AndroidRuntime: FATAL EXCEPTION: main
07-21 11:02:03.000  6001  6001 E AndroidRuntime: Process: com.example.newer, PID: 6001
07-21 11:02:03.000  6001  6001 E AndroidRuntime: java.lang.RuntimeException: newer crash
07-21 11:02:03.000  6001  6001 E AndroidRuntime: \tat com.example.Newer.main(Newer.java:1)
"""

# Real .ips structure: one-line JSON header, then a (multi-line) JSON body.
IPS_HEADER = {
    "app_name": "WebDriverAgentRunner-Runner",
    "timestamp": "2026-07-20 17:33:45.00 +0530",
    "bundleID": "ai.zevnix.WebDriverAgentRunner.xctrunner",
    "os_version": "iPhone OS 26.5.2 (23F84)",
    "name": "WebDriverAgentRunner-Runner",
    "incident_id": "585D9602-9580-4AB9-8E57-052C545F56C5",
}
IPS_BODY = {
    "procName": "WebDriverAgentRunner-Runner",
    "exception": {"type": "EXC_CRASH", "signal": "SIGABRT", "codes": "0x0, 0x0"},
    "termination": {"namespace": "SIGNAL", "code": 6, "indicator": "Abort trap: 6"},
}
IPS_RAW = json.dumps(IPS_HEADER) + "\n" + json.dumps(IPS_BODY, indent=1)


def test_parse_dropbox_crashes_newest_first() -> None:
    crashes = parse_dropbox_crashes(DROPBOX_OUTPUT)
    assert crashes == [
        {
            "date": "2026-07-21 10:57:41",
            "process": "ai.zevnix.openmob_testbed",
            "exception": (
                "android.app.RemoteServiceException$CrashedByAdbException: shell-induced crash"
            ),
        },
        {
            "date": "2026-07-20 09:00:00",
            "process": "com.example.older",
            "exception": "java.lang.IllegalStateException: older crash",
        },
    ]


def test_parse_dropbox_no_entries() -> None:
    assert parse_dropbox_crashes("Drop box contents: 0 entries\n\n(No entries found.)\n") == []


def test_parse_crash_buffer_newest_first() -> None:
    crashes = parse_crash_buffer(CRASH_BUFFER_OUTPUT)
    assert crashes == [
        {
            "date": "07-21 11:02:03",
            "process": "com.example.newer",
            "exception": "java.lang.RuntimeException: newer crash",
        },
        {
            "date": "07-21 10:57:41",
            "process": "ai.zevnix.openmob_testbed",
            "exception": (
                "android.app.RemoteServiceException$CrashedByAdbException: shell-induced crash"
            ),
        },
    ]


def test_parse_crash_buffer_empty() -> None:
    assert parse_crash_buffer("--------- beginning of crash\n") == []


def test_parse_battery_level() -> None:
    assert parse_battery_level("Current Battery Service state:\n  level: 87\n  scale: 100\n") == 87
    assert parse_battery_level("no battery here") is None


def test_parse_ips_headline() -> None:
    summary = parse_ips_headline(IPS_RAW)
    assert summary == {
        "bundle": "ai.zevnix.WebDriverAgentRunner.xctrunner",
        "app_name": "WebDriverAgentRunner-Runner",
        "date": "2026-07-20 17:33:45.00 +0530",
        "os_version": "iPhone OS 26.5.2 (23F84)",
        "exception_type": "EXC_CRASH",
        "signal": "SIGABRT",
        "termination_reason": "SIGNAL Abort trap: 6",
    }


def test_parse_ips_headline_header_only() -> None:
    summary = parse_ips_headline(json.dumps(IPS_HEADER) + "\nnot json body")
    assert summary["bundle"] == "ai.zevnix.WebDriverAgentRunner.xctrunner"
    assert summary["exception_type"] == ""


def test_parse_ips_headline_garbage() -> None:
    with pytest.raises(DeviceError):
        parse_ips_headline("plain text, not an ips file")


def test_crash_sort_key_orders_by_embedded_date() -> None:
    names = [
        "WebDriverAgentRunner-Runner-2026-07-20-171424.ips",
        "SiriSearchFeedback-2026-07-08-150229.000.ips",
        "WebDriverAgentRunner-Runner-2026-07-20-173345.ips",
    ]
    names.sort(key=crash_sort_key, reverse=True)
    assert names[0] == "WebDriverAgentRunner-Runner-2026-07-20-173345.ips"
    assert names[-1] == "SiriSearchFeedback-2026-07-08-150229.000.ips"


def test_split_container_path() -> None:
    assert _split_container_path("com.example.app:/Documents/x.db") == (
        "com.example.app",
        "/Documents/x.db",
    )
    assert _split_container_path("/DCIM/photo.jpg") == (None, "/DCIM/photo.jpg")
    assert _split_container_path("notes.txt") == (None, "notes.txt")


def test_parse_vm_service_url_takes_last_match() -> None:
    logcat = (
        "06-18 12:00:00.000 1234 1256 I flutter : The Dart VM service is listening on "
        "http://127.0.0.1:11111/old-token=/\n"
        "07-21 10:57:29.204 5776 5808 I flutter : The Dart VM service is listening on "
        "http://127.0.0.1:39215/0FIADRh0zas=/\n"
    )
    assert parse_vm_service_url(logcat) == "http://127.0.0.1:39215/0FIADRh0zas=/"
    assert parse_vm_service_url("no service here") is None


def test_ws_endpoint() -> None:
    assert ws_endpoint("http://127.0.0.1:39215/0FIADRh0zas=/") == (
        "ws://127.0.0.1:39215/0FIADRh0zas=/ws"
    )
    assert ws_endpoint("http://127.0.0.1:39215/tok=") == "ws://127.0.0.1:39215/tok=/ws"


def test_matches_filter() -> None:
    assert matches_filter("E/ActivityManager: boom", "activitymanager")
    assert not matches_filter("I/chatty: fine", "boom")
    assert matches_filter("anything", None)
    assert matches_filter("anything", "")


def test_apply_filter_trims_to_last_lines() -> None:
    text = "a boom 1\nquiet\na boom 2\na boom 3\n"
    assert apply_filter(text, "boom", 2) == "a boom 2\na boom 3"
    assert apply_filter(text, None, None) == "a boom 1\nquiet\na boom 2\na boom 3"
