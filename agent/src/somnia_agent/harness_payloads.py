"""Typed stdin payloads for each harness, normalised into one HookEvent.

Claude Code and Codex send snake_case fields; Grok Build sends camelCase.
Unknown fields are ignored so new harness versions do not break ingest.
"""

import json
import os
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class Harness(StrEnum):
    CLAUDE_CODE = "claude-code"
    CODEX = "codex"
    GROK = "grok"


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
        tool_failed=snake.hook_event_name == "PostToolUseFailure",
        prompt=snake.prompt,
        assistant_message=snake.last_assistant_message,
    )


def effective_harness(requested: Harness) -> Harness:
    """Grok Build also runs Claude Code plugin hooks, but sends its own camelCase payload."""
    return Harness.GROK if os.environ.get("GROK_HOOK_EVENT") else requested
