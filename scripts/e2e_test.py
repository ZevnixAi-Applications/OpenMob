#!/usr/bin/env python
"""OpenMob release-gate E2E harness.

Drives the deterministic testbed app (testapp/) on a device using ONLY the
OpenMob engine HTTP API on 127.0.0.1:8930 — this validates the engine, not
adb/WDA. (App install/launch may go through the engine too, since the engine
exposes install/launch endpoints.)

Run with:  uv run --project engine python scripts/e2e_test.py [DEVICE_ID]

The target device defaults to the Android emulator (emulator-5554); override
with a CLI argument or the OPENMOB_DEVICE env var. Android: the testbed APK is
installed through the engine. iOS: the testbed app (ai.zevnix.openmobTestbed)
must already be installed (xcodebuild-signed .app, installed via devicectl —
the engine install endpoint takes .ipa files, not .app bundles); the script
only launches it through the engine.

Requires the engine to be serving on port 8930.
"""

from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path

import httpx
from PIL import Image
from websockets.sync.client import connect as ws_connect

BASE = "http://127.0.0.1:8930/api/v1"
WS_BASE = "ws://127.0.0.1:8930/api/v1"
DEVICE = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("OPENMOB_DEVICE", "emulator-5554")
ANDROID_PACKAGE = "ai.zevnix.openmob_testbed"
IOS_BUNDLE = "ai.zevnix.openmobTestbed"
REPO = Path(__file__).resolve().parent.parent
APK = REPO / "testapp" / "build" / "app" / "outputs" / "flutter-apk" / "app-release.apk"

# Exact colors the testbed renders.
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
YELLOW = (255, 255, 0)
MAGENTA = (255, 0, 255)

# PNG screenshots are lossless; allow a tiny per-channel slack for any
# colorspace conversion. JPEG stream frames get a looser budget.
# iOS: WDA screenshots go through display color management (P3 panel ->
# sRGB PNG), so "pure" red arrives as e.g. (253, 0, 2) — allow +-10.
PNG_TOL = 8
IOS_PNG_TOL = 10
JPEG_TOL = 60

SETTLE = 0.8  # seconds to wait after an action before sampling

passed = 0
failed = 0


def report(ok: bool, name: str, detail: str = "") -> None:
    global passed, failed
    tag = "PASS" if ok else "FAIL"
    if ok:
        passed += 1
    else:
        failed += 1
    print(f"[{tag}] {name}" + (f" — {detail}" if detail else ""), flush=True)
    if not ok:
        sys.exit(f"aborting: step failed: {name}")


def close_to(pixel: tuple[int, int, int], color: tuple[int, int, int], tol: int) -> bool:
    return all(abs(p - c) <= tol for p, c in zip(pixel, color))


def classify(pixel: tuple[int, int, int], tol: int) -> str | None:
    for name, color in [
        ("red", RED), ("green", GREEN), ("blue", BLUE),
        ("yellow", YELLOW), ("magenta", MAGENTA),
    ]:
        if close_to(pixel, color, tol):
            return name
    return None


class Engine:
    def __init__(self) -> None:
        self.http = httpx.Client(base_url=BASE, timeout=30)

    def devices(self) -> list[dict]:
        r = self.http.get("/devices")
        r.raise_for_status()
        return r.json()

    def screenshot(self) -> Image.Image:
        r = self.http.get(f"/devices/{DEVICE}/screenshot")
        r.raise_for_status()
        assert r.headers["content-type"] == "image/png", r.headers
        return Image.open(io.BytesIO(r.content)).convert("RGB")

    def tap(self, x: int, y: int) -> None:
        r = self.http.post(f"/devices/{DEVICE}/tap", json={"x": x, "y": y})
        r.raise_for_status()

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        r = self.http.post(
            f"/devices/{DEVICE}/swipe",
            json={"x1": x1, "y1": y1, "x2": x2, "y2": y2, "duration_ms": duration_ms},
        )
        r.raise_for_status()

    def text(self, text: str) -> None:
        r = self.http.post(f"/devices/{DEVICE}/text", json={"text": text})
        r.raise_for_status()

    def install(self, apk: Path) -> None:
        with apk.open("rb") as fh:
            r = self.http.post(
                f"/devices/{DEVICE}/install",
                files={"file": (apk.name, fh, "application/octet-stream")},
                timeout=300,
            )
        r.raise_for_status()

    def launch(self, package: str) -> None:
        r = self.http.post(f"/devices/{DEVICE}/launch", json={"package": package})
        r.raise_for_status()


def sample(img: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    return img.getpixel((x, y))[:3]


def main() -> None:
    global PNG_TOL
    eng = Engine()

    # a. Devices ------------------------------------------------------------
    devices = eng.devices()
    dev = next((d for d in devices if d["id"] == DEVICE), None)
    report(
        dev is not None and dev["status"] == "online"
        and 200 < dev["width"] < 10000 and 200 < dev["height"] < 10000,
        f"a. GET /devices: {DEVICE} online with sane size",
        f"{dev}",
    )
    if dev["platform"] == "ios":
        PNG_TOL = IOS_PNG_TOL
    w, h = dev["width"], dev["height"]
    cx, cy = w // 2, h // 2
    strip_xy = (cx, int(h * 0.10))       # inside top-15% strip, below status icons
    field_xy = (cx, int(h * 0.95))       # inside bottom-10% TextField band
    p2_xy = (cx, int(h * 0.40))          # page-2 sample, above any keyboard

    # Install + launch the testbed via the engine (build happens outside).
    # iOS: the app must be preinstalled (signed .app via devicectl); the engine
    # install endpoint expects an .ipa, so only launch goes through the engine.
    if dev["platform"] == "android":
        if not APK.is_file():
            report(False, "testbed APK exists", str(APK))
        eng.install(APK)
        eng.launch(ANDROID_PACKAGE)
    else:
        eng.launch(IOS_BUNDLE)
    time.sleep(3.0)  # cold start settle

    # b. Screenshot + center sample -----------------------------------------
    img = eng.screenshot()
    report(
        img.size == (w, h),
        "b1. screenshot decodes; size matches /devices",
        f"png={img.size} devices={(w, h)}",
    )
    center = sample(img, cx, cy)
    report(
        close_to(center, RED, PNG_TOL) or close_to(center, GREEN, PNG_TOL),
        "b2. center pixel is pure red or green",
        f"center={center}",
    )
    is_red = close_to(center, RED, PNG_TOL)

    # c. Single tap flips the color -----------------------------------------
    eng.tap(cx, cy)
    time.sleep(SETTLE)
    center = sample(eng.screenshot(), cx, cy)
    expect = GREEN if is_red else RED
    report(close_to(center, expect, PNG_TOL), "c. tap flips center color", f"center={center}")
    is_red = not is_red

    # d. 10 alternating taps -------------------------------------------------
    ok = True
    detail = ""
    for i in range(10):
        eng.tap(cx, cy)
        time.sleep(SETTLE)
        center = sample(eng.screenshot(), cx, cy)
        expect = GREEN if is_red else RED
        if not close_to(center, expect, PNG_TOL):
            ok, detail = False, f"iteration {i}: expected {expect}, got {center}"
            break
        is_red = not is_red
    report(ok, "d. 10x tap alternates red/green every time", detail or "10/10 flips correct")

    # e. Text input drives the parity strip ---------------------------------
    eng.tap(*field_xy)          # focus the TextField
    time.sleep(1.2)             # allow keyboard/IME focus to settle
    eng.text("hello")           # N=5 -> yellow strip
    time.sleep(SETTLE)
    strip = sample(eng.screenshot(), *strip_xy)
    report(close_to(strip, YELLOW, PNG_TOL), 'e1. "hello" (5 chars) -> yellow strip', f"strip={strip}")

    eng.text("x")               # N=6 -> blue strip
    time.sleep(SETTLE)
    strip = sample(eng.screenshot(), *strip_xy)
    report(close_to(strip, BLUE, PNG_TOL), 'e2. +"x" (6 chars) -> blue strip', f"strip={strip}")

    # Parity alone cannot distinguish "hello" from a lone "h" (both odd), so a
    # third append with a 2-char payload catches first-char-only drop modes:
    # true count 6+2=8 -> blue; drop mode would be 3 -> yellow.
    eng.text("ab")              # N=8 -> still blue
    time.sleep(SETTLE)
    strip = sample(eng.screenshot(), *strip_xy)
    report(close_to(strip, BLUE, PNG_TOL), 'e3. +"ab" (8 chars) -> blue strip', f"strip={strip}")

    # Dismiss keyboard with a background tap (also toggles the color).
    eng.tap(cx, cy)
    time.sleep(SETTLE)
    is_red = not is_red

    # f. Swipe to page 2 and back -------------------------------------------
    eng.swipe(int(w * 0.85), int(h * 0.40), int(w * 0.15), int(h * 0.40), 300)
    time.sleep(1.2)             # page transition settle
    p2 = sample(eng.screenshot(), *p2_xy)
    report(close_to(p2, MAGENTA, PNG_TOL), "f1. swipe right-to-left -> page 2 magenta", f"pixel={p2}")

    eng.tap(cx, cy)             # snap back to page 1
    time.sleep(SETTLE)
    center = sample(eng.screenshot(), cx, cy)
    report(
        close_to(center, RED, PNG_TOL) or close_to(center, GREEN, PNG_TOL),
        "f2. tap on page 2 returns to page 1",
        f"center={center}",
    )
    is_red = close_to(center, RED, PNG_TOL)

    # g1. Soak: 40 x (screenshot + tap) --------------------------------------
    errors = 0
    wrong = 0
    for i in range(40):
        eng.tap(cx, cy)
        time.sleep(0.6)
        try:
            center = sample(eng.screenshot(), cx, cy)
        except Exception as exc:  # noqa: BLE001 — any HTTP/decode error is a soak failure
            errors += 1
            print(f"    soak cycle {i}: error {exc}", flush=True)
            continue
        expect = GREEN if is_red else RED
        if not close_to(center, expect, PNG_TOL):
            wrong += 1
            print(f"    soak cycle {i}: expected {expect}, got {center}", flush=True)
        is_red = not is_red
    report(
        errors == 0 and wrong == 0,
        "g1. soak: 40x screenshot+tap, zero errors, zero wrong colors",
        f"errors={errors} wrong_colors={wrong}",
    )

    # g2. WebSocket stream for 20 s ------------------------------------------
    frames = 0
    max_gap = 0.0
    bad_frames: list[str] = []
    deadline = time.monotonic() + 20.0
    with ws_connect(f"{WS_BASE}/devices/{DEVICE}/stream", max_size=None) as ws:
        last = time.monotonic()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            data = ws.recv(timeout=min(remaining + 0.5, 5.0))
            now = time.monotonic()
            max_gap = max(max_gap, now - last)
            last = now
            frames += 1
            frame = Image.open(io.BytesIO(data)).convert("RGB")
            pixel = sample(frame, cx, cy)
            kind = classify(pixel, JPEG_TOL)
            if kind not in ("red", "green"):
                bad_frames.append(f"frame {frames}: center={pixel} classified={kind}")
    report(
        frames >= 15 and max_gap <= 4.0 and not bad_frames,
        "g2. WS stream 20s: >=15 frames, no gap >4s, every frame red/green",
        f"frames={frames} max_gap={max_gap:.2f}s bad={bad_frames[:3]}",
    )

    print(f"\nE2E RESULT: {passed} passed, {failed} failed")
    if failed == 0:
        print("E2E-OK")


if __name__ == "__main__":
    main()
