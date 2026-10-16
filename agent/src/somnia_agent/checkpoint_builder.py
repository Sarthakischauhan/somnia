"""Deterministic checkpoint draft from what the spool already holds (no LLM on the client)."""

from somnia_agent.api_models import CheckpointIn
from somnia_agent.spool import SpooledEvent

GOAL_CHARS = 500
STATE_CHARS = 2000
MAX_FILES = 50


def _message(event: SpooledEvent, role: str) -> str | None:
    if event.kind != "message" or event.payload.get("role") != role:
        return None
    content = event.payload.get("content")
    return content if isinstance(content, str) and content.strip() else None


def build_checkpoint(
    events: list[SpooledEvent], reason: str, repo: str, git_ref: str | None
) -> CheckpointIn:
    user_messages = [m for e in events if (m := _message(e, "user"))]
    assistant_messages = [m for e in events if (m := _message(e, "assistant"))]
    files: list[str] = []
    for event in events:
        paths = event.payload.get("paths") if event.kind == "files_touched" else None
        if isinstance(paths, list):
            files.extend(p for p in paths if isinstance(p, str) and p not in files)
    goal = user_messages[0] if user_messages else f"Continue work in {repo}"
    state = assistant_messages[-1] if assistant_messages else f"Session checkpointed ({reason})."
    next_steps = [f"Latest request: {user_messages[-1][:GOAL_CHARS]}"] if user_messages else []
    return CheckpointIn(
        goal=goal[:GOAL_CHARS],
        state=state[:STATE_CHARS],
        next_steps=next_steps,
        files_touched=files[-MAX_FILES:],
        git_ref=git_ref,
    )
