"""Turn a normalised hook into somnia event bodies (kind + payload), already redacted."""

import json
from typing import Literal

from pydantic import BaseModel, JsonValue

from somnia_agent.harness_payloads import HookEvent
from somnia_agent.redaction import redact_json, redact_text

MAX_TOOL_OUTPUT_CHARS = 8000
EventKind = Literal["message", "tool_call", "files_touched", "git_ref"]
_PATH_KEYS = ("file_path", "path", "notebook_path")


class EventBody(BaseModel):
    kind: EventKind
    payload: dict[str, JsonValue]


def _output_text(output: JsonValue) -> str | None:
    if output is None:
        return None
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    return text[:MAX_TOOL_OUTPUT_CHARS]


def _input_object(tool_input: JsonValue) -> dict[str, JsonValue]:
    if isinstance(tool_input, dict):
        return tool_input
    if tool_input is None:
        return {}
    return {"value": tool_input}


def touched_paths(tool_input: dict[str, JsonValue]) -> list[str]:
    return [v for k in _PATH_KEYS if isinstance(v := tool_input.get(k), str) and v]


def hook_to_events(hook: HookEvent) -> list[EventBody]:
    if hook.tool_name is not None and hook.event in {"PostToolUse", "PostToolUseFailure"}:
        tool_input = _input_object(hook.tool_input)
        redacted_input = {key: redact_json(value, key) for key, value in tool_input.items()}
        output = _output_text(hook.tool_output)
        events = [
            EventBody(
                kind="tool_call",
                payload={
                    "name": hook.tool_name,
                    "input": redacted_input,
                    "output": None if output is None else redact_text(output),
                    "is_error": hook.tool_failed,
                },
            )
        ]
        paths = touched_paths(tool_input)
        if paths:
            events.append(
                EventBody(kind="files_touched", payload={"paths": list(paths), "action": "write"})
            )
        return events
    if hook.prompt:
        return [
            EventBody(kind="message", payload={"role": "user", "content": redact_text(hook.prompt)})
        ]
    if hook.assistant_message:
        content = redact_text(hook.assistant_message)
        return [EventBody(kind="message", payload={"role": "assistant", "content": content})]
    return []
