"""Consolidate one session's new events into a checkpoint and memories."""

from datetime import datetime
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel, JsonValue

from somnia.config import DreamPolicy
from somnia.db.client import Conn
from somnia.db.vectors import to_vector_literal
from somnia.ingestion.event_models import EVENT_ADAPTER, GitRefEvent
from somnia.ingestion.event_text import render_event
from somnia.ingestion.redaction import redact_secrets
from somnia.memory.inference import SymphonyLlm
from somnia.memory.memory_store import (
    identical_active,
    insert_memory,
    merge_into,
    nearest_active,
    record_conflict,
    supersede,
    target_for,
)
from somnia.memory.models import Embedder, Llm, MemoryCandidate
from somnia.memory.run_log import DreamCounts
from somnia.sessions.continuity import CheckpointDraft, create_checkpoint


class SessionToDream(BaseModel):
    id: UUID
    user_id: UUID
    repo: str
    branch: str
    git_ref: str | None


class _RawEvent(BaseModel):
    id: int
    seq: int
    kind: str
    payload: dict[str, JsonValue]


def sessions_needing_dream(
    conn: Conn, user_id: UUID, repo: str | None = None
) -> list[SessionToDream]:
    """`repo` limits an event-triggered run to that repo; None means every repo."""
    with conn.cursor(row_factory=class_row(SessionToDream)) as cur:
        cur.execute(
            "select s.id, s.user_id, s.repo, s.branch, s.git_ref"
            " from public.sessions s where s.user_id = %s"
            " and (%s::text is null or s.repo = %s::text) and exists (select 1"
            "   from public.events e where e.session_id = s.id and not e.dreamed)"
            " order by s.started_at, s.id",
            (user_id, repo, repo),
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
            "select id, seq, kind, payload from public.events where session_id = %s and not dreamed"
            " order by seq",
            (session.id,),
        )
        raw = cur.fetchall()
    if not raw:
        return
    events = [EVENT_ADAPTER.validate_python(r.model_dump(exclude={"id"})) for r in raw]
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
        "update public.events set dreamed = true where id = any(%s)", ([event.id for event in raw],)
    )
    conn.execute(
        "update public.sessions set dreamed_through_seq = greatest(dreamed_through_seq, %s)"
        " where id = (select id from public.sessions where id = %s"
        " for no key update skip locked)",
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
    target = target_for(candidate, session.user_id, session.repo, session.branch)
    duplicate = identical_active(conn, target, candidate, content)
    if duplicate is not None:
        merge_into(
            conn,
            duplicate,
            content,
            None,
            candidate.confidence,
            policy.merge_confidence_boost,
            session.id,
            now,
        )
        counts.memories_merged += 1
        return
    vector = to_vector_literal(embedder.embed([content])[0])
    nearest = nearest_active(conn, target, candidate.scope, vector)
    if nearest is None or nearest.similarity < policy.similarity_threshold:
        insert_memory(conn, target, candidate, content, vector, [session.id], now)
        counts.memories_added += 1
        return
    decision = llm.reconcile(nearest.content, content, candidate.scope)
    if decision.action == "flag" and isinstance(llm, SymphonyLlm):

        def read_evidence() -> str:
            rows = conn.execute(
                "select kind, left(payload::text, 1000) from public.events"
                " where user_id = %s and (session_id = %s or session_id in ("
                " select unnest(source_session_ids) from public.memories"
                " where id = %s and user_id = %s)) order by id desc limit 12",
                (session.user_id, session.id, nearest.id, session.user_id),
            ).fetchall()
            return redact_secrets(
                "\n".join(f"{kind}: {body}" for kind, body in reversed(rows))
            ).text

        decision = (
            llm.investigate_conflict(nearest.content, content, candidate.scope, read_evidence)
            or decision
        )
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
        return
    if decision.action == "add":
        insert_memory(conn, target, candidate, decided, decided_vector, [session.id], now)
        counts.memories_added += 1
        return
    if decision.action == "supersede":
        new_id = supersede(
            conn, nearest.id, target, candidate, decided, decided_vector, session.id, now
        )
        outcome = "superseded"
        counts.memories_superseded += 1
    elif decision.action == "coexist":
        narrowed = candidate.model_copy(
            update={"scope": decision.narrowed_scope or candidate.scope}
        )
        narrow_target = target_for(narrowed, session.user_id, session.repo, session.branch)
        new_id = insert_memory(
            conn, narrow_target, narrowed, decided, decided_vector, [session.id], now
        )
        outcome = "coexist"
        counts.memories_coexisting += 1
    else:  # flag: keep both, a human decides
        new_id = insert_memory(conn, target, candidate, decided, decided_vector, [session.id], now)
        outcome = "flagged"
        counts.conflicts_flagged += 1
    record_conflict(
        conn,
        user_id=session.user_id,
        repo=session.repo,
        existing_id=nearest.id,
        candidate_id=new_id,
        outcome=outcome,
        rationale=decision.rationale,
        session_id=session.id,
        now=now,
    )
