"""HTTP + WebSocket API server (see docs/API.md)."""

import asyncio
import contextlib
import io
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
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

STREAM_FPS = 8  # screenshot-poll path (Android, and iOS fallback)
RELAY_MAX_FPS = 15  # cap when relaying a native device stream (iOS MJPEG)
JPEG_QUALITY = 70

manager = DeviceManager()
router = APIRouter(prefix="/api/v1")


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
    """Push binary JPEG frames until the client disconnects.

    Devices exposing a native frame stream (iOS via WDA's MJPEG server) are relayed
    directly; when that stream is unavailable — or for devices without one (Android) —
    frames come from the screenshot-poll loop instead.
    """
    await websocket.accept()
    try:
        # Threadpool: discovery is blocking and uses asyncio.run() internally.
        device = await run_in_threadpool(manager.get, device_id)
    except DeviceNotFound:
        await websocket.close(code=4004, reason=f"device {device_id!r} not found")
        return
    try:
        stream_frames = getattr(device, "stream_frames", None)
        if stream_frames is not None:
            with contextlib.suppress(DeviceError):  # MJPEG unavailable — poll instead
                await relay_latest_frames(stream_frames(), websocket.send_bytes, RELAY_MAX_FPS)
        interval = 1 / STREAM_FPS
        while True:
            started = asyncio.get_running_loop().time()
            frame = await run_in_threadpool(_capture_jpeg, device)
            await websocket.send_bytes(frame)
            elapsed = asyncio.get_running_loop().time() - started
            await asyncio.sleep(max(0.0, interval - elapsed))
    except (WebSocketDisconnect, ConnectionError):
        pass
    except DeviceError:
        await websocket.close(code=1011, reason="screenshot failed")


async def relay_latest_frames(
    frames: AsyncIterator[bytes],
    send: Callable[[bytes], Awaitable[None]],
    max_fps: float,
) -> None:
    """Forward frames to `send`, always the newest one, at most `max_fps` per second.

    The producer is drained continuously into a single latest-frame slot so it never
    backs up: frames that arrive while the consumer is busy are dropped in favor of
    the newest (this keeps mirror latency at ~one frame regardless of consumer speed).
    Returns when the producer ends; re-raises whatever error ended it.
    """
    latest: bytes | None = None
    done = False
    fresh = asyncio.Event()
    errors: list[Exception] = []

    async def pump() -> None:
        nonlocal latest, done
        try:
            async for frame in frames:
                latest = frame
                fresh.set()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            errors.append(exc)
        finally:
            done = True
            fresh.set()

    pump_task = asyncio.create_task(pump())
    interval = 1 / max_fps
    loop = asyncio.get_running_loop()
    try:
        while True:
            if not done:
                await fresh.wait()
            fresh.clear()  # before reading the slot, so a newer frame re-wakes us
            frame, latest = latest, None
            if frame is not None:
                started = loop.time()
                await send(frame)
                elapsed = loop.time() - started
                await asyncio.sleep(max(0.0, interval - elapsed))
            elif done:
                break
        if errors:
            raise errors[0]
    finally:
        pump_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pump_task


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
