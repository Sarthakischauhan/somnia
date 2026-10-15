"""Request/response bodies that are specific to the HTTP layer."""

from typing import Literal

from pydantic import BaseModel, Field, JsonValue

from somnia.ingest.event_models import EventIn
from somnia.records import CheckpointRecord, SessionRecord, TaskRecord


class SessionCreate(BaseModel):
    repo: str = Field(min_length=1)
    branch: str = Field(min_length=1)
    git_ref: str | None = None


class EventBatch(BaseModel):
    events: list[EventIn] = Field(min_length=1, max_length=500)


class SessionStatus(BaseModel):
    session: SessionRecord
    latest_checkpoint: CheckpointRecord | None
    unprocessed_events: int


class TaskCompletion(BaseModel):
    status: Literal["done", "failed"]
    result: dict[str, JsonValue] | None = None


class TaskStatus(BaseModel):
    task: TaskRecord
    latest_checkpoint: CheckpointRecord | None
