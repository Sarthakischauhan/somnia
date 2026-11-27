"""Print the FastAPI OpenAPI schema for dashboard type generation."""

import json

import httpx
from pydantic import SecretStr

from somnia.api.app import create_app
from somnia.config import ApiSettings
from somnia.memory.inference import OpenAiEmbedder

with httpx.Client(trust_env=False) as client:
    app = create_app(
        ApiSettings(api_database_url=SecretStr("postgresql://unused"), _env_file=None),
        OpenAiEmbedder(client, "unused"),
    )
    schema = app.openapi()
print(json.dumps(schema, sort_keys=True))
