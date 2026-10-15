"""Greedy packing of ranked items under a token budget measured by a real tokenizer."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


@dataclass(frozen=True, slots=True)
class Packed[T]:
    items: list[T]
    tokens_used: int
    dropped: int


def pack_under_budget[T](
    items: Sequence[T],
    texts: Sequence[str],
    budget: int,
    counter: TokenCounter,
    reserved: int = 0,
) -> Packed[T]:
    """Keep items in rank order while they fit; skip ones that don't."""
    used = reserved
    kept: list[T] = []
    for item, text in zip(items, texts, strict=True):
        cost = counter.count(text)
        if used + cost <= budget:
            kept.append(item)
            used += cost
    return Packed(items=kept, tokens_used=used, dropped=len(items) - len(kept))
