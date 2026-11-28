"""HarnessLlm drives a real CoreHarness run against a scripted core_ai provider."""

from collections.abc import AsyncGenerator
from typing import Any

import pytest
from core_ai import BaseProvider, Message, ModelRegistry, StreamEvent

from somnia.providers.protocols import ProfileItem
from somnia.providers.symphony_harness import HarnessLlm


class _ScriptedProvider(BaseProvider):
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.seen: list[list[Message]] = []

    async def stream(  # type: ignore[override]
        self,
        model_name: str,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
        **_: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        self.seen.append(list(messages))
        yield StreamEvent(type="text_start")
        yield StreamEvent(type="text_delta", delta=self.reply)
        yield StreamEvent(type="done")


def _llm(reply: str) -> tuple[HarnessLlm, _ScriptedProvider]:
    provider = _ScriptedProvider(reply)
    registry = ModelRegistry()  # type: ignore[no-untyped-call]
    registry.register("scripted", provider)
    return HarnessLlm(registry, "scripted:test", timeout_s=30), provider


def test_summarize_parses_fenced_json() -> None:
    llm, provider = _llm(
        '```json\n{"goal": "ship", "state": "done", "memories": '
        '[{"type": "fact", "scope": "repo", "content": "uses uv", "confidence": 0.9}]}\n```'
    )
    digest = llm.summarize_session("[message:user] ship it")
    assert digest.goal == "ship"
    assert digest.memories[0].content == "uses uv"
    system, user = provider.seen[0][0], provider.seen[0][-1]
    assert system.role == "system"
    assert "consolidate a coding-agent session" in str(system.content)
    assert "ship it" in str(user.content)


def test_reconcile_and_classify() -> None:
    llm, _ = _llm('{"action": "merge", "content": "combined"}')
    assert llm.reconcile("a", "b", "repo").action == "merge"

    llm, _ = _llm('{"sections": ["stack", "pitfalls"]}')
    items = [ProfileItem(type="fact", content="python"), ProfileItem(type="gotcha", content="x")]
    assert llm.classify_profile(items) == ["stack", "pitfalls"]
    with pytest.raises(ValueError, match="wrong number"):
        llm.classify_profile(items[:1])


def test_reply_without_json_raises() -> None:
    llm, _ = _llm("I could not do that.")
    with pytest.raises(ValueError, match="no JSON object"):
        llm.summarize_session("x")
