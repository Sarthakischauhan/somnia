"""Session-start context: latest open checkpoint + top-k memories under a token budget."""

from datetime import datetime

from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.connection import Conn
from somnia.db.vectors import to_vector_literal
from somnia.providers.protocols import Embedder
from somnia.records import CheckpointRecord
from somnia.retrieval.packing import pack_under_budget
from somnia.retrieval.ranking import MemoryCandidateRow, RankedMemory, rank_memories
from somnia.retrieval.tokenizer import TiktokenCounter, TokenEncoding
from somnia.store.checkpoints import latest_open_checkpoint


class ContextRequest(BaseModel):
    repo: str
    branch: str
    token_budget: int
    k: int
    query: str | None = None


class SessionContext(BaseModel):
    checkpoint: CheckpointRecord | None
    memories: list[RankedMemory]
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


def build_session_context(
    conn: Conn,
    embedder: Embedder,
    request: ContextRequest,
    now: datetime,
    half_life_days: float,
    candidate_pool: int,
    counter: TiktokenCounter,
) -> SessionContext:
    """Must run inside user_transaction (RLS scopes every query to the caller)."""
    checkpoint = latest_open_checkpoint(conn, request.repo, request.branch)
    query = request.query or (
        checkpoint_text(checkpoint) if checkpoint else f"{request.repo} {request.branch}"
    )
    vector = to_vector_literal(embedder.embed([query])[0])
    with conn.cursor(row_factory=class_row(MemoryCandidateRow)) as cur:
        cur.execute(
            "select id, type, scope, content, confidence, created_at, last_used_at,"
            " 1 - (embedding <=> %(v)s::extensions.vector) as similarity"
            " from public.memories where superseded_by is null and archived_at is null"
            " and (scope = 'global' or (repo = %(repo)s"
            "      and (scope = 'repo' or branch = %(branch)s)))"
            " order by embedding <=> %(v)s::extensions.vector limit %(limit)s",
            {"v": vector, "repo": request.repo, "branch": request.branch, "limit": candidate_pool},
        )
        rows = cur.fetchall()
    top = rank_memories(rows, now, half_life_days)[: request.k]
    reserved = counter.count(checkpoint_text(checkpoint)) if checkpoint else 0
    if reserved > request.token_budget:
        checkpoint, reserved = None, 0
    packed = pack_under_budget(
        top, [m.content for m in top], request.token_budget, counter, reserved
    )
    if packed.items:
        conn.execute(
            "update public.memories set last_used_at = %s, use_count = use_count + 1"
            " where id = any(%s)",
            (now, [m.id for m in packed.items]),
        )
    return SessionContext(
        checkpoint=checkpoint,
        memories=packed.items,
        token_budget=request.token_budget,
        token_encoding=counter.encoding_name,
        tokens_used=packed.tokens_used,
        dropped=packed.dropped,
    )
