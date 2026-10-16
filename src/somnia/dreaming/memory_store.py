"""Memory writes used by dreaming (service connection, explicit user_id). No deletes."""

from datetime import datetime
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.connection import Conn
from somnia.providers.protocols import MemoryCandidate


class NearestMemory(BaseModel):
    id: UUID
    content: str
    similarity: float


class MemoryTarget(BaseModel):
    """Where a candidate lives: global memories carry no repo/branch."""

    user_id: UUID
    repo: str | None
    branch: str | None


def target_for(candidate: MemoryCandidate, user_id: UUID, repo: str, branch: str) -> MemoryTarget:
    if candidate.scope == "global":
        return MemoryTarget(user_id=user_id, repo=None, branch=None)
    if candidate.scope == "repo":
        return MemoryTarget(user_id=user_id, repo=repo, branch=None)
    return MemoryTarget(user_id=user_id, repo=repo, branch=branch)


def nearest_active(
    conn: Conn, target: MemoryTarget, scope: str, vector: str
) -> NearestMemory | None:
    with conn.cursor(row_factory=class_row(NearestMemory)) as cur:
        cur.execute(
            "select id, content, 1 - (embedding <=> %(v)s::extensions.vector) as similarity"
            " from public.memories where user_id = %(u)s and superseded_by is null"
            " and archived_at is null"
            " and scope = %(scope)s and repo is not distinct from %(repo)s"
            " and branch is not distinct from %(branch)s"
            " order by embedding <=> %(v)s::extensions.vector limit 1",
            {
                "v": vector,
                "u": target.user_id,
                "scope": scope,
                "repo": target.repo,
                "branch": target.branch,
            },
        )
        return cur.fetchone()


def insert_memory(
    conn: Conn,
    target: MemoryTarget,
    candidate: MemoryCandidate,
    content: str,
    vector: str,
    source_session_ids: list[UUID],
    now: datetime,
) -> UUID:
    row = conn.execute(
        "insert into public.memories (user_id, type, scope, repo, branch, content, embedding,"
        " confidence, source_session_ids, created_at, updated_at)"
        " values (%s, %s, %s, %s, %s, %s, %s::extensions.vector, %s, %s, %s, %s) returning id",
        (
            target.user_id,
            candidate.type,
            candidate.scope,
            target.repo,
            target.branch,
            content,
            vector,
            candidate.confidence,
            source_session_ids,
            now,
            now,
        ),
    ).fetchone()
    if row is None:
        raise RuntimeError("memory insert returned no row")
    return UUID(str(row[0]))


def merge_into(
    conn: Conn,
    memory_id: UUID,
    content: str,
    vector: str,
    candidate_confidence: float,
    boost: float,
    session_id: UUID,
    now: datetime,
) -> None:
    conn.execute(
        "update public.memories set content = %s, embedding = %s::extensions.vector,"
        " confidence = least(1.0, greatest(confidence, %s) + %s),"
        " source_session_ids = array(select distinct unnest(source_session_ids || %s::uuid)),"
        " updated_at = %s where id = %s",
        (content, vector, candidate_confidence, boost, session_id, now, memory_id),
    )


def supersede(
    conn: Conn,
    old_id: UUID,
    target: MemoryTarget,
    candidate: MemoryCandidate,
    content: str,
    vector: str,
    session_id: UUID,
    now: datetime,
) -> UUID:
    """Insert the replacement carrying the old provenance, then link old -> new."""
    row = conn.execute(
        "select source_session_ids from public.memories where id = %s for update", (old_id,)
    ).fetchone()
    previous: list[UUID] = list(row[0]) if row else []
    sources = [*previous, *([session_id] if session_id not in previous else [])]
    new_id = insert_memory(conn, target, candidate, content, vector, sources, now)
    conn.execute(
        "update public.memories set superseded_by = %s, updated_at = %s where id = %s",
        (new_id, now, old_id),
    )
    return new_id


def decay_unused(
    conn: Conn, user_id: UUID, now: datetime, after_days: float, factor: float, floor: float
) -> int:
    """Lower confidence of memories idle for `after_days` (since use, creation or last decay)."""
    cur = conn.execute(
        "update public.memories set confidence = greatest(%(floor)s, confidence * %(f)s),"
        " last_decayed_at = %(now)s, updated_at = %(now)s"
        " where user_id = %(u)s and superseded_by is null and archived_at is null"
        " and confidence > %(floor)s"
        " and greatest(coalesce(last_used_at, created_at),"
        "              coalesce(last_decayed_at, '-infinity'::timestamptz))"
        "     < %(now)s - make_interval(secs => %(secs)s)",
        {"u": user_id, "floor": floor, "f": factor, "now": now, "secs": after_days * 86400},
    )
    return cur.rowcount


def record_conflict(
    conn: Conn,
    *,
    user_id: UUID,
    repo: str | None,
    existing_id: UUID,
    candidate_id: UUID,
    outcome: str,
    rationale: str,
    session_id: UUID,
    now: datetime,
) -> UUID:
    """Provenance for every contradiction outcome. Only `flagged` stays open for a human."""
    row = conn.execute(
        "insert into public.memory_conflicts (user_id, repo, existing_memory_id,"
        " candidate_memory_id, outcome, rationale, session_id, status, created_at, resolved_at)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) returning id",
        (
            user_id,
            repo,
            existing_id,
            candidate_id,
            outcome,
            rationale,
            session_id,
            "open" if outcome == "flagged" else "resolved",
            now,
            None if outcome == "flagged" else now,
        ),
    ).fetchone()
    if row is None:
        raise RuntimeError("conflict insert returned no row")
    return UUID(str(row[0]))
