"""Row models shared by the store layer and API responses."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, JsonValue


class SessionRecord(BaseModel):
    id: UUID
    device_id: UUID
    repo: str
    branch: str
    git_ref: str | None
    status: Literal["open", "closed"]
    started_at: datetime
    last_event_at: datetime | None
    ended_at: datetime | None


class CheckpointRecord(BaseModel):
    id: UUID
    session_id: UUID | None
    repo: str
    branch: str
    goal: str
    state: str
    next_steps: list[str]
    files_touched: list[str]
    git_ref: str | None
    pushed: bool
    status: Literal["open", "closed"]
    source: Literal["agent", "dream"]
    created_at: datetime


class TaskRecord(BaseModel):
    id: UUID
    session_id: UUID | None
    repo: str | None
    branch: str | None
    title: str
    payload: dict[str, JsonValue]
    status: Literal["queued", "running", "done", "failed"]
    priority: int
    attempts: int
    claimed_by_device: UUID | None
    locked_until: datetime | None
    result: dict[str, JsonValue] | None
    created_at: datetime
    updated_at: datetime
