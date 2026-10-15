"""Agent task queue on a plain table, claimed with FOR UPDATE SKIP LOCKED."""

from typing import Literal
from uuid import UUID

from psycopg.rows import class_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field, JsonValue

from somnia.auth.principal import Principal
from somnia.db.connection import Conn
from somnia.records import TaskRecord

TASK_COLUMNS = (
    "id, session_id, repo, branch, title, payload, status, priority, attempts,"
    " claimed_by_device, locked_until, result, created_at, updated_at"
)


class TaskDraft(BaseModel):
    title: str = Field(min_length=1)
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    repo: str | None = None
    branch: str | None = None
    session_id: UUID | None = None
    priority: int = 0


def enqueue_task(conn: Conn, principal: Principal, draft: TaskDraft) -> TaskRecord:
    with conn.cursor(row_factory=class_row(TaskRecord)) as cur:
        cur.execute(
            "insert into public.tasks (user_id, created_by_device, session_id, repo, branch,"
            " title, payload, priority) values (%s, %s, %s, %s, %s, %s, %s, %s)"
            " returning " + TASK_COLUMNS,
            (
                principal.user_id,
                principal.device_id,
                draft.session_id,
                draft.repo,
                draft.branch,
                draft.title,
                Jsonb(draft.payload),
                draft.priority,
            ),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("task insert returned no row")
    return row


def claim_task(conn: Conn, device_id: UUID, lease_seconds: int) -> TaskRecord | None:
    """Claim the highest-priority queued task (or one whose lease expired)."""
    with conn.cursor(row_factory=class_row(TaskRecord)) as cur:
        cur.execute(
            "update public.tasks set status = 'running', attempts = attempts + 1,"
            " claimed_by_device = %s, locked_until = now() + make_interval(secs => %s),"
            " updated_at = now()"
            " where id = (select id from public.tasks"
            "   where status = 'queued' or (status = 'running' and locked_until < now())"
            "   order by priority desc, created_at limit 1 for update skip locked)"
            " returning " + TASK_COLUMNS,
            (device_id, lease_seconds),
        )
        return cur.fetchone()


def complete_task(
    conn: Conn,
    task_id: UUID,
    status: Literal["done", "failed"],
    result: dict[str, JsonValue] | None,
) -> TaskRecord | None:
    with conn.cursor(row_factory=class_row(TaskRecord)) as cur:
        cur.execute(
            "update public.tasks set status = %s, result = %s, locked_until = null,"
            " updated_at = now() where id = %s returning " + TASK_COLUMNS,
            (status, Jsonb(result) if result is not None else None, task_id),
        )
        return cur.fetchone()


def get_task(conn: Conn, task_id: UUID) -> TaskRecord | None:
    with conn.cursor(row_factory=class_row(TaskRecord)) as cur:
        cur.execute("select " + TASK_COLUMNS + " from public.tasks where id = %s", (task_id,))
        return cur.fetchone()
