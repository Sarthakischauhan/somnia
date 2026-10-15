"""Build providers from ProviderSettings."""

from dataclasses import dataclass

import httpx

from somnia.config import ProviderSettings
from somnia.providers.fake import FakeEmbedder, FakeLlm
from somnia.providers.openai_compat import OpenAiEmbedder, OpenAiLlm
from somnia.providers.protocols import Embedder, Llm


@dataclass(frozen=True, slots=True)
class Providers:
    embedder: Embedder
    llm: Llm


def build_providers(settings: ProviderSettings) -> Providers:
    if settings.provider == "fake":
        return Providers(embedder=FakeEmbedder(), llm=FakeLlm())
    client = httpx.Client(
        base_url=settings.llm_base_url,
        headers={"Authorization": f"Bearer {settings.llm_api_key.get_secret_value()}"},
        timeout=settings.request_timeout_s,
    )
    return Providers(
        embedder=OpenAiEmbedder(client, settings.embedding_model),
        llm=OpenAiLlm(client, settings.chat_model),
    )
