"""HTTP + WebSocket API server (see docs/API.md)."""

import asyncio
import io
import logging
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from PIL import Image
from pydantic import BaseModel

from openmob import __version__
from openmob.device import Device, DeviceError
from openmob.manager import DeviceManager, DeviceNotFound

HOST = "127.0.0.1"
PORT = 8930

STREAM_FPS = 8  # screencap poll fallback rate
VIDEO_STREAM_FPS = 20  # relay cap for the H.264 video pipeline
JPEG_QUALITY = 70

logger = logging.getLogger(__name__)

manager = DeviceManager()
router = APIRouter(prefix="/api/v1")

# Devices for which the video->poll fallback has already been logged.
_fallback_logged: set[str] = set()


def _android_stream_mode() -> str:
    """Streaming backend for Android mirrors: "video" (default) or "poll"."""
    return os.environ.get("OPENMOB_ANDROID_STREAM", "video").strip().lower()


class TapBody(BaseModel):
    x: int
    y: int


class SwipeBody(BaseModel):
    x1: int
    y1: int
    x2: int
    y2: int
    duration_ms: int = 300


class TextBody(BaseModel):
    text: str


class KeyBody(BaseModel):
    key: str


class PackageBody(BaseModel):
    package: str


def device_info(device: Device) -> dict[str, str | int]:
    try:
        return device.info()
    except Exception:
        # Screen size is unavailable while a device is offline (or unimplemented).
        return {
            "id": device.id,
            "name": device.name,
            "platform": device.platform,
            "status": device.status,
            "width": 0,
            "height": 0,
        }


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/devices")
def list_devices() -> list[dict[str, str | int]]:
    return [device_info(device) for device in manager.refresh()]


@router.get("/devices/{device_id}/screenshot")
def screenshot(device_id: str) -> Response:
    return Response(content=manager.get(device_id).screenshot(), media_type="image/png")


@router.post("/devices/{device_id}/tap")
def tap(device_id: str, body: TapBody) -> dict[str, bool]:
    manager.get(device_id).tap(body.x, body.y)
    return {"ok": True}


@router.post("/devices/{device_id}/swipe")
def swipe(device_id: str, body: SwipeBody) -> dict[str, bool]:
    manager.get(device_id).swipe(body.x1, body.y1, body.x2, body.y2, body.duration_ms)
    return {"ok": True}


@router.post("/devices/{device_id}/text")
def input_text(device_id: str, body: TextBody) -> dict[str, bool]:
    manager.get(device_id).input_text(body.text)
    return {"ok": True}


@router.post("/devices/{device_id}/key")
def press_key(device_id: str, body: KeyBody) -> dict[str, bool]:
    manager.get(device_id).press_key(body.key)
    return {"ok": True}


@router.post("/devices/{device_id}/install")
def install(device_id: str, file: UploadFile) -> dict[str, bool]:
    device = manager.get(device_id)
    suffix = Path(file.filename or "app.apk").suffix or ".apk"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name
    try:
        device.install_app(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return {"ok": True}


@router.post("/devices/{device_id}/uninstall")
def uninstall(device_id: str, body: PackageBody) -> dict[str, bool]:
    manager.get(device_id).uninstall_app(body.package)
    return {"ok": True}


@router.get("/devices/{device_id}/apps")
def list_apps(device_id: str) -> list[dict[str, str]]:
    return manager.get(device_id).list_apps()


@router.post("/devices/{device_id}/launch")
def launch(device_id: str, body: PackageBody) -> dict[str, bool]:
    manager.get(device_id).launch_app(body.package)
    return {"ok": True}


@router.websocket("/devices/{device_id}/stream")
async def stream(websocket: WebSocket, device_id: str) -> None:
    """Push binary JPEG frames until the client disconnects."""
    await websocket.accept()
    try:
        device = manager.get(device_id)
    except DeviceNotFound:
        await websocket.close(code=4004, reason=f"device {device_id!r} not found")
        return
    try:
        if device.platform == "android" and _android_stream_mode() != "poll":
            try:
                await _stream_video(websocket, device)
                return
            except DeviceError as exc:
                if device.id not in _fallback_logged:
                    _fallback_logged.add(device.id)
                    logger.warning(
                        "video stream unavailable for %s (%s); "
                        "falling back to screencap polling",
                        device.id,
                        exc,
                    )
        await _stream_poll(websocket, device)
    except (WebSocketDisconnect, ConnectionError):
        pass
    except DeviceError:
        await websocket.close(code=1011, reason="stream failed")


async def _stream_video(websocket: WebSocket, device: Device) -> None:
    """Relay frames from the device's screenrecord->ffmpeg pipeline (~20 fps cap).

    screenrecord only encodes when the display updates, and its decoder holds the
    last frame until the next update arrives. So: prime the client with one
    screencap frame, and when the pipeline goes stale (keepalive repeat, detected
    by identity) send a fresh screencap instead of the repeated frame.
    """
    frames = device.stream_frames()  # raises DeviceError -> caller falls back to poll
    interval = 1 / VIDEO_STREAM_FPS
    loop = asyncio.get_running_loop()
    previous: bytes | None = None
    try:
        try:
            await websocket.send_bytes(await run_in_threadpool(_capture_jpeg, device))
        except DeviceError:
            pass  # priming is best-effort; video frames may still arrive
        while True:
            started = loop.time()
            frame = await run_in_threadpool(next, frames, None)
            if frame is None:
                raise DeviceError("video pipeline ended")
            if frame and frame is not previous:
                previous = frame
            else:
                # Stale tick (keepalive repeat or nothing decoded yet): refresh via
                # screencap so sparse updates, which sit in the decoder until the
                # next display change, become visible within ~1 s.
                try:
                    frame = await run_in_threadpool(_capture_jpeg, device)
                except DeviceError:
                    frame = previous  # keep the last good frame as a keepalive
            if frame:
                await websocket.send_bytes(frame)
            elapsed = loop.time() - started
            await asyncio.sleep(max(0.0, interval - elapsed))
    finally:
        await run_in_threadpool(frames.close)


async def _stream_poll(websocket: WebSocket, device: Device) -> None:
    """Poll screenshots and relay them as JPEG frames (~8 fps)."""
    interval = 1 / STREAM_FPS
    loop = asyncio.get_running_loop()
    while True:
        started = loop.time()
        frame = await run_in_threadpool(_capture_jpeg, device)
        await websocket.send_bytes(frame)
        elapsed = loop.time() - started
        await asyncio.sleep(max(0.0, interval - elapsed))


def _capture_jpeg(device: Device) -> bytes:
    image = Image.open(io.BytesIO(device.screenshot())).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
    return buffer.getvalue()


def create_app() -> FastAPI:
    app = FastAPI(title="OpenMob Engine", version=__version__)
    app.include_router(router)

    @app.exception_handler(DeviceNotFound)
    async def _not_found(request: Request, exc: DeviceNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(DeviceError)
    async def _device_error(request: Request, exc: DeviceError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(NotImplementedError)
    async def _not_implemented(request: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(status_code=501, content={"detail": str(exc)})

    return app


app = create_app()


def serve(port: int = PORT) -> None:
    """Run the API server (blocking)."""
    import uvicorn

    uvicorn.run(app, host=HOST, port=port, log_level="info")
