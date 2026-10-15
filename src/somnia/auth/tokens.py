"""Per-device API tokens. Only the SHA-256 hash is stored; tokens are 256-bit random."""

import hashlib
import secrets

TOKEN_PREFIX = "smn_"


def generate_device_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
