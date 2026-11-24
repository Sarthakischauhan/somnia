"""Pipe Symphony lifecycle events into the Somnia agent's redacted local spool."""

import asyncio
import json
import subprocess
from pathlib import Path

from core_harness import Tool
from core_harness.extensions import CommandSpec


def setup(api):
    cwd = Path.cwd()
    runs = set()
    arguments = {}

    def record(event, payload, **fields):
        body = {
            "session_id": payload["run_id"],
            "cwd": str(cwd),
            "hook_event_name": event,
            **fields,
        }
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
        except (OSError, subprocess.TimeoutExpired):
            return

    def start(_event, payload):
        if payload.get("parent_id") is None and payload.get("prompt"):
            runs.add(payload["run_id"])
            record("UserPromptSubmit", payload, prompt=payload["prompt"])

    def tool_start(_event, payload):
        if payload.get("run_id") in runs and payload.get("tool_name") != "somnia_resume":
            arguments[(payload["run_id"], payload["tool_call_id"])] = payload.get("arguments")

    def tool_done(_event, payload):
        if payload.get("run_id") not in runs or payload.get("tool_name") == "somnia_resume":
            return
        key = (payload["run_id"], payload["tool_call_id"])
        record(
            "PostToolUse",
            payload,
            tool_name=payload["tool_name"],
            tool_input=arguments.pop(key, None),
            tool_response=payload.get("result", "")[:8000],
            tool_failed=payload.get("status") != "success",
        )

    def end(_event, payload):
        run_id = payload.get("run_id")
        if run_id not in runs:
            return
        runs.remove(run_id)
        for key in [key for key in arguments if key[0] == run_id]:
            arguments.pop(key)
        if output := payload.get("output_text"):
            record("Stop", payload, last_assistant_message=output)

    async def resume() -> str:
        """Read the last Somnia handoff for this git checkout and verify it before using it."""
        return await asyncio.to_thread(_resume, cwd)

    async def resume_command(argument: str) -> str:
        return await resume()

    api.register_tool(Tool(resume, name="somnia_resume"))
    api.register_command(
        CommandSpec("somnia-resume", "Show the last Somnia handoff", resume_command)
    )
    api.on("run_started", start)
    api.on("tool_execution_started", tool_start)
    api.on("tool_execution_completed", tool_done)
    api.on("run_completed", end)
    api.on("run_cancelled", end)
    api.on("run_failed", end)
    api.on("run_limit_exceeded", end)


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
