"""Deterministic offline providers for tests and local dev."""

import hashlib
import math
import re
from collections.abc import Sequence

from somnia.db.vectors import EMBEDDING_DIM
from somnia.providers.protocols import (
    MemoryCandidate,
    MemoryScope,
    MemoryType,
    ProfileItem,
    ProfileSection,
    ReconcileDecision,
    SessionDigest,
)

_WORD = re.compile(r"[a-z0-9_]+")
_MESSAGE_LINE = re.compile(r"^\[message:(?P<role>\w+)\] (?P<text>.*)$")
_FILES_LINE = re.compile(r"^\[files_touched:\w+\] (?P<paths>.*)$")
_NEGATIONS = frozenset({"not", "never", "no", "dont", "don", "cannot"})
_NARROWER: dict[MemoryScope, MemoryScope] = {"global": "repo", "repo": "branch", "branch": "branch"}
_STACK_WORDS = frozenset(
    {
        "stack",
        "python",
        "fastapi",
        "postgres",
        "pgvector",
        "supabase",
        "next",
        "react",
        "typescript",
        "uv",
        "node",
        "framework",
        "library",
        "version",
        "runtime",
        "database",
    }
)
_TYPE_SECTION: dict[str, ProfileSection] = {
    "convention": "conventions",
    "decision": "decisions",
    "gotcha": "pitfalls",
    "todo": "open_work",
}


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


_TYPED_PREFIX = re.compile(r"\b(?P<kind>remember|convention|decision|gotcha|todo):\s*(?P<text>.+)$")


def _candidate(message: str) -> MemoryCandidate | None:
    """`remember: x` -> fact; `convention|decision|gotcha|todo: x` -> that type."""
    match = _TYPED_PREFIX.search(message)
    if match is None:
        return None
    kind = match["kind"]
    memory_type: MemoryType = "fact" if kind == "remember" else _MEMORY_TYPES[kind]
    return MemoryCandidate(
        type=memory_type, scope="repo", content=match["text"].strip(), confidence=0.6
    )


_MEMORY_TYPES: dict[str, MemoryType] = {
    "convention": "convention",
    "decision": "decision",
    "gotcha": "gotcha",
    "todo": "todo",
}


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
        memories = [candidate for m in messages if (candidate := _candidate(m)) is not None]
        next_steps = [m.split("next:", 1)[1].strip() for m in messages if "next:" in m]
        return SessionDigest(
            goal=messages[0] if messages else "(no messages)",
            state=messages[-1] if messages else "(no messages)",
            next_steps=next_steps,
            files_touched=sorted(set(files)),
            memories=memories,
        )

    def reconcile(
        self, existing: str, candidate: str, candidate_scope: MemoryScope
    ) -> ReconcileDecision:
        """merge near-duplicates; `only` -> coexist (narrower scope); a negation present in
        exactly one side -> flag; anything else -> supersede."""
        a, b = set(_tokens(existing)), set(_tokens(candidate))
        jaccard = len(a & b) / len(a | b) if a | b else 1.0
        if jaccard >= 0.6 and bool(a & _NEGATIONS) == bool(b & _NEGATIONS):
            merged = candidate if len(candidate) >= len(existing) else existing
            return ReconcileDecision(action="merge", content=merged, rationale="same fact")
        if "only" in b:
            return ReconcileDecision(
                action="coexist",
                content=candidate,
                narrowed_scope=_NARROWER[candidate_scope],
                rationale="candidate applies to a narrower context",
            )
        if bool(a & _NEGATIONS) != bool(b & _NEGATIONS):
            return ReconcileDecision(
                action="flag", content=candidate, rationale="statements contradict each other"
            )
        return ReconcileDecision(
            action="supersede", content=candidate, rationale="candidate is newer"
        )

    def classify_profile(self, items: Sequence[ProfileItem]) -> list[ProfileSection]:
        sections: list[ProfileSection] = []
        for item in items:
            if item.type in _TYPE_SECTION:
                sections.append(_TYPE_SECTION[item.type])
            elif set(_tokens(item.content)) & _STACK_WORDS:
                sections.append("stack")
            else:
                sections.append("architecture")
        return sections
