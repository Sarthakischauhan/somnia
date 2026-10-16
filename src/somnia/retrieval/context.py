"""Session-start context: project profile, then the latest open checkpoint, then the
top-k memories and undreamt chunks, packed under a tiktoken budget in that priority order
(when something must go, the lowest-priority pieces are dropped first)."""

from datetime import datetime
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.connection import Conn
from somnia.db.vectors import to_vector_literal
from somnia.providers.protocols import Embedder
from somnia.records import CheckpointRecord
from somnia.retrieval.hybrid import ContextItem, chunk_items, merge_ranked, undreamt_chunks
from somnia.retrieval.packing import pack_under_budget
from somnia.retrieval.profile_context import ProjectProfileOut, entry_text, load_profile
from somnia.retrieval.ranking import MemoryCandidateRow, rank_memories
from somnia.retrieval.tokenizer import TiktokenCounter, TokenEncoding
from somnia.store.checkpoints import latest_open_checkpoint


class ContextRequest(BaseModel):
    repo: str
    branch: str
    token_budget: int
    k: int
    query: str | None = None


class RetrievalWeights(BaseModel):
    half_life_days: float
    candidate_pool: int
    chunk_weight: float
    chunk_dedupe_similarity: float


class SessionContext(BaseModel):
    profile: ProjectProfileOut | None
    checkpoint: CheckpointRecord | None
    memories: list[ContextItem]
    token_budget: int
    token_encoding: TokenEncoding
    tokens_used: int
    dropped: int


def checkpoint_text(checkpoint: CheckpointRecord) -> str:
    return "\n".join(
        [
            f"goal: {checkpoint.goal}",
            f"state: {checkpoint.state}",
            *(f"next: {s}" for s in checkpoint.next_steps),
        ]
    )


def _memory_candidates(
    conn: Conn, vector: str, request: ContextRequest, limit: int
) -> list[MemoryCandidateRow]:
    with conn.cursor(row_factory=class_row(MemoryCandidateRow)) as cur:
        cur.execute(
            "select id, type, scope, content, confidence, created_at, last_used_at,"
            " 1 - (embedding <=> %(v)s::extensions.vector) as similarity"
            " from public.memories where superseded_by is null and archived_at is null"
            " and (scope = 'global' or (repo = %(repo)s"
            "      and (scope = 'repo' or branch = %(branch)s)))"
            " order by embedding <=> %(v)s::extensions.vector limit %(limit)s",
            {"v": vector, "repo": request.repo, "branch": request.branch, "limit": limit},
        )
        return cur.fetchall()


def build_session_context(
    conn: Conn,
    embedder: Embedder,
    request: ContextRequest,
    now: datetime,
    weights: RetrievalWeights,
    counter: TiktokenCounter,
) -> SessionContext:
    """Must run inside user_transaction (RLS scopes every query to the caller)."""
    profile = load_profile(conn, request.repo)
    checkpoint = latest_open_checkpoint(conn, request.repo, request.branch)
    query = request.query or (
        checkpoint_text(checkpoint) if checkpoint else f"{request.repo} {request.branch}"
    )
    vector = to_vector_literal(embedder.embed([query])[0])
    memory_rows = _memory_candidates(conn, vector, request, weights.candidate_pool)
    chunk_rows = undreamt_chunks(
        conn, vector, request.repo, [m.id for m in memory_rows], weights.candidate_pool
    )
    entries = profile.entries if profile else []
    packed_profile = pack_under_budget(
        entries, [entry_text(e) for e in entries], request.token_budget, counter
    )
    in_profile = frozenset(
        e.source_memory_id for e in packed_profile.items if e.source_memory_id is not None
    )
    ranked = merge_ranked(
        rank_memories(memory_rows, now, weights.half_life_days),
        chunk_items(
            chunk_rows,
            now,
            weights.half_life_days,
            weights.chunk_weight,
            weights.chunk_dedupe_similarity,
        ),
        request.k,
        in_profile,
    )
    used = packed_profile.tokens_used
    dropped = packed_profile.dropped
    if checkpoint is not None:
        cost = counter.count(checkpoint_text(checkpoint))
        if used + cost <= request.token_budget:
            used += cost
        else:
            checkpoint, dropped = None, dropped + 1
    packed_items = pack_under_budget(
        ranked, [i.content for i in ranked], request.token_budget, counter, used
    )
    used_memory_ids = [UUID(i.id) for i in packed_items.items if i.source == "memory"]
    if used_memory_ids:
        conn.execute(
            "update public.memories set last_used_at = %s, use_count = use_count + 1"
            " where id = any(%s)",
            (now, used_memory_ids),
        )
    return SessionContext(
        profile=(
            profile.model_copy(update={"entries": packed_profile.items})
            if profile is not None and packed_profile.items
            else None
        ),
        checkpoint=checkpoint,
        memories=packed_items.items,
        token_budget=request.token_budget,
        token_encoding=counter.encoding_name,
        tokens_used=packed_items.tokens_used,
        dropped=dropped + packed_items.dropped,
    )
