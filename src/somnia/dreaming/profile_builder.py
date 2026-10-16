"""Incremental project-profile rebuild (service connection, explicit user_id).

Only memories updated and checkpoints created since the profile's watermarks are read:
active repo-scoped memories are (re)classified into a section and upserted by source
memory; superseded or archived ones retire their entry. A branch's newest checkpoint
replaces that branch's open-work entries. Entries are retired, never deleted.
"""

from datetime import datetime
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.connection import Conn
from somnia.providers.protocols import Llm, MemoryType, ProfileItem

CHECKPOINT_CONFIDENCE = 0.6


class _ProfileState(BaseModel):
    id: UUID
    memories_through: datetime | None
    memories_through_id: UUID | None
    checkpoints_through: datetime | None
    checkpoints_through_id: UUID | None


class _Cursor(BaseModel):
    """Last (timestamp, id) consumed; rows compare as a tuple so ties are never skipped."""

    ts: datetime | None
    id: UUID | None


class _ChangedMemory(BaseModel):
    id: UUID
    type: MemoryType
    content: str
    confidence: float
    active: bool
    source_session_ids: list[UUID]
    updated_at: datetime


class _NewCheckpoint(BaseModel):
    id: UUID
    session_id: UUID | None
    branch: str
    goal: str
    next_steps: list[str]
    created_at: datetime


def _ensure_profile(conn: Conn, user_id: UUID, repo: str) -> _ProfileState:
    with conn.cursor(row_factory=class_row(_ProfileState)) as cur:
        cur.execute(
            "insert into public.project_profiles (user_id, repo) values (%s, %s)"
            " on conflict (user_id, repo) do update set repo = excluded.repo"
            " returning id, memories_through, memories_through_id, checkpoints_through,"
            " checkpoints_through_id",
            (user_id, repo),
        )
        state = cur.fetchone()
    if state is None:
        raise RuntimeError("profile upsert returned no row")
    return state


def _changed_memories(conn: Conn, user_id: UUID, repo: str, since: _Cursor) -> list[_ChangedMemory]:
    with conn.cursor(row_factory=class_row(_ChangedMemory)) as cur:
        cur.execute(
            "select id, type, content, confidence, source_session_ids, updated_at,"
            " (superseded_by is null and archived_at is null) as active"
            " from public.memories where user_id = %s and repo = %s and scope = 'repo'"
            " and (%s::timestamptz is null or (updated_at, id) > (%s::timestamptz, %s::uuid))"
            " order by updated_at, id",
            (user_id, repo, since.ts, since.ts, since.id),
        )
        return cur.fetchall()


def _new_checkpoints(conn: Conn, user_id: UUID, repo: str, since: _Cursor) -> list[_NewCheckpoint]:
    with conn.cursor(row_factory=class_row(_NewCheckpoint)) as cur:
        cur.execute(
            "select id, session_id, branch, goal, next_steps, created_at"
            " from public.checkpoints where user_id = %s and repo = %s"
            " and (%s::timestamptz is null or (created_at, id) > (%s::timestamptz, %s::uuid))"
            " order by created_at, id",
            (user_id, repo, since.ts, since.ts, since.id),
        )
        return cur.fetchall()


def _apply_memories(
    conn: Conn,
    profile_id: UUID,
    user_id: UUID,
    changed: list[_ChangedMemory],
    llm: Llm,
    now: datetime,
) -> int:
    active = [m for m in changed if m.active]
    retired = [m.id for m in changed if not m.active]
    sections = llm.classify_profile([ProfileItem(type=m.type, content=m.content) for m in active])
    with conn.cursor() as cur:
        cur.executemany(
            "insert into public.project_profile_entries (profile_id, user_id, section, content,"
            " confidence, source_memory_id, source_session_ids, created_at, updated_at)"
            " values (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " on conflict (profile_id, source_memory_id) where source_memory_id is not null"
            " do update set section = excluded.section, content = excluded.content,"
            " confidence = excluded.confidence, source_session_ids = excluded.source_session_ids,"
            " updated_at = excluded.updated_at, retired_at = null",
            [
                (
                    profile_id,
                    user_id,
                    section,
                    m.content,
                    m.confidence,
                    m.id,
                    m.source_session_ids,
                    now,
                    now,
                )
                for m, section in zip(active, sections, strict=True)
            ],
        )
        cur.execute(
            "update public.project_profile_entries set retired_at = %s, updated_at = %s"
            " where profile_id = %s and source_memory_id = any(%s) and retired_at is null",
            (now, now, profile_id, retired),
        )
        return len(active) + cur.rowcount


def _apply_checkpoints(
    conn: Conn, profile_id: UUID, user_id: UUID, new: list[_NewCheckpoint], now: datetime
) -> int:
    latest: dict[str, _NewCheckpoint] = {}
    for checkpoint in new:  # ordered by created_at: the last one per branch wins
        latest[checkpoint.branch] = checkpoint
    changed = 0
    for branch, checkpoint in latest.items():
        cur = conn.execute(
            "update public.project_profile_entries set retired_at = %s, updated_at = %s"
            " where profile_id = %s and source_checkpoint_id is not null"
            " and source_branch = %s and retired_at is null",
            (now, now, profile_id, branch),
        )
        changed += cur.rowcount
        items = checkpoint.next_steps or [checkpoint.goal]
        sessions = [checkpoint.session_id] if checkpoint.session_id else []
        with conn.cursor() as insert:
            insert.executemany(
                "insert into public.project_profile_entries (profile_id, user_id, section,"
                " content, confidence, source_checkpoint_id, source_branch, source_session_ids,"
                " created_at, updated_at) values (%s, %s, 'open_work', %s, %s, %s, %s, %s, %s, %s)",
                [
                    (
                        profile_id,
                        user_id,
                        f"[{branch}] {item}",
                        CHECKPOINT_CONFIDENCE,
                        checkpoint.id,
                        branch,
                        sessions,
                        now,
                        now,
                    )
                    for item in items
                ],
            )
        changed += len(items)
    return changed


def rebuild_profile(conn: Conn, user_id: UUID, repo: str, llm: Llm, now: datetime) -> int:
    """Returns how many entries were added, updated or retired."""
    state = _ensure_profile(conn, user_id, repo)
    memory_cursor = _Cursor(ts=state.memories_through, id=state.memories_through_id)
    checkpoint_cursor = _Cursor(ts=state.checkpoints_through, id=state.checkpoints_through_id)
    memories = _changed_memories(conn, user_id, repo, memory_cursor)
    checkpoints = _new_checkpoints(conn, user_id, repo, checkpoint_cursor)
    if not memories and not checkpoints:
        return 0
    changed = 0
    if memories:
        changed += _apply_memories(conn, state.id, user_id, memories, llm, now)
    if checkpoints:
        changed += _apply_checkpoints(conn, state.id, user_id, checkpoints, now)
    if memories:
        memory_cursor = _Cursor(ts=memories[-1].updated_at, id=memories[-1].id)
    if checkpoints:
        checkpoint_cursor = _Cursor(ts=checkpoints[-1].created_at, id=checkpoints[-1].id)
    conn.execute(
        "update public.project_profiles set memories_through = %s, memories_through_id = %s,"
        " checkpoints_through = %s, checkpoints_through_id = %s,"
        " version = version + 1, updated_at = %s where id = %s",
        (
            memory_cursor.ts,
            memory_cursor.id,
            checkpoint_cursor.ts,
            checkpoint_cursor.id,
            now,
            state.id,
        ),
    )
    return changed


def profile_repos(conn: Conn, user_id: UUID) -> list[str]:
    rows = conn.execute(
        "select repo from public.memories where user_id = %s and repo is not null"
        " union select repo from public.checkpoints where user_id = %s order by 1",
        (user_id, user_id),
    ).fetchall()
    return [str(r[0]) for r in rows]
