"""Pipe Symphony lifecycle events into the Somnia agent's redacted local spool."""

import asyncio
import json
import subprocess
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import BoundedSemaphore

from core_harness import Tool
from core_harness.extensions import AddonEvent, CommandSpec, EventPayload, ExtensionAPI
from core_harness.timing import TERMINAL_RUN_EVENTS

_RESUME_TOOL = "somnia_resume"
_MAX_PENDING = 32
_dispose: Callable[[], None] | None = None


def setup(api: ExtensionAPI) -> None:
    global _dispose
    cwd = Path.cwd()
    runs: dict[str, dict[str, object]] = {}
    worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="somnia-ingest")
    pending = BoundedSemaphore(_MAX_PENDING)

    def record(run_id: str, event: str, **fields: object) -> None:
        # Symphony dispatches callbacks inline. Never wait for the CLI or backlog here.
        if not pending.acquire(blocking=False):
            return
        body = {"session_id": run_id, "cwd": str(cwd), "hook_event_name": event, **fields}
        try:
            job = worker.submit(_ingest, body)
        except RuntimeError:  # addon is shutting down
            pending.release()
        else:
            job.add_done_callback(lambda _: pending.release())

    def on_event(event: str, payload: EventPayload) -> None:
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            return
        if event == AddonEvent.RUN_STARTED:
            if payload.get("parent_id") is None and (prompt := payload.get("prompt")):
                runs[run_id] = {}
                record(run_id, "UserPromptSubmit", prompt=prompt)
            return

        arguments = runs.get(run_id)
        if arguments is None:
            return
        if event in TERMINAL_RUN_EVENTS:
            del runs[run_id]
            if output := payload.get("output_text"):
                record(run_id, "Stop", last_assistant_message=output)
            return

        tool_name = payload.get("tool_name")
        call_id = payload.get("tool_call_id")
        if not isinstance(tool_name, str) or tool_name == _RESUME_TOOL:
            return
        if not isinstance(call_id, str):
            return
        if event == AddonEvent.TOOL_EXECUTION_STARTED:
            arguments[call_id] = payload.get("arguments")
        elif event == AddonEvent.TOOL_EXECUTION_COMPLETED:
            record(
                run_id,
                "PostToolUse",
                tool_name=tool_name,
                tool_input=arguments.pop(call_id, None),
                tool_response=payload.get("result", ""),
                tool_failed=payload.get("status") != "success",
            )

    async def resume() -> str:
        """Read the last Somnia handoff for this git checkout and verify it before using it."""
        return await asyncio.to_thread(_resume, cwd)

    async def resume_command(_argument: str) -> str:
        return await resume()

    api.register_tool(Tool(resume, name=_RESUME_TOOL))
    api.register_command(
        CommandSpec("somnia-resume", "Show the last Somnia handoff", resume_command)
    )
    unsubscribe = [
        api.on(event, on_event)
        for event in (
            AddonEvent.RUN_STARTED,
            AddonEvent.TOOL_EXECUTION_STARTED,
            AddonEvent.TOOL_EXECUTION_COMPLETED,
            *sorted(TERMINAL_RUN_EVENTS),
        )
    ]

    def stop() -> None:
        for cancel in unsubscribe:
            cancel()
        runs.clear()
        worker.shutdown(wait=False)

    _dispose = stop


def dispose() -> None:
    global _dispose
    if _dispose is not None:
        _dispose()
        _dispose = None


def _ingest(body: dict[str, object]) -> None:
    try:
        subprocess.run(
            ["somnia-agent", "ingest", "--harness", "symphony"],
            input=json.dumps(body),
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, TypeError, ValueError):
        return


def _resume(cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["somnia-agent", "resume", "--cwd", str(cwd)],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "Somnia is unavailable. Check that somnia-agent is installed and reachable."
    return (result.stdout if result.returncode == 0 else result.stderr).strip()
