"""Write the FastAPI OpenAPI schema to web/openapi.json (source for the typed TS client)."""

import json
from pathlib import Path

import httpx
from pydantic import SecretStr

from somnia.api.app import create_app
from somnia.config import ApiSettings
from somnia.memory.inference import OpenAiEmbedder

with httpx.Client(trust_env=False) as client:
    app = create_app(
        ApiSettings(api_database_url=SecretStr("postgresql://unused")),
        OpenAiEmbedder(client, "unused"),
    )
    schema = app.openapi()
target = Path(__file__).resolve().parent.parent / "web" / "openapi.json"
target.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n")
print(f"wrote {target}")
