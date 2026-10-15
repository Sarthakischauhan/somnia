"""Provider contracts. Anything satisfying these Protocols can back somnia."""

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, Field

MemoryType = Literal["fact", "decision", "convention", "gotcha", "todo"]
MemoryScope = Literal["global", "repo", "branch"]


class MemoryCandidate(BaseModel):
    type: MemoryType
    scope: MemoryScope
    content: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class SessionDigest(BaseModel):
    goal: str
    state: str
    next_steps: list[str] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    memories: list[MemoryCandidate] = Field(default_factory=list)


class MergeDecision(BaseModel):
    action: Literal["add", "merge", "supersede"]
    content: str = Field(min_length=1)


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class Llm(Protocol):
    def summarize_session(self, transcript: str) -> SessionDigest: ...

    def reconcile(self, existing: str, candidate: str) -> MergeDecision: ...
