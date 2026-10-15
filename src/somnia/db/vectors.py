"""pgvector text literals (avoids an untyped adapter dependency)."""

from collections.abc import Sequence

EMBEDDING_DIM = 1536


def to_vector_literal(values: Sequence[float]) -> str:
    if len(values) != EMBEDDING_DIM:
        raise ValueError(f"expected {EMBEDDING_DIM}-d embedding, got {len(values)}")
    return "[" + ",".join(f"{v:.7g}" for v in values) + "]"
