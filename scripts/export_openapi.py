"""Write the FastAPI OpenAPI schema to web/openapi.json (source for the typed TS client)."""

import json
from pathlib import Path

from pydantic import SecretStr

from somnia.api.app import create_app
from somnia.config import ApiSettings
from somnia.providers.fake import FakeEmbedder

app = create_app(ApiSettings(api_database_url=SecretStr("postgresql://unused")), FakeEmbedder())
target = Path(__file__).resolve().parent.parent / "web" / "openapi.json"
target.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
print(f"wrote {target}")
