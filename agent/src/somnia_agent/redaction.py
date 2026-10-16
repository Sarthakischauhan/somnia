"""Client-side secret redaction, applied before anything is written to the spool.

Mirrors somnia.ingest.redaction / payload_redaction on the server (parity is tested in the
server test suite) so secrets never sit on disk or cross the network unredacted.
"""

import re

from pydantic import JsonValue

PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "private_key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
        "[REDACTED:private_key]",
    ),
    ("aws_key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), "[REDACTED:aws_key]"),
    (
        "github",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"),
        "[REDACTED:github_token]",
    ),
    ("openai", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "[REDACTED:api_key]"),
    ("slack", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "[REDACTED:slack_token]"),
    ("somnia", re.compile(r"\bsmn_[A-Za-z0-9_-]{20,}"), "[REDACTED:somnia_token]"),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
        "[REDACTED:jwt]",
    ),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{16,}=*"), "Bearer [REDACTED]"),
    ("url_password", re.compile(r"(\b[a-z][a-z0-9+.-]*://[^:/\s@]+:)[^@\s]+@"), r"\1[REDACTED]@"),
    (
        "assignment",
        re.compile(
            r"(?i)\b([A-Z0-9_]*(?:password|passwd|secret|api_?key|access_?key|token)[A-Z0-9_]*"
            r"\s*[:=]\s*)(['\"]?)([^\s'\"]{6,})\2"
        ),
        r"\1\2[REDACTED]\2",
    ),
)

SECRET_KEY = re.compile(
    r"(?i)(password|passwd|secret|api_?key|access_?key|token|authorization|private_?key)"
)
REDACTED_VALUE = "[REDACTED]"


def redact_text(text: str) -> str:
    for _name, pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_json(value: JsonValue, key: str | None = None) -> JsonValue:
    if isinstance(value, dict):
        return {k: redact_json(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_json(v, key) for v in value]
    if isinstance(value, str):
        if key is not None and SECRET_KEY.search(key) and value:
            return REDACTED_VALUE
        return redact_text(value)
    return value
