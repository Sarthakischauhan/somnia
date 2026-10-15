"""Resolve a bearer token to the device and user it belongs to."""

from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.auth.tokens import hash_device_token
from somnia.db.connection import Conn


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
