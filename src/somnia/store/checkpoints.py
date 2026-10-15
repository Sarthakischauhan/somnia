"""Checkpoints: one open checkpoint per (user, repo, branch); older ones get closed."""

from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel, Field

from somnia.db.connection import Conn
from somnia.records import CheckpointRecord

_COLUMNS = (
    "id, session_id, repo, branch, goal, state, next_steps, files_touched, git_ref,"
    " pushed, status, source, created_at"
)


class CheckpointDraft(BaseModel):
    goal: str = Field(min_length=1)
    state: str = Field(min_length=1)
    next_steps: list[str] = Field(default_factory=list)
    files_touched: list[str] = Field(default_factory=list)
    git_ref: str | None = None
    pushed: bool = False


def create_checkpoint(
    conn: Conn,
    *,
    user_id: UUID,
    session_id: UUID | None,
    repo: str,
    branch: str,
    draft: CheckpointDraft,
    source: str,
) -> CheckpointRecord:
    conn.execute(
        "update public.checkpoints set status = 'closed'"
        " where user_id = %s and repo = %s and branch = %s and status = 'open'",
        (user_id, repo, branch),
    )
    with conn.cursor(row_factory=class_row(CheckpointRecord)) as cur:
        cur.execute(
            "insert into public.checkpoints (user_id, session_id, repo, branch, goal, state,"
            " next_steps, files_touched, git_ref, pushed, source)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning " + _COLUMNS,
            (
                user_id,
                session_id,
                repo,
                branch,
                draft.goal,
                draft.state,
                draft.next_steps,
                draft.files_touched,
                draft.git_ref,
                draft.pushed,
                source,
            ),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("checkpoint insert returned no row")
    return row


def latest_open_checkpoint(conn: Conn, repo: str, branch: str) -> CheckpointRecord | None:
    """RLS-scoped: callers run inside user_transaction."""
    with conn.cursor(row_factory=class_row(CheckpointRecord)) as cur:
        cur.execute(
            "select " + _COLUMNS + " from public.checkpoints"
            " where repo = %s and branch = %s and status = 'open'"
            " order by created_at desc limit 1",
            (repo, branch),
        )
        return cur.fetchone()


def latest_checkpoint_for_session(conn: Conn, session_id: UUID) -> CheckpointRecord | None:
    with conn.cursor(row_factory=class_row(CheckpointRecord)) as cur:
        cur.execute(
            "select " + _COLUMNS + " from public.checkpoints where session_id = %s"
            " order by created_at desc limit 1",
            (session_id,),
        )
        return cur.fetchone()
