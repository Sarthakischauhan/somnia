"""OpenAI-compatible HTTP providers (OpenAI, Azure-compatible gateways, vLLM, Ollama...)."""

from collections.abc import Sequence

import httpx
from pydantic import BaseModel

from somnia.db.vectors import EMBEDDING_DIM
from somnia.providers.protocols import MergeDecision, SessionDigest

_DIGEST_PROMPT = """You consolidate a coding-agent session into durable memory.
Return JSON: {"goal": str, "state": str, "next_steps": [str], "files_touched": [str],
"memories": [{"type": "fact|decision|convention|gotcha|todo",
"scope": "global|repo|branch", "content": str, "confidence": 0..1}]}.
Only keep memories that will help a future agent on this repo. Never include secrets."""

_RECONCILE_PROMPT = """Compare an EXISTING memory with a CANDIDATE memory.
Return JSON {"action": "add|merge|supersede", "content": str}.
merge: same fact, content = best combined wording. supersede: candidate replaces
an outdated/contradicted existing memory, content = candidate wording.
add: unrelated, content = candidate."""


class _EmbeddingItem(BaseModel):
    index: int
    embedding: list[float]


class _EmbeddingResponse(BaseModel):
    data: list[_EmbeddingItem]


class _ChatMessage(BaseModel):
    content: str


class _ChatChoice(BaseModel):
    message: _ChatMessage


class _ChatResponse(BaseModel):
    choices: list[_ChatChoice]


class OpenAiEmbedder:
    def __init__(self, client: httpx.Client, model: str) -> None:
        self._client = client
        self._model = model

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.post(
            "/embeddings",
            json={"model": self._model, "input": list(texts), "dimensions": EMBEDDING_DIM},
        )
        response.raise_for_status()
        parsed = _EmbeddingResponse.model_validate_json(response.content)
        return [item.embedding for item in sorted(parsed.data, key=lambda i: i.index)]


class OpenAiLlm:
    def __init__(self, client: httpx.Client, model: str) -> None:
        self._client = client
        self._model = model

    def summarize_session(self, transcript: str) -> SessionDigest:
        return SessionDigest.model_validate_json(self._complete(_DIGEST_PROMPT, transcript))

    def reconcile(self, existing: str, candidate: str) -> MergeDecision:
        user = f"EXISTING:\n{existing}\n\nCANDIDATE:\n{candidate}"
        return MergeDecision.model_validate_json(self._complete(_RECONCILE_PROMPT, user))

    def _complete(self, system: str, user: str) -> str:
        response = self._client.post(
            "/chat/completions",
            json={
                "model": self._model,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
        )
        response.raise_for_status()
        return _ChatResponse.model_validate_json(response.content).choices[0].message.content
