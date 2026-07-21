"""HTTP + WebSocket API server (see docs/API.md)."""

import asyncio
import io
import tempfile
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from PIL import Image
from pydantic import BaseModel

from openmob import __version__
from openmob.debugger import CapabilityError, DebugError, DebugSessionManager, SessionNotFound
from openmob.device import Device, DeviceError
from openmob.manager import DeviceManager, DeviceNotFound

HOST = "127.0.0.1"
PORT = 8930

STREAM_FPS = 8
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
