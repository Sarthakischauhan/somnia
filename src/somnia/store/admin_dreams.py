"""dream_runs history, manual trigger and schedule status (RLS-scoped)."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.connection import Conn

_COLUMNS = (
    "id, user_id, trigger, status, requested_at, started_at, finished_at, sessions_processed,"
    " checkpoints_created, memories_added, memories_merged, memories_superseded,"
    " memories_decayed, error"
)


class DreamRunRecord(BaseModel):
    id: UUID
    user_id: UUID | None
    trigger: Literal["schedule", "pg_cron", "manual"]
    status: Literal["requested", "running", "succeeded", "failed"]
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    sessions_processed: int
    checkpoints_created: int
    memories_added: int
    memories_merged: int
    memories_superseded: int
    memories_decayed: int
    error: str | None


class DreamSchedule(BaseModel):
    pg_cron_schedule: str | None
    worker_interval_s: float
    last_run: DreamRunRecord | None
    last_success_at: datetime | None
    pending_requests: int


def list_dream_runs(conn: Conn, limit: int) -> list[DreamRunRecord]:
    with conn.cursor(row_factory=class_row(DreamRunRecord)) as cur:
        cur.execute(
            "select " + _COLUMNS + " from public.dream_runs"
            " order by requested_at desc, id limit %s",
            (limit,),
        )
        return cur.fetchall()


def request_dream(conn: Conn) -> DreamRunRecord:
    row = conn.execute("select public.somnia_request_user_dream()").fetchone()
    if row is None:
        raise RuntimeError("dream request returned no id")
    with conn.cursor(row_factory=class_row(DreamRunRecord)) as cur:
        cur.execute("select " + _COLUMNS + " from public.dream_runs where id = %s", (row[0],))
        run = cur.fetchone()
    if run is None:
        raise RuntimeError("requested dream run not visible")
    return run


def dream_schedule(conn: Conn, worker_interval_s: float) -> DreamSchedule:
    cron = conn.execute("select public.somnia_dream_cron_schedule()").fetchone()
    runs = list_dream_runs(conn, 1)
    stats = conn.execute(
        "select max(finished_at) filter (where status = 'succeeded'),"
        " count(*) filter (where status = 'requested') from public.dream_runs"
    ).fetchone()
    return DreamSchedule(
        pg_cron_schedule=cron[0] if cron else None,
        worker_interval_s=worker_interval_s,
        last_run=runs[0] if runs else None,
        last_success_at=stats[0] if stats else None,
        pending_requests=int(stats[1]) if stats else 0,
    )
