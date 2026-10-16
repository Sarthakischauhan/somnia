"""Hybrid retrieval: undreamt chunks are searchable immediately, weighted below memories,
deduped against memories, and marked with their source."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from somnia.db.connection import Conn
from somnia.dreaming.dream import run_dream
from somnia.dreaming.policy import DreamPolicy
from somnia.ingest.pipeline import process_pending_events
from somnia.providers.fake import FakeEmbedder, FakeLlm
from somnia.retrieval.hybrid import ChunkCandidateRow, chunk_items, merge_ranked
from somnia.retrieval.ranking import RankedMemory
from tests.conftest import FIXED_NOW, Device, post_session


def _memory(score_similarity: float, confidence: float) -> RankedMemory:
    return RankedMemory(
        id=uuid.uuid4(),
        type="fact",
        scope="repo",
        content="memory",
        confidence=confidence,
        similarity=score_similarity,
        recency=1.0,
        score=score_similarity * confidence,
    )


def _chunk(similarity: float, overlap: float) -> ChunkCandidateRow:
    return ChunkCandidateRow(
        id=7,
        session_id=uuid.uuid4(),
        content="chunk",
        created_at=FIXED_NOW,
        similarity=similarity,
        memory_overlap=overlap,
    )


def test_chunks_are_weighted_below_memories_and_deduped() -> None:
    (chunk,) = chunk_items([_chunk(0.8, 0.1)], FIXED_NOW, 30, 0.5, 0.9)
    assert (chunk.source, chunk.id, chunk.confidence) == ("chunk", "chunk:7", 0.5)
    assert chunk.score == pytest.approx(0.4)
    # Equal similarity: a full-confidence memory outranks the chunk.
    ranked = merge_ranked([_memory(0.8, 1.0)], [chunk], k=5)
    assert [i.source for i in ranked] == ["memory", "chunk"]
    # A chunk that restates a candidate memory is dropped.
    assert chunk_items([_chunk(0.8, 0.95)], FIXED_NOW, 30, 0.5, 0.9) == []
    assert merge_ranked([_memory(0.8, 1.0)], [chunk], k=1)[0].source == "memory"
    older = chunk_items([_chunk(0.8, 0.0)], FIXED_NOW + timedelta(days=30), 30, 0.5, 0.9)
    assert older[0].score == pytest.approx(0.2)  # recency decays chunks like memories


def _context(client: TestClient, device: Device, query: str) -> list[dict[str, object]]:
    response = client.get(
        "/v1/context",
        headers=device.headers,
        params={"repo": "acme/api", "branch": "main", "query": query},
    )
    assert response.status_code == 200, response.text
    items = response.json()["memories"]
    assert isinstance(items, list)
    return items


@pytest.mark.db
def test_undreamt_chunks_are_searchable_until_dreamt(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    session_id = post_session(client, device, ["deploy with fly launch to staging"])
    assert _context(client, device, "deploy fly staging") == []  # not yet chunked
    while process_pending_events(service_conn, FakeEmbedder(), 100, 1200, 150):
        pass

    (item,) = _context(client, device, "deploy fly staging")
    assert item["source"] == "chunk"
    assert item["session_id"] == session_id
    assert item["type"] is None
    assert item["confidence"] == pytest.approx(0.5)
    assert "deploy with fly launch to staging" in str(item["content"])

    # Another user never sees these chunks (RLS).
    from tests.conftest import make_device

    other = make_device(service_conn, "user-b")
    other_view = client.get(
        "/v1/context",
        headers=other.headers,
        params={"repo": "acme/api", "branch": "main", "query": "deploy fly staging"},
    )
    assert other_view.json()["memories"] == []

    # Same content as a memory: the chunk is deduped and only the memory is returned.
    chunk_text = str(item["content"])
    service_conn.execute(
        "insert into public.memories (user_id, type, scope, repo, branch, content, embedding,"
        " confidence) values (%s, 'fact', 'branch', 'acme/api', 'main', %s, %s, 0.8)",
        (device.user_id, chunk_text, str(FakeEmbedder().embed([chunk_text])[0])),
    )
    assert [i["source"] for i in _context(client, device, "deploy fly staging")] == ["memory"]

    # Once dreamt, the session's chunks leave the hybrid pool.
    service_conn.execute("update public.memories set archived_at = now()")
    run_dream(service_conn, FakeLlm(), FakeEmbedder(), DreamPolicy(), FIXED_NOW)
    assert [i["source"] for i in _context(client, device, "deploy fly staging")] == []
