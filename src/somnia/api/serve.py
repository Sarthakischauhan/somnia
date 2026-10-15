"""`somnia-api` entry point."""

import uvicorn

from somnia.api.app import create_app
from somnia.config import ApiSettings, ProviderSettings
from somnia.providers.factory import build_providers


def main() -> None:
    settings = ApiSettings()  # values come from the environment
    providers = build_providers(ProviderSettings())
    uvicorn.run(create_app(settings, providers.embedder), host="0.0.0.0", port=8000)
