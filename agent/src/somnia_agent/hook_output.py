"""What each harness expects on stdout from our hooks."""

import json

from somnia_agent.harness_payloads import Harness

_CONTEXT_EVENTS = frozenset({"SessionStart", "UserPromptSubmit"})
_CODEX_JSON_REQUIRED = frozenset({"Stop", "SubagentStop"})


def ingest_stdout(harness: Harness, event: str) -> str:
    """Codex rejects plain text from Stop hooks, so it gets an empty JSON object."""
    return "{}" if harness is Harness.CODEX and event in _CODEX_JSON_REQUIRED else ""


def context_stdout(harness: Harness, event: str, text: str | None) -> str:
    if text is None:
        return ingest_stdout(harness, event)
    if harness is Harness.GROK or event not in _CONTEXT_EVENTS:
        # Grok ignores stdout for passive events; printing is only useful for manual runs.
        return text
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}},
        ensure_ascii=False,
    )
