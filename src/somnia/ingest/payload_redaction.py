"""Redact secrets inside a JSON payload before it is stored."""

import re

from pydantic import JsonValue

from somnia.ingest.redaction import redact_secrets

_SECRET_KEY = re.compile(
    r"(?i)(password|passwd|secret|api_?key|access_?key|token|authorization|private_?key)"
)
REDACTED_VALUE = "[REDACTED]"


def redact_json(value: JsonValue, key: str | None = None) -> JsonValue:
    """Walk dicts/lists: string values under secret-looking keys are replaced whole,
    all other strings go through the shared text redactor."""
    if isinstance(value, dict):
        return {k: redact_json(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_json(v, key) for v in value]
    if isinstance(value, str):
        if key is not None and _SECRET_KEY.search(key) and value:
            return REDACTED_VALUE
        return redact_secrets(value).text
    return value
