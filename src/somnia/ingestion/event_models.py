"""Typed event bodies agents post. `kind` discriminates the payload shape."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, TypeAdapter


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MessagePayload(_Strict):
    role: Literal["user", "assistant", "system", "tool"]
    content: str


class ToolCallPayload(_Strict):
    name: str
    input: dict[str, JsonValue] = Field(default_factory=dict)
    output: str | None = None
    is_error: bool = False


class FilesTouchedPayload(_Strict):
    paths: list[str] = Field(min_length=1)
    action: Literal["read", "write", "delete"] = "write"


class GitRefPayload(_Strict):
    ref: str = Field(min_length=1)
    pushed: bool = False


class MessageEvent(_Strict):
    seq: int = Field(gt=0)
    kind: Literal["message"]
    payload: MessagePayload


class ToolCallEvent(_Strict):
    seq: int = Field(gt=0)
    kind: Literal["tool_call"]
    payload: ToolCallPayload


class FilesTouchedEvent(_Strict):
    seq: int = Field(gt=0)
    kind: Literal["files_touched"]
    payload: FilesTouchedPayload


class GitRefEvent(_Strict):
    seq: int = Field(gt=0)
    kind: Literal["git_ref"]
    payload: GitRefPayload


EventIn = Annotated[
    MessageEvent | ToolCallEvent | FilesTouchedEvent | GitRefEvent,
    Field(discriminator="kind"),
]
EVENT_ADAPTER: TypeAdapter[EventIn] = TypeAdapter(EventIn)
