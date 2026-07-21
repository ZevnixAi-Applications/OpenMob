"""HTTP + WebSocket API server (see docs/API.md)."""

import asyncio
import io
import tempfile
from pathlib import Path

import anyio

from fastapi import APIRouter, FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from PIL import Image
from pydantic import BaseModel

from openmob import __version__, flutter
from openmob.device import Device, DeviceError
from openmob.logstream import matches_filter
from openmob.manager import DeviceManager, DeviceNotFound

HOST = "127.0.0.1"
PORT = 8930

STREAM_FPS = 8
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


class UrlBody(BaseModel):
    url: str


class PathBody(BaseModel):
    path: str


class PushBody(BaseModel):
    local_path: str
    device_path: str


class PullBody(BaseModel):
    device_path: str
    local_path: str


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


@router.get("/devices/{device_id}/logs")
def get_logs(device_id: str, lines: int = 200, filter: str | None = None) -> dict[str, str]:
    return {"logs": manager.get(device_id).logs(lines=lines, filter_str=filter)}


@router.post("/devices/{device_id}/screenshot/save")
def save_screenshot(device_id: str, body: PathBody) -> dict[str, str | bool]:
    png = manager.get(device_id).screenshot()
    target = Path(body.path)
    if not target.is_absolute():
        raise DeviceError(f"path must be absolute: {body.path}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)
    return {"ok": True, "path": str(target)}


@router.get("/devices/{device_id}/crashes")
def crash_reports(device_id: str, limit: int = 5) -> list[dict[str, str]]:
    return manager.get(device_id).crash_reports(limit=limit)


@router.post("/devices/{device_id}/open_url")
def open_url(device_id: str, body: UrlBody) -> dict[str, bool]:
    manager.get(device_id).open_url(body.url)
    return {"ok": True}


@router.post("/devices/{device_id}/clear_data")
def clear_app_data(device_id: str, body: PackageBody) -> dict[str, bool]:
    manager.get(device_id).clear_app_data(body.package)
    return {"ok": True}


@router.post("/devices/{device_id}/force_stop")
def force_stop(device_id: str, body: PackageBody) -> dict[str, bool]:
    manager.get(device_id).force_stop(body.package)
    return {"ok": True}


@router.post("/devices/{device_id}/push")
def push_file(device_id: str, body: PushBody) -> dict[str, bool]:
    manager.get(device_id).push_file(body.local_path, body.device_path)
    return {"ok": True}


@router.post("/devices/{device_id}/pull")
def pull_file(device_id: str, body: PullBody) -> dict[str, bool]:
    manager.get(device_id).pull_file(body.device_path, body.local_path)
    return {"ok": True}


@router.get("/devices/{device_id}/info")
def system_info(device_id: str) -> dict[str, str | int]:
    return manager.get(device_id).system_info()


@router.get("/devices/{device_id}/flutter/vm-service")
def flutter_vm_service(device_id: str) -> dict[str, str]:
    return flutter.vm_service(manager.get(device_id))


@router.post("/devices/{device_id}/flutter/hot-reload")
def flutter_hot_reload(device_id: str) -> dict[str, object]:
    return flutter.hot_reload(manager.get(device_id))


@router.websocket("/devices/{device_id}/logs/stream")
async def logs_stream(websocket: WebSocket, device_id: str, filter: str | None = None) -> None:
    """Push log lines (one text message per line) until the client disconnects."""
    await websocket.accept()
    try:
        device = manager.get(device_id)
        stream = await run_in_threadpool(device.stream_logs)
    except DeviceNotFound:
        await websocket.close(code=4004, reason=f"device {device_id!r} not found")
        return
    except DeviceError as exc:
        await websocket.close(code=1011, reason=str(exc)[:120])
        return

    async def pump() -> None:
        while True:
            line = await run_in_threadpool(stream.readline)
            if line is None:
                return
            if matches_filter(line, filter):
                await websocket.send_text(line)

    async def watch_disconnect() -> None:
        while True:  # raises WebSocketDisconnect when the client goes away
            await websocket.receive()

    tasks = [asyncio.ensure_future(pump()), asyncio.ensure_future(watch_disconnect())]
    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:  # consume expected exceptions (e.g. WebSocketDisconnect)
            task.exception()
    finally:
        # Shielded: cleanup must run even when the endpoint task itself was cancelled
        # by the client disconnecting.
        with anyio.CancelScope(shield=True):
            await run_in_threadpool(stream.close)


@router.websocket("/devices/{device_id}/stream")
async def stream(websocket: WebSocket, device_id: str) -> None:
    """Push binary JPEG frames until the client disconnects."""
    await websocket.accept()
    try:
        device = manager.get(device_id)
    except DeviceNotFound:
        await websocket.close(code=4004, reason=f"device {device_id!r} not found")
        return
    interval = 1 / STREAM_FPS
    try:
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
