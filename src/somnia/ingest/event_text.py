"""Render a typed event as one line of transcript text."""

import json
from typing import assert_never

from somnia.ingest.event_models import (
    EventIn,
    FilesTouchedEvent,
    GitRefEvent,
    MessageEvent,
    ToolCallEvent,
)


def render_event(event: EventIn) -> str:
    match event:
        case MessageEvent(payload=p):
            return f"[message:{p.role}] {p.content}"
        case ToolCallEvent(payload=p):
            status = "error" if p.is_error else "ok"
            args = json.dumps(p.input, sort_keys=True)
            output = f" -> {p.output}" if p.output else ""
            return f"[tool_call:{p.name}:{status}] {args}{output}"
        case FilesTouchedEvent(payload=p):
            return f"[files_touched:{p.action}] {', '.join(p.paths)}"
        case GitRefEvent(payload=p):
            return f"[git_ref] {p.ref}{' (pushed)' if p.pushed else ''}"
        case _:
            assert_never(event)
