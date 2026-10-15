import uuid
from datetime import UTC, datetime, timedelta

import pytest

from somnia.retrieval.packing import estimate_tokens, pack_under_budget
from somnia.retrieval.ranking import MemoryCandidateRow, rank_memories, recency_factor

NOW = datetime(2026, 10, 15, tzinfo=UTC)


def _row(content: str, similarity: float, confidence: float, age_days: float) -> MemoryCandidateRow:
    return MemoryCandidateRow(
        id=uuid.uuid4(),
        type="fact",
        scope="repo",
        content=content,
        confidence=confidence,
        similarity=similarity,
        created_at=NOW - timedelta(days=age_days),
        last_used_at=None,
    )


def test_recency_half_life() -> None:
    assert recency_factor(NOW, NOW, 30) == pytest.approx(1.0)
    assert recency_factor(NOW - timedelta(days=30), NOW, 30) == pytest.approx(0.5)
    assert recency_factor(NOW + timedelta(days=1), NOW, 30) == pytest.approx(1.0)


def test_score_is_product_of_similarity_confidence_recency() -> None:
    rows = [
        _row("similar but stale", similarity=0.9, confidence=0.9, age_days=90),  # .9*.9*.125
        _row("fresh and confident", similarity=0.7, confidence=0.9, age_days=0),  # .63
        _row("fresh low confidence", similarity=0.9, confidence=0.3, age_days=0),  # .27
    ]
    ranked = rank_memories(rows, NOW, half_life_days=30)
    assert [m.content for m in ranked] == [
        "fresh and confident",
        "fresh low confidence",
        "similar but stale",
    ]
    assert ranked[0].score == pytest.approx(0.7 * 0.9 * 1.0)
    assert ranked[2].score == pytest.approx(0.9 * 0.9 * 0.125)


def test_negative_similarity_clamps_to_zero() -> None:
    assert rank_memories([_row("x", -0.4, 1.0, 0)], NOW, 30)[0].score == 0.0


def test_packing_respects_budget_and_skips_oversized() -> None:
    texts = ["a" * 40, "b" * 400, "c" * 40]  # 10, 100, 10 tokens
    packed = pack_under_budget(texts, texts, budget=30, reserved=5)
    assert packed.items == ["a" * 40, "c" * 40]
    assert packed.tokens_used == 25
    assert packed.dropped == 1
    assert estimate_tokens("") == 1
