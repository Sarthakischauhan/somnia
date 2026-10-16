"""The subset of somnia API responses the agent reads. Unknown fields are ignored."""

from pydantic import BaseModel, ConfigDict, Field


class _Response(BaseModel):
    model_config = ConfigDict(extra="ignore")


class SessionOut(_Response):
    id: str
    repo: str
    branch: str
    status: str


class CheckpointOut(_Response):
    goal: str
    state: str
    next_steps: list[str] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    git_ref: str | None = None
    pushed: bool = False
    branch: str
    created_at: str


class MemoryOut(_Response):
    id: str
    type: str
    scope: str
    content: str
    confidence: float


class ContextOut(_Response):
    checkpoint: CheckpointOut | None
    memories: list[MemoryOut]
    token_budget: int
    tokens_used: int
    dropped: int


class InsertOut(_Response):
    accepted: int
    duplicates: int


class StatusOut(_Response):
    session: SessionOut
    latest_checkpoint: CheckpointOut | None
    unprocessed_events: int


class CheckpointIn(BaseModel):
    goal: str = Field(min_length=1)
    state: str = Field(min_length=1)
    next_steps: list[str] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    git_ref: str | None = None
    pushed: bool = False
