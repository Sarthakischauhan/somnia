"""Deterministic offline providers for tests and local dev."""

import hashlib
import math
import re
from collections.abc import Sequence

from somnia.db.vectors import EMBEDDING_DIM
from somnia.providers.protocols import MemoryCandidate, MergeDecision, SessionDigest

_WORD = re.compile(r"[a-z0-9_]+")
_MESSAGE_LINE = re.compile(r"^\[message:(?P<role>\w+)\] (?P<text>.*)$")
_FILES_LINE = re.compile(r"^\[files_touched:\w+\] (?P<paths>.*)$")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


class FakeEmbedder:
    """Hashed bag-of-words: texts sharing words get high cosine similarity."""

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * EMBEDDING_DIM
        for token in _tokens(text) or ["<empty>"]:
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIM
            vec[index] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


class FakeLlm:
    """Rule-based digest: `remember: ...` lines become memories, `next: ...` next steps."""

    def summarize_session(self, transcript: str) -> SessionDigest:
        messages: list[str] = []
        files: list[str] = []
        for line in transcript.splitlines():
            if match := _MESSAGE_LINE.match(line):
                messages.append(match["text"])
            elif match := _FILES_LINE.match(line):
                files.extend(p.strip() for p in match["paths"].split(",") if p.strip())
        memories = [
            MemoryCandidate(
                type="fact",
                scope="repo",
                content=m.split("remember:", 1)[1].strip(),
                confidence=0.6,
            )
            for m in messages
            if "remember:" in m
        ]
        next_steps = [m.split("next:", 1)[1].strip() for m in messages if "next:" in m]
        return SessionDigest(
            goal=messages[0] if messages else "(no messages)",
            state=messages[-1] if messages else "(no messages)",
            next_steps=next_steps,
            files_touched=sorted(set(files)),
            memories=memories,
        )

    def reconcile(self, existing: str, candidate: str) -> MergeDecision:
        a, b = set(_tokens(existing)), set(_tokens(candidate))
        jaccard = len(a & b) / len(a | b) if a | b else 1.0
        if jaccard >= 0.6:
            merged = candidate if len(candidate) >= len(existing) else existing
            return MergeDecision(action="merge", content=merged)
        return MergeDecision(action="supersede", content=candidate)
