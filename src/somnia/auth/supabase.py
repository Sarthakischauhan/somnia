"""Verify dashboard bearer tokens with the configured Supabase Auth project."""

from uuid import UUID

import httpx
from fastapi import HTTPException, status
from pydantic import BaseModel, ValidationError


class _AuthUser(BaseModel):
    id: UUID
    is_anonymous: bool = False


def resolve_dashboard_user(client: httpx.Client, token: str) -> UUID:
    # Supabase Auth verifies the token; never derive identity from unverified claims.
    try:
        response = client.get("user", headers={"Authorization": f"Bearer {token}"})
    except httpx.RequestError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth unavailable") from exc
    if response.status_code in (400, 401, 403):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid dashboard token")
    if response.status_code != 200:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth unavailable")
    try:
        user = _AuthUser.model_validate_json(response.content)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth unavailable") from exc
    if user.is_anonymous:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign-in required")
    return user.id
