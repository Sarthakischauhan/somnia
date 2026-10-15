"""Per-request auth + RLS scope as a FastAPI dependency."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, status
from psycopg_pool import ConnectionPool

from somnia.auth.principal import Principal, resolve_principal
from somnia.db.connection import Conn, user_transaction


@dataclass(frozen=True, slots=True)
class Scoped:
    """A connection inside an RLS-scoped transaction plus the caller's identity."""

    conn: Conn
    principal: Principal


def _bearer_token(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    return token.strip()


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
