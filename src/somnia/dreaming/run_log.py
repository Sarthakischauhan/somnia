"""dream_runs bookkeeping."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from somnia.db.connection import Conn


class DreamCounts(BaseModel):
    sessions_processed: int = 0
    checkpoints_created: int = 0
    memories_added: int = 0
    memories_merged: int = 0
    memories_superseded: int = 0
    memories_decayed: int = 0


def claim_requested_run(conn: Conn) -> UUID | None:
    row = conn.execute(
        "update public.dream_runs set status = 'running', started_at = now()"
        " where id = (select id from public.dream_runs where status = 'requested'"
        "   order by requested_at limit 1 for update skip locked) returning id"
    ).fetchone()
    return UUID(str(row[0])) if row else None


def start_run(conn: Conn, trigger: str, now: datetime) -> UUID:
    row = conn.execute(
        "insert into public.dream_runs (trigger, status, requested_at, started_at)"
        " values (%s, 'running', %s, %s) returning id",
        (trigger, now, now),
    ).fetchone()
    if row is None:
        raise RuntimeError("dream_runs insert returned no row")
    return UUID(str(row[0]))


def finish_run(
    conn: Conn, run_id: UUID, counts: DreamCounts, error: str | None, now: datetime
) -> None:
    conn.execute(
        "update public.dream_runs set status = %s, finished_at = %s, error = %s,"
        " sessions_processed = %s, checkpoints_created = %s, memories_added = %s,"
        " memories_merged = %s, memories_superseded = %s, memories_decayed = %s"
        " where id = %s",
        (
            "failed" if error else "succeeded",
            now,
            error,
            counts.sessions_processed,
            counts.checkpoints_created,
            counts.memories_added,
            counts.memories_merged,
            counts.memories_superseded,
            counts.memories_decayed,
            run_id,
        ),
    )
