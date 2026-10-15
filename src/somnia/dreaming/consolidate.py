"""Consolidate one session's new events into a checkpoint and memories."""

from datetime import datetime
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel, JsonValue

from somnia.db.connection import Conn
from somnia.db.vectors import to_vector_literal
from somnia.dreaming.memory_store import (
    insert_memory,
    merge_into,
    nearest_active,
    supersede,
    target_for,
)
from somnia.dreaming.policy import DreamPolicy
from somnia.dreaming.run_log import DreamCounts
from somnia.ingest.event_models import EVENT_ADAPTER, GitRefEvent
from somnia.ingest.event_text import render_event
from somnia.ingest.redaction import redact_secrets
from somnia.providers.protocols import Embedder, Llm, MemoryCandidate
from somnia.store.checkpoints import CheckpointDraft, create_checkpoint


class SessionToDream(BaseModel):
    id: UUID
    user_id: UUID
    repo: str
    branch: str
    git_ref: str | None
    dreamed_through_seq: int


class _RawEvent(BaseModel):
    seq: int
    kind: str
    payload: dict[str, JsonValue]


def sessions_needing_dream(conn: Conn, user_id: UUID) -> list[SessionToDream]:
    with conn.cursor(row_factory=class_row(SessionToDream)) as cur:
        cur.execute(
            "select s.id, s.user_id, s.repo, s.branch, s.git_ref, s.dreamed_through_seq"
            " from public.sessions s where s.user_id = %s and exists (select 1"
            "   from public.events e where e.session_id = s.id and e.seq > s.dreamed_through_seq)"
            " order by s.started_at for update of s skip locked",
            (user_id,),
        )
        return cur.fetchall()


def consolidate_session(
    conn: Conn,
    session: SessionToDream,
    llm: Llm,
    embedder: Embedder,
    policy: DreamPolicy,
    counts: DreamCounts,
    now: datetime,
) -> None:
    with conn.cursor(row_factory=class_row(_RawEvent)) as cur:
        cur.execute(
            "select seq, kind, payload from public.events where session_id = %s and seq > %s"
            " order by seq",
            (session.id, session.dreamed_through_seq),
        )
        raw = cur.fetchall()
    if not raw:
        return
    events = [EVENT_ADAPTER.validate_python(r.model_dump()) for r in raw]
    transcript = redact_secrets("\n".join(render_event(e) for e in events)).text
    digest = llm.summarize_session(transcript)
    pushed = any(isinstance(e, GitRefEvent) and e.payload.pushed for e in events)
    create_checkpoint(
        conn,
        user_id=session.user_id,
        session_id=session.id,
        repo=session.repo,
        branch=session.branch,
        source="dream",
        draft=CheckpointDraft(
            goal=digest.goal or "(unknown)",
            state=digest.state or "(unknown)",
            next_steps=digest.next_steps,
            files_touched=digest.files_touched,
            git_ref=session.git_ref,
            pushed=pushed,
        ),
    )
    counts.checkpoints_created += 1
    for candidate in digest.memories:
        _apply_candidate(conn, session, candidate, llm, embedder, policy, counts, now)
    conn.execute(
        "update public.sessions set dreamed_through_seq = %s where id = %s",
        (raw[-1].seq, session.id),
    )
    counts.sessions_processed += 1


def _apply_candidate(
    conn: Conn,
    session: SessionToDream,
    candidate: MemoryCandidate,
    llm: Llm,
    embedder: Embedder,
    policy: DreamPolicy,
    counts: DreamCounts,
    now: datetime,
) -> None:
    content = redact_secrets(candidate.content).text
    vector = to_vector_literal(embedder.embed([content])[0])
    target = target_for(candidate, session.user_id, session.repo, session.branch)
    nearest = nearest_active(conn, target, candidate.scope, vector)
    if nearest is None or nearest.similarity < policy.similarity_threshold:
        insert_memory(conn, target, candidate, content, vector, [session.id], now)
        counts.memories_added += 1
        return
    decision = llm.reconcile(nearest.content, content)
    decided = redact_secrets(decision.content).text
    decided_vector = (
        vector if decided == content else to_vector_literal(embedder.embed([decided])[0])
    )
    if decision.action == "merge":
        merge_into(
            conn,
            nearest.id,
            decided,
            decided_vector,
            candidate.confidence,
            policy.merge_confidence_boost,
            session.id,
            now,
        )
        counts.memories_merged += 1
    elif decision.action == "supersede":
        supersede(conn, nearest.id, target, candidate, decided, decided_vector, session.id, now)
        counts.memories_superseded += 1
    else:
        insert_memory(conn, target, candidate, decided, decided_vector, [session.id], now)
        counts.memories_added += 1
