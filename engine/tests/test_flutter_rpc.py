"""Unit tests for the VM Service JSON-RPC plumbing over a mocked WebSocket."""

import asyncio
import json

import pytest

from openmob.device import DeviceError
from openmob.flutter import VmRpc, hot_reload_over_ws


class FakeVmServiceWs:
    """WS-like transport emulating a Dart VM service (send/recv of JSON-RPC strings)."""

    def __init__(self, isolates: list[dict], reload_success: bool = True) -> None:
        self.isolates = isolates
        self.reload_success = reload_success
        self.calls: list[tuple[str, dict]] = []
        self._replies: list[str] = []

    async def send(self, message: str) -> None:
        request = json.loads(message)
        self.calls.append((request["method"], request["params"]))
        # Interleave a streamNotify event to prove the client skips non-matching messages.
        self._replies.append(
            json.dumps({"jsonrpc": "2.0", "method": "streamNotify", "params": {"streamId": "GC"}})
        )
        self._replies.append(json.dumps(self._respond(request)))

    async def recv(self) -> str:
        return self._replies.pop(0)

    def _respond(self, request: dict) -> dict:
        reply = {"jsonrpc": "2.0", "id": request["id"]}
        if request["method"] == "getVM":
            reply["result"] = {"type": "VM", "isolates": self.isolates}
        elif request["method"] == "reloadSources":
            reply["result"] = {"type": "ReloadReport", "success": self.reload_success}
        else:
            reply["error"] = {"code": -32601, "message": "Method not found"}
        return reply


def test_rpc_call_skips_stream_events() -> None:
    ws = FakeVmServiceWs(isolates=[])
    result = asyncio.run(VmRpc(ws).call("getVM"))
    assert result["type"] == "VM"
    assert ws.calls == [("getVM", {})]


def test_rpc_error_raises_device_error() -> None:
    ws = FakeVmServiceWs(isolates=[])
    with pytest.raises(DeviceError, match="Method not found"):
        asyncio.run(VmRpc(ws).call("noSuchMethod"))


def test_hot_reload_reloads_each_isolate() -> None:
    ws = FakeVmServiceWs(
        isolates=[
            {"id": "isolates/1", "name": "main"},
            {"id": "isolates/2", "name": "worker"},
        ]
    )
    result = asyncio.run(hot_reload_over_ws(ws))
    assert result == {
        "success": True,
        "isolates": [
            {"isolate": "main", "success": True},
            {"isolate": "worker", "success": True},
        ],
    }
    assert ("reloadSources", {"isolateId": "isolates/1"}) in ws.calls
    assert ("reloadSources", {"isolateId": "isolates/2"}) in ws.calls


def test_hot_reload_reports_failure() -> None:
    ws = FakeVmServiceWs(isolates=[{"id": "isolates/1", "name": "main"}], reload_success=False)
    result = asyncio.run(hot_reload_over_ws(ws))
    assert result["success"] is False


def test_hot_reload_no_isolates() -> None:
    ws = FakeVmServiceWs(isolates=[])
    with pytest.raises(DeviceError, match="no isolates"):
        asyncio.run(hot_reload_over_ws(ws))
