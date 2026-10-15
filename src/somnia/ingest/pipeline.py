"""Worker step: claim unprocessed events, redact, chunk, embed, store chunks."""

from dataclasses import dataclass
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel, JsonValue

from somnia.db.connection import Conn
from somnia.db.vectors import to_vector_literal
from somnia.ingest.chunking import chunk_text
from somnia.ingest.event_models import EVENT_ADAPTER
from somnia.ingest.event_text import render_event
from somnia.ingest.redaction import redact_secrets
from somnia.providers.protocols import Embedder


class _PendingEvent(BaseModel):
    id: int
    user_id: UUID
    session_id: UUID
    seq: int
    kind: str
    payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class _PendingChunk:
    event: _PendingEvent
    ord: int
    content: str
    redactions: int


def process_pending_events(
    conn: Conn, embedder: Embedder, batch_size: int, max_chars: int, overlap: int
) -> int:
    """Process one batch; returns how many events were consumed. Safe to run
    from many workers at once thanks to FOR UPDATE SKIP LOCKED."""
    with conn.transaction():
        with conn.cursor(row_factory=class_row(_PendingEvent)) as cur:
            cur.execute(
                "select id, user_id, session_id, seq, kind, payload from public.events"
                " where processed_at is null order by id limit %s for update skip locked",
                (batch_size,),
            )
            events = cur.fetchall()
        if not events:
            return 0
        pending: list[_PendingChunk] = []
        for event in events:
            body = EVENT_ADAPTER.validate_python(
                {"seq": event.seq, "kind": event.kind, "payload": event.payload}
            )
            redacted = redact_secrets(render_event(body))
            for ord_, piece in enumerate(chunk_text(redacted.text, max_chars, overlap)):
                pending.append(_PendingChunk(event, ord_, piece, redacted.count))
        vectors = embedder.embed([p.content for p in pending])
        with conn.cursor() as cur:
            cur.executemany(
                "insert into public.chunks"
                " (user_id, session_id, event_id, ord, content, redactions, embedding)"
                " values (%s, %s, %s, %s, %s, %s, %s::extensions.vector)"
                " on conflict (event_id, ord) do nothing",
                [
                    (
                        p.event.user_id,
                        p.event.session_id,
                        p.event.id,
                        p.ord,
                        p.content,
                        p.redactions,
                        to_vector_literal(v),
                    )
                    for p, v in zip(pending, vectors, strict=True)
                ],
            )
            cur.execute(
                "update public.events set processed_at = now() where id = any(%s)",
                ([e.id for e in events],),
            )
        return len(events)
