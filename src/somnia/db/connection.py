"""Connection type alias and the per-request RLS scope."""

import json
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from psycopg import Connection
from psycopg.rows import TupleRow

Conn = Connection[TupleRow]


@contextmanager
def user_transaction(conn: Conn, user_id: UUID) -> Iterator[Conn]:
    """Run a transaction as the `authenticated` role with auth.uid() = user_id,
    so every statement inside is filtered by RLS."""
    with conn.transaction():
        conn.execute("set local role authenticated")
        claims = json.dumps({"sub": str(user_id), "role": "authenticated"})
        conn.execute("select set_config('request.jwt.claims', %s, true)", (claims,))
        yield conn
