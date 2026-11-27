"""`somnia-api` entry point."""

import os

import uvicorn

from somnia.api.app import create_app
from somnia.config import ApiSettings, ProviderSettings
from somnia.memory.inference import OpenAiEmbedder, embedding_client


def main() -> None:
    try:
        port = int(os.environ.get("PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SystemExit("PORT must be an integer between 1 and 65535") from None

    settings = ApiSettings()  # values come from the environment
    provider = ProviderSettings()
    host = os.environ.get("SOMNIA_HOST", "127.0.0.1")
    with embedding_client(provider) as client:
        uvicorn.run(
            create_app(settings, OpenAiEmbedder(client, provider.embedding_model)),
            host=host,
            port=port,
            workers=1,
        )
