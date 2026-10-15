"""Session-start context ranking + token budget against real pgvector."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from somnia.db.connection import Conn
from somnia.db.vectors import to_vector_literal
from somnia.providers.fake import FakeEmbedder
from tests.conftest import FIXED_NOW, Device

pytestmark = pytest.mark.db


def _memory(
    conn: Conn,
    device: Device,
    content: str,
    confidence: float,
    age_days: float,
    repo: str = "acme/api",
    superseded: bool = False,
) -> uuid.UUID:
    vector = to_vector_literal(FakeEmbedder().embed([content])[0])
    created = FIXED_NOW - timedelta(days=age_days)
    row = conn.execute(
        "insert into public.memories (user_id, type, scope, repo, content, embedding,"
        " confidence, created_at) values (%s, 'fact', 'repo', %s, %s, %s::extensions.vector,"
        " %s, %s) returning id",
        (device.user_id, repo, content, vector, confidence, created),
    ).fetchone()
    assert row is not None
    if superseded:
        conn.execute("update public.memories set superseded_by = id where id = %s", (row[0],))
    return uuid.UUID(str(row[0]))


def test_context_ranks_by_similarity_confidence_recency(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    _memory(service_conn, device, "database migrations use supabase cli", 0.9, 0)
    _memory(service_conn, device, "database migrations use supabase cli locally", 0.9, 120)
    _memory(service_conn, device, "database migrations use supabase", 0.2, 0)
    _memory(service_conn, device, "frontend uses tailwind", 0.9, 0)
    _memory(service_conn, device, "database migrations use supabase cli", 0.9, 0, repo="other/repo")
    _memory(
        service_conn, device, "database migrations use supabase cli old", 1.0, 0, superseded=True
    )

    response = client.get(
        "/v1/context",
        headers=device.headers,
        params={
            "repo": "acme/api",
            "branch": "main",
            "query": "database migrations supabase cli",
            "k": 3,
            "token_budget": 1000,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    contents = [m["content"] for m in body["memories"]]
    assert contents[0] == "database migrations use supabase cli"
    assert "database migrations use supabase cli old" not in contents
    assert len(contents) == 3
    scores = [m["score"] for m in body["memories"]]
    assert scores == sorted(scores, reverse=True)
    for m in body["memories"]:
        assert m["score"] == pytest.approx(m["similarity"] * m["confidence"] * m["recency"])
    stale = next(m for m in body["memories"] if m["content"].endswith("locally"))
    assert stale["recency"] == pytest.approx(0.5**4)

    used = service_conn.execute(
        "select count(*) from public.memories where last_used_at is not null"
    ).fetchone()
    assert used is not None
    assert used[0] == 3


def test_context_packs_checkpoint_and_memories_under_token_budget(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    session = client.post(
        "/v1/sessions", headers=device.headers, json={"repo": "acme/api", "branch": "main"}
    ).json()
    client.post(
        f"/v1/sessions/{session['id']}/checkpoints",
        headers=device.headers,
        json={"goal": "add retries", "state": "wip", "next_steps": ["write test"]},
    )
    for i in range(5):
        _memory(service_conn, device, f"retries note {i} " + "x" * 160, 0.9, i)  # ~45 tokens

    body = client.get(
        "/v1/context",
        headers=device.headers,
        params={
            "repo": "acme/api",
            "branch": "main",
            "token_budget": 120,
            "k": 5,
        },
    ).json()
    assert body["checkpoint"]["goal"] == "add retries"
    assert body["tokens_used"] <= 120
    assert len(body["memories"]) == 2
    assert body["dropped"] == 3
