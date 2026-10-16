"""dream_runs bookkeeping. Timestamps are wall-clock (clock_timestamp()); the logical
`now` used for decay is stored separately in logical_now."""

from datetime import datetime
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.connection import Conn


class DreamCounts(BaseModel):
    sessions_processed: int = 0
    checkpoints_created: int = 0
    memories_added: int = 0
    memories_merged: int = 0
    memories_superseded: int = 0
    memories_decayed: int = 0
    conflicts_flagged: int = 0
    memories_coexisting: int = 0
    profile_entries_changed: int = 0


class RunRequest(BaseModel):
    user_id: UUID | None
    repo: str | None
    trigger: str


def claim_requested_run(conn: Conn) -> UUID | None:
    row = conn.execute(
        "update public.dream_runs set status = 'running', started_at = clock_timestamp()"
        " where id = (select id from public.dream_runs where status = 'requested'"
        "   order by requested_at limit 1 for update skip locked) returning id"
    ).fetchone()
    return UUID(str(row[0])) if row else None


def load_request(conn: Conn, run_id: UUID) -> RunRequest:
    with conn.cursor(row_factory=class_row(RunRequest)) as cur:
        cur.execute("select user_id, repo, trigger from public.dream_runs where id = %s", (run_id,))
        request = cur.fetchone()
    if request is None:
        raise LookupError(f"dream run {run_id} not found")
    return request


def start_user_run(
    conn: Conn, user_id: UUID, trigger: str, now: datetime, parent_run_id: UUID | None
) -> UUID:
    row = conn.execute(
        "insert into public.dream_runs (user_id, trigger, status, requested_at, started_at,"
        " logical_now, parent_run_id)"
        " values (%s, %s, 'running', clock_timestamp(), clock_timestamp(), %s, %s) returning id",
        (user_id, trigger, now, parent_run_id),
    ).fetchone()
    if row is None:
        raise RuntimeError("dream_runs insert returned no row")
    return UUID(str(row[0]))


def finish_run(
    conn: Conn, run_id: UUID, counts: DreamCounts, error: str | None, now: datetime
) -> None:
    conn.execute(
        "update public.dream_runs set status = %s, error = %s, logical_now = %s,"
        " started_at = coalesce(started_at, clock_timestamp()), finished_at = clock_timestamp(),"
        " sessions_processed = %s, checkpoints_created = %s, memories_added = %s,"
        " memories_merged = %s, memories_superseded = %s, memories_decayed = %s,"
        " conflicts_flagged = %s, memories_coexisting = %s, profile_entries_changed = %s"
        " where id = %s",
        (
            "failed" if error else "succeeded",
            error,
            now,
            counts.sessions_processed,
            counts.checkpoints_created,
            counts.memories_added,
            counts.memories_merged,
            counts.memories_superseded,
            counts.memories_decayed,
            counts.conflicts_flagged,
            counts.memories_coexisting,
            counts.profile_entries_changed,
            run_id,
        ),
    )
