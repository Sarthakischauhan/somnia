"""Greedy packing of ranked items under a token budget."""

import math
from collections.abc import Sequence
from dataclasses import dataclass


def estimate_tokens(text: str) -> int:
    """~4 characters per token; conservative and provider-independent."""
    return max(1, math.ceil(len(text) / 4))


@dataclass(frozen=True, slots=True)
class Packed[T]:
    items: list[T]
    tokens_used: int
    dropped: int


def pack_under_budget[T](
    items: Sequence[T], texts: Sequence[str], budget: int, reserved: int = 0
) -> Packed[T]:
    """Keep items in rank order while they fit; skip ones that don't."""
    used = reserved
    kept: list[T] = []
    for item, text in zip(items, texts, strict=True):
        cost = estimate_tokens(text)
        if used + cost <= budget:
            kept.append(item)
            used += cost
    return Packed(items=kept, tokens_used=used, dropped=len(items) - len(kept))
