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


ProfileSection = Literal[
    "stack", "conventions", "architecture", "decisions", "open_work", "pitfalls"
]


class ReconcileDecision(BaseModel):
    """What to do with a candidate memory that is close to an existing one.

    add: unrelated, store it. merge: same fact, `content` is the combined wording.
    supersede: the candidate updates/contradicts the existing memory and replaces it.
    coexist: both hold, in different contexts; the candidate is stored with the narrower
    `narrowed_scope`. flag: a contradiction the model cannot settle; both are kept and a
    human resolves it.
    """

    action: Literal["add", "merge", "supersede", "coexist", "flag"]
    content: str = Field(min_length=1)
    narrowed_scope: MemoryScope | None = None
    rationale: str = ""


class ProfileItem(BaseModel):
    type: MemoryType
    content: str


class ProfileSections(BaseModel):
    sections: list[ProfileSection]


class Embedder(Protocol):
    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class Llm(Protocol):
    def summarize_session(self, transcript: str) -> SessionDigest: ...

    def reconcile(
        self, existing: str, candidate: str, candidate_scope: MemoryScope
    ) -> ReconcileDecision: ...

    def classify_profile(self, items: Sequence[ProfileItem]) -> list[ProfileSection]:
        """One project-profile section per item, same order."""
        ...
