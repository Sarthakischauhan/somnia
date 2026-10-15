"""Memory ranking: vector similarity x confidence x recency decay."""

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from somnia.providers.protocols import MemoryScope, MemoryType


class MemoryCandidateRow(BaseModel):
    id: UUID
    type: MemoryType
    scope: MemoryScope
    content: str
    confidence: float
    similarity: float
    created_at: datetime
    last_used_at: datetime | None


class RankedMemory(BaseModel):
    id: UUID
    type: MemoryType
    scope: MemoryScope
    content: str
    confidence: float
    similarity: float
    recency: float
    score: float


def recency_factor(last_activity: datetime, now: datetime, half_life_days: float) -> float:
    """Exponential decay: 1.0 now, 0.5 after one half-life."""
    age_days = max((now - last_activity).total_seconds(), 0.0) / 86400.0
    return float(0.5 ** (age_days / half_life_days))


def rank_memories(
    rows: Sequence[MemoryCandidateRow], now: datetime, half_life_days: float
) -> list[RankedMemory]:
    ranked = []
    for row in rows:
        recency = recency_factor(row.last_used_at or row.created_at, now, half_life_days)
        similarity = max(row.similarity, 0.0)
        ranked.append(
            RankedMemory(
                id=row.id,
                type=row.type,
                scope=row.scope,
                content=row.content,
                confidence=row.confidence,
                similarity=similarity,
                recency=recency,
                score=similarity * row.confidence * recency,
            )
        )
    return sorted(ranked, key=lambda m: m.score, reverse=True)
