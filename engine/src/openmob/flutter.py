"""Flutter debugging helpers: Dart VM Service discovery and hot reload.

A Flutter app built in debug mode logs a line like

    I flutter : The Dart VM service is listening on http://127.0.0.1:39215/0FIADRh0zas=/

on startup. On Android we find that line in logcat, `adb forward` a local port to the
device port, and hand back a URL that works from the host. Hot reload speaks the VM
Service JSON-RPC protocol over the service's WebSocket endpoint (`<url>ws`).
"""

import asyncio
import json
import re
from urllib.parse import urlsplit

from openmob.android import AndroidDevice
from openmob.device import Device, DeviceError

VM_SERVICE_RE = re.compile(r"The Dart VM service is listening on (http://[^\s]+)")

DEVTOOLS_HINT = (
    "Open the URL in Dart DevTools: run `dart devtools` and paste the URL, "
    "or use `dart devtools --machine` from tooling."
)

RPC_TIMEOUT = 10.0


def parse_vm_service_url(logcat_text: str) -> str | None:
    """Return the most recent Dart VM service URL mentioned in logcat output."""
    matches = VM_SERVICE_RE.findall(logcat_text)
    return matches[-1] if matches else None


def ws_endpoint(http_url: str) -> str:
    """Map the VM service HTTP URL to its WebSocket endpoint (…/TOKEN=/ -> ws://…/TOKEN=/ws)."""
    base = http_url if http_url.endswith("/") else http_url + "/"
    return "ws" + base.removeprefix("http") + "ws"


def _require_android(device: Device) -> AndroidDevice:
    if not isinstance(device, AndroidDevice):
        raise DeviceError(
            "Flutter VM service detection currently supports Android only; on iOS run "
            "`flutter attach` or read the URL from Xcode/console logs manually"
        )
    return device


def vm_service(device: Device) -> dict[str, str]:
    """Detect a running debug Flutter app's VM service and forward it to the host."""
    android = _require_android(device)
    url = parse_vm_service_url(
        android.logs(lines=1000, filter_str="The Dart VM service is listening")
    )
    if url is None:
        raise DeviceError(
            "no Dart VM service found in logcat — is a Flutter app running in debug mode?"
        )
    parts = urlsplit(url)
    if parts.port is None:
        raise DeviceError(f"could not parse VM service URL: {url!r}")
    local_port = android.forward_tcp(parts.port)
    local_url = f"http://127.0.0.1:{local_port}{parts.path}"
    return {"url": local_url, "device_url": url, "devtools_hint": DEVTOOLS_HINT}


class VmRpc:
    """Minimal JSON-RPC 2.0 client over a VM Service WebSocket-like object.

    The transport only needs async `send(str)` and `recv() -> str` methods, which keeps
    the plumbing unit-testable without a real socket.
    """

    def __init__(self, ws) -> None:
        self._ws = ws
        self._next_id = 0

    async def call(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        request_id = str(self._next_id)
        await self._ws.send(
            json.dumps(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}
            )
        )
        while True:  # skip streamNotify events and unrelated messages
            message = json.loads(await self._ws.recv())
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise DeviceError(f"VM service {method} failed: {error.get('message', error)}")
            result = message.get("result")
            if not isinstance(result, dict):
                raise DeviceError(f"VM service {method} returned no result")
            return result


async def hot_reload_over_ws(ws) -> dict[str, object]:
    """Run reloadSources for every isolate reachable over the given WS transport."""
    rpc = VmRpc(ws)
    vm = await rpc.call("getVM")
    isolates = [ref for ref in vm.get("isolates", []) if isinstance(ref, dict) and "id" in ref]
    if not isolates:
        raise DeviceError("VM service reports no isolates to reload")
    reports = []
    for ref in isolates:
        report = await rpc.call("reloadSources", {"isolateId": ref["id"]})
        entry: dict[str, object] = {
            "isolate": ref.get("name", ref["id"]),
            "success": bool(report.get("success")),
        }
        # Surface the VM's reason on failure (e.g. no kernel compiler when the app was
        # launched from an installed APK instead of `flutter run`).
        notices = [
            notice["message"]
            for notice in report.get("notices", [])
            if isinstance(notice, dict) and notice.get("message")
        ]
        if notices and not entry["success"]:
            entry["reason"] = "; ".join(notices)
        reports.append(entry)
    return {
        "success": all(report["success"] for report in reports),
        "isolates": reports,
    }


def hot_reload(device: Device) -> dict[str, object]:
    """Detect the VM service on `device` and hot-reload the running Flutter app."""
    service = vm_service(device)

    async def run() -> dict[str, object]:
        import websockets

        try:
            async with websockets.connect(ws_endpoint(service["url"])) as ws:
                return await asyncio.wait_for(hot_reload_over_ws(ws), timeout=RPC_TIMEOUT)
        except (OSError, asyncio.TimeoutError) as exc:
            raise DeviceError(f"could not talk to the VM service: {exc}") from exc

    result = asyncio.run(run())
    result["vm_service_url"] = service["url"]
    return result
