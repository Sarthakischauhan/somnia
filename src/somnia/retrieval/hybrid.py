"""Hybrid retrieval: dreamt memories ranked together with not-yet-dreamt chunks.

Chunks make a session's new context searchable before the next dream. They are weighted
below memories (`chunk_weight` stands in for confidence) and dropped when a candidate
memory already says the same thing (cosine >= `dedupe_similarity`).
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Literal
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.connection import Conn
from somnia.providers.protocols import MemoryScope, MemoryType
from somnia.retrieval.ranking import RankedMemory, recency_factor


class ContextItem(BaseModel):
    source: Literal["memory", "chunk"]
    id: str
    type: MemoryType | None
    scope: MemoryScope | None
    content: str
    confidence: float
    similarity: float
    recency: float
    score: float
    session_id: UUID | None


class ChunkCandidateRow(BaseModel):
    id: int
    session_id: UUID
    content: str
    created_at: datetime
    similarity: float
    memory_overlap: float


def undreamt_chunks(
    conn: Conn, vector: str, repo: str, memory_ids: Sequence[UUID], limit: int
) -> list[ChunkCandidateRow]:
    """Chunks of events past their session's dream watermark (RLS-scoped)."""
    with conn.cursor(row_factory=class_row(ChunkCandidateRow)) as cur:
        cur.execute(
            "select c.id, c.session_id, c.content, c.created_at,"
            " 1 - (c.embedding <=> %(v)s::extensions.vector) as similarity,"
            " coalesce((select max(1 - (m.embedding <=> c.embedding)) from public.memories m"
            "   where m.id = any(%(mids)s)), 0) as memory_overlap"
            " from public.chunks c join public.events e on e.id = c.event_id"
            " join public.sessions s on s.id = c.session_id"
            " where s.repo = %(repo)s and e.seq > s.dreamed_through_seq"
            " order by c.embedding <=> %(v)s::extensions.vector limit %(limit)s",
            {"v": vector, "repo": repo, "mids": list(memory_ids), "limit": limit},
        )
        return cur.fetchall()


def memory_item(memory: RankedMemory) -> ContextItem:
    return ContextItem(
        source="memory",
        id=str(memory.id),
        type=memory.type,
        scope=memory.scope,
        content=memory.content,
        confidence=memory.confidence,
        similarity=memory.similarity,
        recency=memory.recency,
        score=memory.score,
        session_id=None,
    )


def chunk_items(
    rows: Sequence[ChunkCandidateRow],
    now: datetime,
    half_life_days: float,
    weight: float,
    dedupe_similarity: float,
) -> list[ContextItem]:
    items = []
    for row in rows:
        if row.memory_overlap >= dedupe_similarity:
            continue
        similarity = max(row.similarity, 0.0)
        recency = recency_factor(row.created_at, now, half_life_days)
        items.append(
            ContextItem(
                source="chunk",
                id=f"chunk:{row.id}",
                type=None,
                scope=None,
                content=row.content,
                confidence=weight,
                similarity=similarity,
                recency=recency,
                score=similarity * weight * recency,
                session_id=row.session_id,
            )
        )
    return items


def merge_ranked(
    memories: Sequence[RankedMemory],
    chunks: Sequence[ContextItem],
    k: int,
    exclude_memory_ids: frozenset[UUID] = frozenset(),
) -> list[ContextItem]:
    """Top-k across both sources. Memories already present as profile entries are skipped."""
    combined = [memory_item(m) for m in memories if m.id not in exclude_memory_ids]
    combined.extend(chunks)
    return sorted(combined, key=lambda item: item.score, reverse=True)[:k]
