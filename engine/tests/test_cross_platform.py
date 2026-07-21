"""Cross-platform binary/path resolution and iOS macOS-gating (no devices required).

Windows/macOS behaviour is exercised by monkeypatching ``platform.system`` (read
at call time by ``openmob.osinfo``), ``os.environ``, and a fake filesystem via
``monkeypatch.setattr`` on ``pathlib.Path`` probes. Every ``@cache``d finder is
cleared before use so a prior call's result does not leak between OS scenarios.
"""

import platform
from pathlib import Path

import pytest

from openmob import android, ios, osinfo, sim, videostream, virtual
from openmob.debugger import DebugError, DebugSessionManager
from openmob.device import DeviceError


@pytest.fixture(autouse=True)
def _clear_finder_caches():
    """adb/emulator/cmdline-tool/ffmpeg finders are cached; reset around each test."""
    for finder in (
        android.find_adb,
        virtual.find_emulator,
        virtual.find_sdkmanager,
        virtual.find_avdmanager,
        videostream.find_ffmpeg,
    ):
        finder.cache_clear()
    yield
    for finder in (
        android.find_adb,
        virtual.find_emulator,
        virtual.find_sdkmanager,
        virtual.find_avdmanager,
        videostream.find_ffmpeg,
    ):
        finder.cache_clear()


def _fake_fs(monkeypatch, existing: set[str]) -> None:
    """Make only paths in `existing` look like present, executable files."""
    existing = {str(Path(p)) for p in existing}
    monkeypatch.setattr(Path, "is_file", lambda self: str(self) in existing)
    monkeypatch.setattr("openmob.android.os.access", lambda p, mode: str(p) in existing)
    monkeypatch.setattr("openmob.virtual.os.access", lambda p, mode: str(p) in existing)
    monkeypatch.setattr("openmob.videostream.os.access", lambda p, mode: str(p) in existing)


def _as_windows(monkeypatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Windows")


def _as_macos(monkeypatch) -> None:
    monkeypatch.setattr(platform, "system", lambda: "Darwin")


# --- osinfo helpers ---------------------------------------------------------


def test_exe_and_script_names_on_windows(monkeypatch) -> None:
    _as_windows(monkeypatch)
    assert osinfo.exe_name("adb") == "adb.exe"
    assert osinfo.exe_name("emulator") == "emulator.exe"
    assert osinfo.script_name("sdkmanager") == "sdkmanager.bat"
    assert osinfo.is_windows() and not osinfo.is_macos()


def test_exe_and_script_names_on_macos(monkeypatch) -> None:
    _as_macos(monkeypatch)
    assert osinfo.exe_name("adb") == "adb"
    assert osinfo.script_name("sdkmanager") == "sdkmanager"
    assert osinfo.is_macos() and not osinfo.is_windows()


# --- adb resolution ---------------------------------------------------------


def test_find_adb_windows_localappdata(monkeypatch) -> None:
    _as_windows(monkeypatch)
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\dev\AppData\Local")
    # Built with the same joins the code uses so the comparison is host-agnostic
    # (a real Windows host resolves the backslashes; here we only assert equality).
    adb = Path(r"C:\Users\dev\AppData\Local") / "Android" / "Sdk" / "platform-tools" / "adb.exe"
    _fake_fs(monkeypatch, {str(adb)})
    monkeypatch.setattr("openmob.android.shutil.which", lambda name: None)
    assert android.find_adb() == str(adb)


def test_find_adb_windows_android_home_uses_exe(monkeypatch) -> None:
    _as_windows(monkeypatch)
    monkeypatch.setenv("ANDROID_HOME", r"D:\sdk")
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    adb = Path(r"D:\sdk") / "platform-tools" / "adb.exe"
    _fake_fs(monkeypatch, {str(adb)})
    monkeypatch.setattr("openmob.android.shutil.which", lambda name: None)
    assert android.find_adb() == str(adb)


def test_find_adb_windows_falls_back_to_path(monkeypatch) -> None:
    _as_windows(monkeypatch)
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\dev\AppData\Local")
    _fake_fs(monkeypatch, set())
    monkeypatch.setattr(
        "openmob.android.shutil.which",
        lambda name: r"C:\tools\adb.exe" if name == "adb" else None,
    )
    assert android.find_adb() == r"C:\tools\adb.exe"


def test_find_adb_macos_uses_library_path(monkeypatch) -> None:
    _as_macos(monkeypatch)
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    adb = Path.home() / "Library/Android/sdk/platform-tools/adb"
    _fake_fs(monkeypatch, {str(adb)})
    monkeypatch.setattr("openmob.android.shutil.which", lambda name: None)
    assert android.find_adb() == str(adb)


def test_find_adb_missing_raises(monkeypatch) -> None:
    _as_windows(monkeypatch)
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    _fake_fs(monkeypatch, set())
    monkeypatch.setattr("openmob.android.shutil.which", lambda name: None)
    with pytest.raises(DeviceError, match="adb not found"):
        android.find_adb()


# --- emulator resolution ----------------------------------------------------


def test_find_emulator_windows_localappdata(monkeypatch) -> None:
    _as_windows(monkeypatch)
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\dev\AppData\Local")
    emu = Path(r"C:\Users\dev\AppData\Local") / "Android" / "Sdk" / "emulator" / "emulator.exe"
    _fake_fs(monkeypatch, {str(emu)})
    monkeypatch.setattr("openmob.virtual.shutil.which", lambda name: None)
    assert virtual.find_emulator() == str(emu)


def test_find_emulator_uses_android_sdk_root(monkeypatch) -> None:
    _as_windows(monkeypatch)
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.setenv("ANDROID_SDK_ROOT", r"E:\android")
    emu = Path(r"E:\android") / "emulator" / "emulator.exe"
    _fake_fs(monkeypatch, {str(emu)})
    monkeypatch.setattr("openmob.virtual.shutil.which", lambda name: None)
    assert virtual.find_emulator() == str(emu)


# --- sdkmanager / avdmanager resolution -------------------------------------


def test_find_sdkmanager_windows_is_bat(monkeypatch) -> None:
    _as_windows(monkeypatch)
    monkeypatch.setenv("ANDROID_HOME", r"D:\sdk")
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    tool = Path(r"D:\sdk") / "cmdline-tools" / "latest" / "bin" / "sdkmanager.bat"
    _fake_fs(monkeypatch, {str(tool)})
    monkeypatch.setattr("openmob.virtual.shutil.which", lambda name: None)
    assert virtual.find_sdkmanager() == str(tool)


def test_find_avdmanager_macos_no_suffix(monkeypatch) -> None:
    _as_macos(monkeypatch)
    monkeypatch.setenv("ANDROID_HOME", "/opt/android")
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    tool = Path("/opt/android/cmdline-tools/latest/bin/avdmanager")
    _fake_fs(monkeypatch, {str(tool)})
    monkeypatch.setattr("openmob.virtual.shutil.which", lambda name: None)
    assert virtual.find_avdmanager() == str(tool)


def test_sdk_root_windows_default(monkeypatch) -> None:
    _as_windows(monkeypatch)
    monkeypatch.delenv("ANDROID_HOME", raising=False)
    monkeypatch.delenv("ANDROID_SDK_ROOT", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", r"C:\Users\dev\AppData\Local")
    assert virtual._sdk_root() == Path(r"C:\Users\dev\AppData\Local") / "Android" / "Sdk"


# --- ffmpeg resolution ------------------------------------------------------


def test_find_ffmpeg_windows_path_only(monkeypatch) -> None:
    _as_windows(monkeypatch)
    _fake_fs(monkeypatch, set())  # no homebrew paths should even be probed
    monkeypatch.setattr(
        "openmob.videostream.shutil.which",
        lambda name: r"C:\ffmpeg\bin\ffmpeg.exe" if name == "ffmpeg" else None,
    )
    assert videostream.find_ffmpeg() == r"C:\ffmpeg\bin\ffmpeg.exe"


def test_find_ffmpeg_windows_missing_raises(monkeypatch) -> None:
    _as_windows(monkeypatch)
    _fake_fs(monkeypatch, set())
    monkeypatch.setattr("openmob.videostream.shutil.which", lambda name: None)
    with pytest.raises(DeviceError, match="ffmpeg not found"):
        videostream.find_ffmpeg()


# --- iOS gated off macOS ----------------------------------------------------


def test_ios_discover_empty_off_macos(monkeypatch) -> None:
    _as_windows(monkeypatch)
    assert ios.discover() == []


def test_sim_discover_empty_off_macos(monkeypatch) -> None:
    _as_windows(monkeypatch)
    assert sim.discover() == []


def test_list_simulators_empty_off_macos(monkeypatch) -> None:
    _as_windows(monkeypatch)
    assert virtual.list_simulators() == []


def test_create_ios_device_off_macos_raises(monkeypatch) -> None:
    _as_windows(monkeypatch)
    with pytest.raises(DeviceError, match="iOS control requires macOS"):
        virtual.create_virtual_device(
            "ios", "iPhone 15", device_type="iPhone-15", runtime="iOS-18"
        )


def test_ios_create_options_unavailable_off_macos(monkeypatch) -> None:
    _as_windows(monkeypatch)
    options = virtual.create_options()["ios"]
    assert options["available"] is False
    assert "macOS" in options["reason"]


def test_debug_create_off_macos_raises(monkeypatch) -> None:
    _as_windows(monkeypatch)
    manager = DebugSessionManager()
    with pytest.raises(DebugError, match="requires macOS"):
        manager.create(device_id="sim-1", bundle_id="com.example.app")
