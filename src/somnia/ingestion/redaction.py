"""Secret redaction applied before anything is chunked, embedded or sent to an LLM."""

import re
from dataclasses import dataclass

_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
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


@dataclass(frozen=True, slots=True)
class Redacted:
    text: str
    count: int


def redact_secrets(text: str) -> Redacted:
    total = 0
    for _name, pattern, replacement in _PATTERNS:
        text, n = pattern.subn(replacement, text)
        total += n
    return Redacted(text=text, count=total)
