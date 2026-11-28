"""Normalise harness hook payloads and map them to redacted Somnia event bodies.

Claude Code and Codex send snake_case fields; Grok Build sends camelCase.
Unknown fields are ignored so new harness versions do not break ingest.
"""

import json
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from somnia_agent.redaction import redact_json, redact_text

MAX_TOOL_OUTPUT_CHARS = 8000
EventKind = Literal["message", "tool_call", "files_touched", "git_ref"]
_PATH_KEYS = ("file_path", "path", "notebook_path", "target_file")


class Harness(StrEnum):
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"
    GROK = "grok"
    SYMPHONY = "symphony"


class HookEvent(BaseModel):
    harness: Harness
    event: str
    session_id: str = Field(min_length=1)
    cwd: str | None = None
    tool_name: str | None = None
    tool_input: JsonValue = None
    tool_output: JsonValue = None
    tool_failed: bool = False
    prompt: str | None = None
    assistant_message: str | None = None


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class SnakeCasePayload(_Lenient):
    """Claude Code (code.claude.com/docs/en/hooks) and Codex (developers.openai.com/codex/hooks)."""

    session_id: str
    hook_event_name: str
    cwd: str | None = None
    tool_name: str | None = None
    tool_input: JsonValue = None
    tool_response: JsonValue = None
    prompt: str | None = None
    last_assistant_message: str | None = None
    tool_failed: bool = False


class GrokPayload(_Lenient):
    """Grok Build (docs.x.ai/build/features/hooks)."""

    session_id: str = Field(alias="sessionId")
    hook_event_name: str = Field(alias="hookEventName")
    cwd: str | None = None
    workspace_root: str | None = Field(default=None, alias="workspaceRoot")
    tool_name: str | None = Field(default=None, alias="toolName")
    tool_input: JsonValue = Field(default=None, alias="toolInput")
    tool_response: JsonValue = Field(default=None, alias="toolResponse")
    tool_output: JsonValue = Field(default=None, alias="toolOutput")
    prompt: str | None = None
    last_assistant_message: str | None = Field(default=None, alias="lastAssistantMessage")


def parse_hook(harness: Harness, raw: bytes) -> HookEvent:
    data = json.loads(raw)
    if harness is Harness.GROK:
        grok = GrokPayload.model_validate(data)
        return HookEvent(
            harness=harness,
            event=grok.hook_event_name,
            session_id=grok.session_id,
            cwd=grok.workspace_root or grok.cwd,
            tool_name=grok.tool_name,
            tool_input=grok.tool_input,
            tool_output=grok.tool_response if grok.tool_response is not None else grok.tool_output,
            tool_failed=grok.hook_event_name == "PostToolUseFailure",
            prompt=grok.prompt,
            assistant_message=grok.last_assistant_message,
        )
    snake = SnakeCasePayload.model_validate(data)
    return HookEvent(
        harness=harness,
        event=snake.hook_event_name,
        session_id=snake.session_id,
        cwd=snake.cwd,
        tool_name=snake.tool_name,
        tool_input=snake.tool_input,
        tool_output=snake.tool_response,
        tool_failed=snake.tool_failed or snake.hook_event_name == "PostToolUseFailure",
        prompt=snake.prompt,
        assistant_message=snake.last_assistant_message,
    )


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
