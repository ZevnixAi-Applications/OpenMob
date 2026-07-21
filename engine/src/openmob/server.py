"""HTTP + WebSocket API server (see docs/API.md)."""

import asyncio
import contextlib
import io
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import anyio

from fastapi import APIRouter, FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from PIL import Image
from pydantic import BaseModel

from openmob import __version__, flutter, virtual
from openmob.debugger import CapabilityError, DebugError, DebugSessionManager, SessionNotFound
from openmob.device import Device, DeviceError
from openmob.logstream import matches_filter
from openmob.manager import DeviceManager, DeviceNotFound
from openmob.virtual import VirtualDeviceNotFound

HOST = "127.0.0.1"
PORT = 8930

STREAM_FPS = 8  # screenshot-poll path (Android, and iOS fallback)
RELAY_MAX_FPS = 15  # cap when relaying a native device stream (iOS MJPEG)
JPEG_QUALITY = 70

manager = DeviceManager()
debug_manager = DebugSessionManager()
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


class VirtualDeviceBody(BaseModel):
    name: str


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


# --- interactive debugger (see docs/DEBUGGING.md) ---------------------------


class DebugSessionBody(BaseModel):
    device_id: str
    pid: int | None = None
    bundle_id: str | None = None
    breakpoints: list[str] = []
    debugserver_url: str | None = None


class BreakpointBody(BaseModel):
    spec: str


class StepBody(BaseModel):
    kind: str  # in | over | out


class EvalBody(BaseModel):
    expr: str
    frame_id: int | None = None


@router.post("/debug/sessions")
def debug_create(body: DebugSessionBody) -> dict:
    session, attach = debug_manager.create(
        device_id=body.device_id,
        pid=body.pid,
        bundle_id=body.bundle_id,
        breakpoints=body.breakpoints,
        debugserver_url=body.debugserver_url,
    )
    return {**session.info(), "attach": attach}


@router.get("/debug/sessions")
def debug_list() -> list[dict]:
    return debug_manager.list()


@router.get("/debug/sessions/{session_id}/state")
def debug_state(
    session_id: str, stack: bool = True, vars: bool = True, threads: bool = False
) -> dict:
    return debug_manager.get(session_id).state(stack=stack, variables=vars, threads=threads)


@router.post("/debug/sessions/{session_id}/breakpoints")
def debug_breakpoint_add(session_id: str, body: BreakpointBody) -> dict:
    return debug_manager.get(session_id).breakpoint_set(body.spec)


@router.get("/debug/sessions/{session_id}/breakpoints")
def debug_breakpoint_list(session_id: str) -> list[dict]:
    return debug_manager.get(session_id).breakpoint_list()


@router.delete("/debug/sessions/{session_id}/breakpoints/{bp_id}")
def debug_breakpoint_delete(session_id: str, bp_id: int) -> dict:
    return debug_manager.get(session_id).breakpoint_delete(bp_id)


@router.post("/debug/sessions/{session_id}/continue")
def debug_continue(session_id: str) -> dict:
    return debug_manager.get(session_id).cont()


@router.post("/debug/sessions/{session_id}/pause")
def debug_pause(session_id: str) -> dict:
    return debug_manager.get(session_id).pause()


@router.post("/debug/sessions/{session_id}/step")
def debug_step(session_id: str, body: StepBody) -> dict:
    return debug_manager.get(session_id).step(body.kind)


@router.post("/debug/sessions/{session_id}/eval")
def debug_eval(session_id: str, body: EvalBody) -> dict:
    return debug_manager.get(session_id).eval(body.expr, body.frame_id)


@router.get("/debug/sessions/{session_id}/output")
def debug_output(session_id: str) -> list[dict]:
    return debug_manager.get(session_id).output()


@router.delete("/debug/sessions/{session_id}")
def debug_detach(session_id: str, kill: bool = False) -> dict:
    return debug_manager.remove(session_id, kill=kill)


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


@router.get("/virtual-devices")
def list_virtual_devices() -> list[dict[str, str | None]]:
    return virtual.list_virtual_devices()


@router.post("/virtual-devices/launch")
def launch_virtual_device(body: VirtualDeviceBody) -> dict[str, bool | str]:
    return virtual.launch(body.name)


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

    @app.exception_handler(VirtualDeviceNotFound)
    async def _virtual_not_found(request: Request, exc: VirtualDeviceNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(DeviceError)
    async def _device_error(request: Request, exc: DeviceError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(SessionNotFound)
    async def _session_not_found(request: Request, exc: SessionNotFound) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(CapabilityError)
    async def _capability_error(request: Request, exc: CapabilityError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "error": "capability_missing",
                "commands": exc.commands,
            },
        )

    @app.exception_handler(DebugError)
    async def _debug_error(request: Request, exc: DebugError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(NotImplementedError)
    async def _not_implemented(request: Request, exc: NotImplementedError) -> JSONResponse:
        return JSONResponse(status_code=501, content={"detail": str(exc)})

    return app


app = create_app()


def serve(port: int = PORT) -> None:
    """Run the API server (blocking)."""
    import uvicorn

    uvicorn.run(app, host=HOST, port=port, log_level="info")
