"""Llm backed by symphony-harness (`core_harness`): any provider `core_ai` can reach.

Each call is one tool-less `CoreHarness.run` capped at a single turn, so the dream job
gets one model completion per summarize / reconcile / classify, same as the HTTP Llm.
"""

import asyncio
from collections.abc import Sequence

from core_ai import ModelRegistry
from core_harness import CoreHarness, HarnessConfig
from pydantic import BaseModel
from somnia.providers.protocols import (
    MemoryScope,
    ProfileItem,
    ProfileSection,
    ProfileSections,
    ReconcileDecision,
    SessionDigest,
)

from somnia.providers.prompts import DIGEST_PROMPT, PROFILE_PROMPT, RECONCILE_PROMPT

_JSON_ONLY = "\nReply with the JSON object only: no prose, no code fences."


class HarnessLlm:
    def __init__(self, registry: ModelRegistry, model_id: str, timeout_s: float) -> None:
        self._registry = registry
        self._model_id = model_id
        self._config = HarnessConfig(max_turns=1, max_runtime_seconds=timeout_s)

    def summarize_session(self, transcript: str) -> SessionDigest:
        return self._complete(DIGEST_PROMPT, transcript, SessionDigest)

    def reconcile(
        self, existing: str, candidate: str, candidate_scope: MemoryScope
    ) -> ReconcileDecision:
        user = f"EXISTING:\n{existing}\n\nCANDIDATE (scope={candidate_scope}):\n{candidate}"
        return self._complete(RECONCILE_PROMPT, user, ReconcileDecision)

    def classify_profile(self, items: Sequence[ProfileItem]) -> list[ProfileSection]:
        if not items:
            return []
        user = "\n".join(f"{i + 1}. ({item.type}) {item.content}" for i, item in enumerate(items))
        parsed = self._complete(PROFILE_PROMPT, user, ProfileSections)
        if len(parsed.sections) != len(items):
            raise ValueError("profile classification returned the wrong number of sections")
        return parsed.sections

    def _complete[T: BaseModel](self, system: str, user: str, model: type[T]) -> T:
        harness = CoreHarness(
            registry=self._registry,
            model_id=self._model_id,
            system_prompt=system + _JSON_ONLY,
            config=self._config,
        )
        # The worker is synchronous, so each call gets its own event loop.
        result = asyncio.run(harness.run(user, conversation=[]))
        return model.model_validate_json(_json_object(result.output_text))


def _json_object(text: str) -> str:
    """The outermost {...} in `text`; tolerates code fences or a stray sentence."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("model reply contained no JSON object")
    return text[start : end + 1]
