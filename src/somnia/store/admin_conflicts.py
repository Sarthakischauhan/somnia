"""Memory conflicts for the admin UI (RLS-scoped). Resolution never deletes a memory:
keep_existing / keep_candidate mark the other side superseded, keep_both just closes it."""

from datetime import datetime
from typing import Literal
from uuid import UUID

import psycopg
from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.connection import Conn
from somnia.store.admin_memories import MemoryRecord, get_memory

ConflictOutcome = Literal["superseded", "coexist", "flagged"]
ConflictStatus = Literal["open", "resolved"]
Resolution = Literal["keep_existing", "keep_candidate", "keep_both"]


class ConflictRecord(BaseModel):
    id: UUID
    repo: str | None
    existing_memory_id: UUID
    candidate_memory_id: UUID
    outcome: ConflictOutcome
    rationale: str
    session_id: UUID | None
    status: ConflictStatus
    resolution: Resolution | None
    created_at: datetime
    resolved_at: datetime | None


class ConflictView(BaseModel):
    conflict: ConflictRecord
    existing: MemoryRecord
    candidate: MemoryRecord


class ConflictResolution(BaseModel):
    resolution: Resolution


class ConflictAlreadyResolvedError(Exception):
    pass


_COLUMNS = (
    "id, repo, existing_memory_id, candidate_memory_id, outcome, rationale, session_id,"
    " status, resolution, created_at, resolved_at"
)


def _view(conn: Conn, conflict: ConflictRecord) -> ConflictView:
    existing = get_memory(conn, conflict.existing_memory_id)
    candidate = get_memory(conn, conflict.candidate_memory_id)
    if existing is None or candidate is None:
        raise LookupError("conflict references a memory that is not visible")
    return ConflictView(conflict=conflict, existing=existing, candidate=candidate)


def list_conflicts(
    conn: Conn, statuses: list[ConflictStatus], outcomes: list[ConflictOutcome], limit: int
) -> list[ConflictView]:
    with conn.cursor(row_factory=class_row(ConflictRecord)) as cur:
        cur.execute(
            "select " + _COLUMNS + " from public.memory_conflicts"
            " where status = any(%s) and outcome = any(%s)"
            " order by created_at desc, id limit %s",
            (statuses, outcomes, limit),
        )
        rows = cur.fetchall()
    return [_view(conn, row) for row in rows]


def resolve_conflict(conn: Conn, conflict_id: UUID, resolution: Resolution) -> ConflictView | None:
    try:
        row = conn.execute(
            "select public.somnia_resolve_conflict(%s, %s)", (conflict_id, resolution)
        ).fetchone()
    except psycopg.errors.ObjectNotInPrerequisiteState as exc:
        raise ConflictAlreadyResolvedError(str(exc)) from exc
    if row is None or row[0] is None:
        return None
    with conn.cursor(row_factory=class_row(ConflictRecord)) as cur:
        cur.execute(
            "select " + _COLUMNS + " from public.memory_conflicts where id = %s", (conflict_id,)
        )
        conflict = cur.fetchone()
    return None if conflict is None else _view(conn, conflict)
