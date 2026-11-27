"""Typed calls and models for the somnia agent API, authenticated with the device token.

The agent reads only a subset of API response fields; unknown fields are ignored.
"""

import httpx
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from somnia_agent.config import AgentConfig
from somnia_agent.spool import SpooledEvent


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
    """A retrieved item: a dreamt memory, or a not-yet-dreamt session chunk."""

    source: str = "memory"
    id: str
    type: str | None = None
    scope: str | None = None
    content: str
    confidence: float
    disputed: bool = False


class ProfileEntryOut(_Response):
    section: str
    content: str
    confidence: float
    disputed: bool = False


class ProfileOut(_Response):
    repo: str
    entries: list[ProfileEntryOut]


class OpenTaskOut(_Response):
    id: str
    title: str
    status: str


class ContextOut(_Response):
    profile: ProfileOut | None = None
    checkpoint: CheckpointOut | None
    open_tasks: list[OpenTaskOut] = Field(default_factory=list)
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


def make_http(config: AgentConfig, timeout_seconds: float) -> httpx.Client:
    return httpx.Client(
        base_url=config.api_url,
        headers={"Authorization": f"Bearer {config.token}"},
        timeout=timeout_seconds,
    )


class SomniaClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def create_session(self, repo: str, branch: str, git_ref: str | None) -> SessionOut:
        body = {"repo": repo, "branch": branch, "git_ref": git_ref}
        response = self._http.post("/v1/sessions", json=body)
        response.raise_for_status()
        return SessionOut.model_validate(response.json())

    def post_events(self, session_id: str, events: list[SpooledEvent]) -> InsertOut:
        body: dict[str, JsonValue] = {"events": [e.model_dump(mode="json") for e in events]}
        response = self._http.post(f"/v1/sessions/{session_id}/events", json=body)
        response.raise_for_status()
        return InsertOut.model_validate(response.json())

    def post_checkpoint(self, session_id: str, draft: CheckpointIn) -> None:
        response = self._http.post(
            f"/v1/sessions/{session_id}/checkpoints", json=draft.model_dump(mode="json")
        )
        response.raise_for_status()

    def close_session(self, session_id: str) -> None:
        self._http.post(f"/v1/sessions/{session_id}/close").raise_for_status()

    def session_status(self, session_id: str) -> StatusOut:
        response = self._http.get(f"/v1/sessions/{session_id}/status")
        response.raise_for_status()
        return StatusOut.model_validate(response.json())

    def context(
        self,
        repo: str,
        branch: str,
        token_budget: int,
        k: int,
        query: str | None,
        *,
        checkpoint_first: bool = False,
    ) -> ContextOut:
        params: dict[str, str | int] = {
            "repo": repo,
            "branch": branch,
            "token_budget": token_budget,
            "k": k,
        }
        if checkpoint_first:
            params["checkpoint_first"] = "true"
        if query:
            params["query"] = query
        response = self._http.get("/v1/context", params=params)
        response.raise_for_status()
        return ContextOut.model_validate(response.json())

    def verify(self) -> None:
        self._http.get("/v1/admin/repos").raise_for_status()
