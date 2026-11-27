"""Per-request auth + RLS scope as a FastAPI dependency."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Header, HTTPException, status
from psycopg_pool import ConnectionPool

from somnia.auth.principal import Principal, resolve_principal
from somnia.auth.supabase import resolve_dashboard_user
from somnia.auth.tokens import TOKEN_PREFIX
from somnia.db.connection import Conn, user_transaction


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
