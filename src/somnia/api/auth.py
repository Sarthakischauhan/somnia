"""Per-request auth + RLS scope as a FastAPI dependency."""

import hashlib
import secrets
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import Header, HTTPException, status
from psycopg.rows import class_row
from psycopg_pool import ConnectionPool
from pydantic import BaseModel, ValidationError

from somnia.db.client import Conn, user_transaction

TOKEN_PREFIX = "smn_"


def generate_device_token() -> str:
    return TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_device_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Principal(BaseModel, frozen=True):
    user_id: UUID
    device_id: UUID


def resolve_principal(conn: Conn, token: str) -> Principal | None:
    with conn.cursor(row_factory=class_row(Principal)) as cur:
        cur.execute(
            "select user_id, device_id from public.somnia_resolve_device(%s)",
            (hash_device_token(token),),
        )
        return cur.fetchone()


class _AuthUser(BaseModel):
    id: UUID
    is_anonymous: bool = False


_DASHBOARD_AUTH_TTL_SECONDS = 30.0
_dashboard_users: dict[str, tuple[float, UUID]] = {}


def resolve_dashboard_user(client: httpx.Client, token: str) -> UUID:
    now = time.monotonic()
    cached = _dashboard_users.get(token)
    if cached is not None and cached[0] > now:
        return cached[1]
    # Supabase Auth verifies the token; never derive identity from unverified claims.
    try:
        response = client.get("user", headers={"Authorization": f"Bearer {token}"})
    except httpx.RequestError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth unavailable") from exc
    if response.status_code in (400, 401):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid dashboard token")
    if response.status_code == 403:
        message = "invalid dashboard token"
        try:
            payload = response.json()
            code = str(payload.get("error_code", ""))
            description = str(payload.get("msg", ""))[:160]
        except ValueError:
            code = ""
            description = ""
        if code not in {"bad_jwt", "session_expired", "session_not_found"} or description:
            message = f"dashboard token rejected ({code or 'forbidden'}): {description}"
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, message)
    if response.status_code != 200:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth unavailable")
    try:
        user = _AuthUser.model_validate_json(response.content)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth unavailable") from exc
    if user.is_anonymous:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign-in required")
    _dashboard_users[token] = (now + _DASHBOARD_AUTH_TTL_SECONDS, user.id)
    if len(_dashboard_users) > 32:
        expired = [key for key, (expires, _) in _dashboard_users.items() if expires <= now]
        for key in expired:
            del _dashboard_users[key]
    return user.id


@dataclass(frozen=True, slots=True)
class Scoped:
    """A connection inside an RLS-scoped transaction plus the caller's identity."""

    conn: Conn
    principal: Principal


def _bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token or any(c.isspace() for c in token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing or malformed bearer token")
    return token


def scoped_dependency(pool: ConnectionPool[Conn]) -> Callable[..., Iterator[Scoped]]:
    def dependency(
        authorization: Annotated[str | None, Header()] = None,
    ) -> Iterator[Scoped]:
        token = _bearer_token(authorization)
        with pool.connection() as conn:
            principal = resolve_principal(conn, token)
            if principal is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid device token")
            with user_transaction(conn, principal.user_id):
                yield Scoped(conn=conn, principal=principal)

    return dependency


def user_database_dependency(
    pool: ConnectionPool[Conn],
    device_scope: Callable[[str | None], Iterator[Scoped]],
    auth_client: httpx.Client | None,
) -> Callable[..., Iterator[Conn]]:
    def dependency(authorization: Annotated[str | None, Header()] = None) -> Iterator[Conn]:
        token = _bearer_token(authorization)
        if token.startswith(TOKEN_PREFIX):
            with contextmanager(device_scope)(authorization) as scoped:
                yield scoped.conn
            return
        if auth_client is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid bearer token")
        user_id = resolve_dashboard_user(auth_client, token)
        with pool.connection() as conn, user_transaction(conn, user_id):
            yield conn

    return dependency
