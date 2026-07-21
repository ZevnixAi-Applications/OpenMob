"""Host-OS detection and per-OS executable naming.

Every check reads ``platform.system()`` at call time (never cached at import) so
tests can monkeypatch it, and so a single build of the engine behaves correctly
on whatever OS it runs on. OpenMob controls Android (adb is cross-platform) and
Android emulators on Windows, macOS, and Linux; iOS is macOS-only because it
needs Xcode + WebDriverAgent (see the guards in ios/sim/debugger).
"""

import platform

# Shown wherever iOS/simulator/lldb control is attempted off macOS.
IOS_REQUIRES_MACOS = "iOS control requires macOS (Xcode + WebDriverAgent)"


def is_windows() -> bool:
    """True when running on Windows."""
    return platform.system() == "Windows"


def is_macos() -> bool:
    """True when running on macOS."""
    return platform.system() == "Darwin"


def exe_name(name: str) -> str:
    """Executable file name for a bare tool name (``adb`` -> ``adb.exe`` on Windows)."""
    return f"{name}.exe" if is_windows() else name


def script_name(name: str) -> str:
    """SDK cmdline-tool file name (``sdkmanager`` -> ``sdkmanager.bat`` on Windows)."""
    return f"{name}.bat" if is_windows() else name
