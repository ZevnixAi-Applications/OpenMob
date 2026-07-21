"""Standalone lldb worker: JSON-lines over stdio, run under Xcode's python3.

Why a subprocess: Xcode ships lldb's Python module built for its own CPython
(currently 3.9), so it cannot be imported into the engine's uv-managed 3.12
interpreter. The engine (openmob/debugger.py) spawns this script with
`xcrun python3 lldb_worker.py --lldb-python-path "$(xcrun lldb -P)"` and talks
a simple protocol:

    -> {"id": 1, "cmd": "attach", "pid": 123}
    <- {"id": 1, "ok": true, "result": {"state": "stopped", ...}}
    <- {"id": 2, "ok": false, "error": "..."}

This file must stay dependency-free and Python 3.9 compatible (stdlib only,
`import lldb` deferred to runtime) so the engine's test suite can import its
pure helpers without lldb installed.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import time

_FILE_LINE_RE = re.compile(r"^(.+):(\d+)$")

# Reasonable ceilings so `state` responses stay small enough for an LLM context.
MAX_FRAMES = 20
MAX_VARS = 30
MAX_CHILDREN = 10
VAR_DEPTH = 2
STEP_TIMEOUT = 15.0
ATTACH_TIMEOUT = 30.0
EVAL_TIMEOUT_US = 15_000_000
OUTPUT_RING_CHUNKS = 256


def classify_spec(spec):
    """Split a breakpoint spec into ("file", path, line) or ("symbol", name, None).

    "File.swift:42" -> file:line; anything else ("-[Class method:]",
    "Module.Type.method", "viewDidAppear") is a symbol/name breakpoint.
    """
    match = _FILE_LINE_RE.match(spec)
    if match and "." in os.path.basename(match.group(1)):
        return ("file", match.group(1), int(match.group(2)))
    return ("symbol", spec, None)


class WorkerError(Exception):
    """Command failed; message is sent back verbatim."""


class LldbWorker:
    """Owns one SBDebugger/SBTarget/SBProcess; one command at a time."""

    def __init__(self, lldb_module):
        self.lldb = lldb_module
        self.lldb.SBDebugger.Initialize()
        self.debugger = self.lldb.SBDebugger.Create()
        self.debugger.SetAsync(True)
        self.listener = self.debugger.GetListener()
        self.target = None
        self.process = None
        self.specs = {}  # breakpoint id -> original spec string
        self.output = collections.deque(maxlen=OUTPUT_RING_CHUNKS)

    # --- event plumbing ----------------------------------------------------

    def drain_events(self):
        """Consume pending lldb events (state changes, stdout/stderr bits)."""
        event = self.lldb.SBEvent()
        while self.listener.GetNextEvent(event):
            self._pump_output()
            event = self.lldb.SBEvent()

    def _pump_output(self):
        if self.process is None:
            return
        while True:
            chunk = self.process.GetSTDOUT(4096)
            if not chunk:
                break
            self.output.append(("stdout", chunk))
        while True:
            chunk = self.process.GetSTDERR(4096)
            if not chunk:
                break
            self.output.append(("stderr", chunk))

    def state_name(self):
        self.drain_events()
        if self.process is None or not self.process.IsValid():
            return "detached"
        return self.lldb.SBDebugger.StateAsCString(self.process.GetState())

    def wait_for_state(self, wanted, timeout):
        """Poll (draining events) until the process reaches one of `wanted`."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.state_name()
            if state in wanted:
                return state
            event = self.lldb.SBEvent()
            self.listener.WaitForEvent(1, event)
            self._pump_output()
        return self.state_name()

    def require_process(self):
        if self.process is None or not self.process.IsValid():
            raise WorkerError("no process attached")
        return self.process

    def require_stopped(self):
        process = self.require_process()
        state = self.state_name()
        if state != "stopped":
            raise WorkerError(
                "process is %s, not stopped — pause it or wait for a breakpoint" % state
            )
        return process

    # --- commands ----------------------------------------------------------

    def cmd_ping(self, req):
        return {"pong": True, "lldb": self.debugger.GetVersionString()}

    def cmd_attach(self, req):
        if self.process is not None and self.process.IsValid():
            raise WorkerError("already attached")
        pid = int(req["pid"])
        self.target = self.debugger.CreateTarget("")
        error = self.lldb.SBError()
        self.process = self.target.AttachToProcessWithID(self.listener, pid, error)
        if error.Fail() or not self.process or not self.process.IsValid():
            message = error.GetCString() or "unknown attach failure"
            self.process = None
            raise WorkerError("attach to pid %d failed: %s" % (pid, message))
        state = self.wait_for_state({"stopped"}, ATTACH_TIMEOUT)
        executable = self.target.GetExecutable()
        return {
            "pid": self.process.GetProcessID(),
            "state": state,
            "executable": executable.GetFilename() if executable else None,
        }

    def cmd_connect(self, req):
        """Real-device path: connect to a remote debugserver, then attach by pid."""
        if self.process is not None and self.process.IsValid():
            raise WorkerError("already attached")
        url = req["url"]  # e.g. connect://[fd12::1]:1234
        self.debugger.SetCurrentPlatform("remote-ios")
        self.target = self.debugger.CreateTarget("")
        error = self.lldb.SBError()
        self.process = self.target.ConnectRemote(self.listener, url, "gdb-remote", error)
        if error.Fail() or not self.process or not self.process.IsValid():
            message = error.GetCString() or "unknown connect failure"
            self.process = None
            raise WorkerError("connect to %s failed: %s" % (url, message))
        state = self.wait_for_state({"stopped"}, ATTACH_TIMEOUT)
        return {"pid": self.process.GetProcessID(), "state": state}

    def cmd_bp_set(self, req):
        if self.target is None:
            raise WorkerError("no target — attach first")
        spec = req["spec"]
        kind, arg, line = classify_spec(spec)
        if kind == "file":
            bp = self.target.BreakpointCreateByLocation(arg, line)
        else:
            bp = self.target.BreakpointCreateByName(arg)
        if not bp.IsValid():
            raise WorkerError("could not create breakpoint for %r" % spec)
        self.specs[bp.GetID()] = spec
        return self._bp_info(bp)

    def cmd_bp_list(self, req):
        if self.target is None:
            raise WorkerError("no target — attach first")
        return {
            "breakpoints": [
                self._bp_info(self.target.GetBreakpointAtIndex(i))
                for i in range(self.target.GetNumBreakpoints())
            ]
        }

    def cmd_bp_delete(self, req):
        if self.target is None:
            raise WorkerError("no target — attach first")
        bp_id = int(req["bp_id"])
        if not self.target.BreakpointDelete(bp_id):
            raise WorkerError("no breakpoint with id %d" % bp_id)
        self.specs.pop(bp_id, None)
        return {"deleted": bp_id}

    def _bp_info(self, bp):
        return {
            "id": bp.GetID(),
            "spec": self.specs.get(bp.GetID(), ""),
            "locations": bp.GetNumLocations(),
            "resolved": bp.GetNumResolvedLocations() > 0,
            "hit_count": bp.GetHitCount(),
            "enabled": bp.IsEnabled(),
        }

    def cmd_continue(self, req):
        process = self.require_process()
        if self.state_name() == "running":
            raise WorkerError("process is already running")
        error = process.Continue()
        if error.Fail():
            raise WorkerError("continue failed: %s" % error.GetCString())
        # Fire-and-forget: give it a beat, report whatever state it is in now.
        state = self.wait_for_state({"running", "stopped", "exited"}, 1.0)
        return {"state": state}

    def cmd_pause(self, req):
        process = self.require_process()
        if self.state_name() == "stopped":
            return {"state": "stopped"}
        error = process.Stop()
        if error.Fail():
            raise WorkerError("pause failed: %s" % error.GetCString())
        state = self.wait_for_state({"stopped"}, 10.0)
        if state != "stopped":
            raise WorkerError("process did not stop (state: %s)" % state)
        return {"state": state}

    def cmd_step(self, req):
        process = self.require_stopped()
        kind = req["kind"]
        thread = process.GetSelectedThread()
        if not thread.IsValid():
            raise WorkerError("no selected thread")
        if kind == "in":
            thread.StepInto()
        elif kind == "over":
            thread.StepOver()
        elif kind == "out":
            thread.StepOut()
        else:
            raise WorkerError("unknown step kind %r (expected in/over/out)" % kind)
        state = self.wait_for_state({"stopped", "exited"}, STEP_TIMEOUT)
        if state != "stopped":
            raise WorkerError("step did not stop (state: %s)" % state)
        return {"state": state, "frame": self._frame_info(thread.GetFrameAtIndex(0))}

    def cmd_eval(self, req):
        process = self.require_stopped()
        thread = process.GetSelectedThread()
        frame_id = int(req.get("frame_id") or 0)
        frame = thread.GetFrameAtIndex(frame_id)
        if not frame.IsValid():
            raise WorkerError("no frame %d on the selected thread" % frame_id)
        options = self.lldb.SBExpressionOptions()
        options.SetIgnoreBreakpoints(True)
        options.SetTimeoutInMicroSeconds(EVAL_TIMEOUT_US)
        value = frame.EvaluateExpression(req["expr"], options)
        error = value.GetError()
        if error.Fail() and value.GetValue() is None and value.GetSummary() is None:
            raise WorkerError("expression failed: %s" % (error.GetCString() or "unknown"))
        return {
            "value": value.GetValue(),
            "summary": value.GetSummary(),
            "type": value.GetTypeName(),
            "description": value.GetObjectDescription(),
        }

    def cmd_state(self, req):
        include_stack = req.get("stack", True)
        include_vars = req.get("vars", True)
        include_threads = req.get("threads", False)
        state = self.state_name()
        result = {"state": state}
        if self.process is not None and self.process.IsValid():
            result["pid"] = self.process.GetProcessID()
        if self.target is not None:
            result["breakpoints"] = self.cmd_bp_list({})["breakpoints"]
        if state != "stopped":
            return result
        thread = self.process.GetSelectedThread()
        result["stop_reason"] = self._stop_reason(thread)
        if include_threads:
            result["threads"] = [
                {
                    "id": t.GetThreadID(),
                    "index": t.GetIndexID(),
                    "name": t.GetName(),
                    "queue": t.GetQueueName(),
                    "stop_reason": self._stop_reason(t),
                    "frame0": self._frame_info(t.GetFrameAtIndex(0)),
                }
                for t in self.process
            ]
        if include_stack:
            result["stack"] = [
                self._frame_info(thread.GetFrameAtIndex(i))
                for i in range(min(thread.GetNumFrames(), MAX_FRAMES))
            ]
        if include_vars:
            frame = thread.GetFrameAtIndex(0)
            variables = frame.GetVariables(True, True, False, True)  # args, locals, in-scope
            result["locals"] = [
                self._render_value(variables.GetValueAtIndex(i), VAR_DEPTH)
                for i in range(min(variables.GetSize(), MAX_VARS))
            ]
        return result

    def cmd_output(self, req):
        self.drain_events()
        return {"chunks": [{"stream": stream, "text": text} for stream, text in self.output]}

    def cmd_detach(self, req):
        process = self.require_process()
        kill = bool(req.get("kill", False))
        error = process.Kill() if kill else process.Detach()
        if error.Fail():
            raise WorkerError("detach failed: %s" % error.GetCString())
        self.process = None
        self.target = None
        self.specs.clear()
        return {"detached": True, "killed": kill}

    # --- rendering ---------------------------------------------------------

    def _stop_reason(self, thread):
        reasons = {
            self.lldb.eStopReasonNone: "none",
            self.lldb.eStopReasonTrace: "trace",
            self.lldb.eStopReasonBreakpoint: "breakpoint",
            self.lldb.eStopReasonWatchpoint: "watchpoint",
            self.lldb.eStopReasonSignal: "signal",
            self.lldb.eStopReasonException: "exception",
            self.lldb.eStopReasonExec: "exec",
            self.lldb.eStopReasonPlanComplete: "plan_complete",
        }
        return reasons.get(thread.GetStopReason(), "other")

    def _frame_info(self, frame):
        if frame is None or not frame.IsValid():
            return None
        line_entry = frame.GetLineEntry()
        file_spec = line_entry.GetFileSpec() if line_entry.IsValid() else None
        module = frame.GetModule()
        module_spec = module.GetFileSpec() if module.IsValid() else None
        return {
            "index": frame.GetFrameID(),
            "function": frame.GetFunctionName(),
            "module": module_spec.GetFilename() if module_spec else None,
            "file": file_spec.GetFilename() if file_spec else None,
            "line": line_entry.GetLine() if line_entry.IsValid() else None,
            "pc": "0x%x" % frame.GetPC(),
        }

    def _render_value(self, value, depth):
        info = {
            "name": value.GetName(),
            "type": value.GetTypeName(),
            "value": value.GetValue(),
            "summary": value.GetSummary(),
        }
        num_children = value.GetNumChildren()
        if depth > 0 and num_children > 0:
            info["children"] = [
                self._render_value(value.GetChildAtIndex(i), depth - 1)
                for i in range(min(num_children, MAX_CHILDREN))
            ]
            if num_children > MAX_CHILDREN:
                info["children_truncated"] = num_children
        return info

    # --- dispatch ----------------------------------------------------------

    def handle(self, request):
        cmd = request.get("cmd")
        handler = getattr(self, "cmd_%s" % cmd, None)
        if handler is None:
            raise WorkerError("unknown command %r" % cmd)
        return handler(request)


def serve(lldb_module, stdin=None, stdout=None):
    """Blocking JSON-lines loop; one request, one response, in order."""
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    worker = LldbWorker(lldb_module)
    for line in stdin:
        line = line.strip()
        if not line:
            continue
        request_id = None
        try:
            request = json.loads(line)
            request_id = request.get("id")
            result = worker.handle(request)
            response = {"id": request_id, "ok": True, "result": result}
        except WorkerError as exc:
            response = {"id": request_id, "ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 — worker must never die mid-protocol
            response = {
                "id": request_id,
                "ok": False,
                "error": "%s: %s" % (type(exc).__name__, exc),
            }
        stdout.write(json.dumps(response) + "\n")
        stdout.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lldb-python-path", required=True, help="output of `xcrun lldb -P`")
    args = parser.parse_args()
    sys.path.insert(0, args.lldb_python_path)
    import lldb  # noqa: PLC0415 — only importable under Xcode's python3

    serve(lldb)


if __name__ == "__main__":
    main()
