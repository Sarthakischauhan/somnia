"""Idempotent event writes keyed by (session_id, seq)."""

from collections.abc import Sequence
from uuid import UUID

from psycopg.types.json import Jsonb
from pydantic import BaseModel

from somnia.db.connection import Conn
from somnia.ingest.event_models import EventIn


class InsertOutcome(BaseModel):
    accepted: int
    duplicates: int


def insert_events(
    conn: Conn, user_id: UUID, session_id: UUID, events: Sequence[EventIn]
) -> InsertOutcome:
    accepted = 0
    with conn.cursor() as cur:
        for event in events:
            cur.execute(
                "insert into public.events (user_id, session_id, seq, kind, payload)"
                " values (%s, %s, %s, %s, %s)"
                " on conflict on constraint events_session_seq_key do nothing",
                (
                    user_id,
                    session_id,
                    event.seq,
                    event.kind,
                    Jsonb(event.payload.model_dump(mode="json")),
                ),
            )
            accepted += cur.rowcount
    return InsertOutcome(accepted=accepted, duplicates=len(events) - accepted)


def count_unprocessed(conn: Conn, session_id: UUID) -> int:
    row = conn.execute(
        "select count(*) from public.events where session_id = %s and processed_at is null",
        (session_id,),
    ).fetchone()
    return int(row[0]) if row else 0
