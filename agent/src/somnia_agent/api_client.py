"""Typed calls to the somnia agent API, authenticated with the device token."""

import httpx
from pydantic import JsonValue

from somnia_agent.api_models import (
    CheckpointIn,
    ContextOut,
    InsertOut,
    SessionOut,
    StatusOut,
)
from somnia_agent.config import AgentConfig
from somnia_agent.spool import SpooledEvent


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
        self, repo: str, branch: str, token_budget: int, k: int, query: str | None
    ) -> ContextOut:
        params: dict[str, str | int] = {
            "repo": repo,
            "branch": branch,
            "token_budget": token_budget,
            "k": k,
        }
        if query:
            params["query"] = query
        response = self._http.get("/v1/context", params=params)
        response.raise_for_status()
        return ContextOut.model_validate(response.json())

    def verify(self) -> None:
        self._http.get("/v1/admin/repos").raise_for_status()
