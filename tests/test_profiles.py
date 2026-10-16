"""Project profiles: built by dreaming, rebuilt incrementally, served first in /v1/context."""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from somnia.db.connection import Conn
from somnia.dreaming.dream import run_dream
from somnia.dreaming.policy import DreamPolicy
from somnia.dreaming.profile_builder import rebuild_profile
from somnia.providers.fake import FakeEmbedder, FakeLlm
from somnia.providers.protocols import ProfileItem, ProfileSection
from somnia.retrieval.tokenizer import TiktokenCounter
from tests.conftest import FIXED_NOW, Device, make_device, post_session

pytestmark = pytest.mark.db

POLICY = DreamPolicy(similarity_threshold=0.95)
COUNTER = TiktokenCounter("o200k_base")


class CountingLlm(FakeLlm):
    """Records what the profile builder asks to classify."""

    def __init__(self) -> None:
        self.classified: list[list[str]] = []

    def classify_profile(self, items: Sequence[ProfileItem]) -> list[ProfileSection]:
        self.classified.append([i.content for i in items])
        return super().classify_profile(items)


def _dream(conn: Conn, llm: FakeLlm, days: float = 0) -> None:
    run_dream(conn, llm, FakeEmbedder(), POLICY, FIXED_NOW + timedelta(days=days))


def _sections(client: TestClient, device: Device) -> dict[str, list[str]]:
    response = client.get(
        "/v1/admin/project-profile", headers=device.headers, params={"repo": "acme/api"}
    )
    assert response.status_code == 200, response.text
    out: dict[str, list[str]] = {}
    for entry in response.json()["entries"]:
        out.setdefault(entry["section"], []).append(entry["content"])
    return out


def test_profile_build_sections_and_provenance(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    sid = post_session(
        client,
        device,
        [
            "set up the service",
            "remember: the api uses fastapi with postgres and pgvector",
            "convention: every module is mypy strict",
            "decision: device tokens are stored hashed",
            "gotcha: rls needs set local role inside a transaction",
            "next: add the project page",
        ],
    )
    _dream(service_conn, FakeLlm())
    assert _sections(client, device) == {
        "stack": ["the api uses fastapi with postgres and pgvector"],
        "conventions": ["every module is mypy strict"],
        "decisions": ["device tokens are stored hashed"],
        "pitfalls": ["rls needs set local role inside a transaction"],
        "open_work": ["[main] add the project page"],
    }
    rows = service_conn.execute(
        "select section, source_memory_id is not null, source_checkpoint_id is not null,"
        " source_session_ids, confidence from public.project_profile_entries order by section"
    ).fetchall()
    for section, has_memory, has_checkpoint, sessions, confidence in rows:
        assert has_memory != has_checkpoint
        assert has_checkpoint == (section == "open_work")
        assert [str(s) for s in sessions] == [sid]
        assert 0 < confidence <= 1
    other = make_device(service_conn, "user-b")
    hidden = client.get(
        "/v1/admin/project-profile", headers=other.headers, params={"repo": "acme/api"}
    )
    assert hidden.status_code == 404  # RLS: user B never sees user A's profile


def test_profile_rebuild_is_incremental(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    llm = CountingLlm()
    post_session(client, device, ["one", "convention: use ruff", "decision: uv for deps"])
    _dream(service_conn, llm)
    assert [sorted(batch) for batch in llm.classified] == [["use ruff", "uv for deps"]]
    entry_times: dict[str, datetime] = dict(
        service_conn.execute(
            "select content, updated_at from public.project_profile_entries"
            " where source_memory_id is not null"
        ).fetchall()
    )

    _dream(service_conn, llm, 1)  # nothing changed: no classification, no writes
    assert len(llm.classified) == 1

    post_session(client, device, ["two", "gotcha: pgvector needs the extensions schema"])
    _dream(service_conn, llm, 2)
    assert llm.classified[-1] == ["pgvector needs the extensions schema"]
    after: dict[str, datetime] = dict(
        service_conn.execute(
            "select content, updated_at from public.project_profile_entries"
            " where source_memory_id is not null"
        ).fetchall()
    )
    assert after["use ruff"] == entry_times["use ruff"]  # untouched entries keep their stamp
    assert set(after) == {"use ruff", "uv for deps", "pgvector needs the extensions schema"}

    # Archiving a memory retires its entry (kept, not deleted) on the next rebuild.
    service_conn.execute(
        "update public.memories set archived_at = %s, updated_at = %s where content = 'use ruff'",
        (FIXED_NOW + timedelta(days=3), FIXED_NOW + timedelta(days=3)),
    )
    _dream(service_conn, llm, 3)
    assert "conventions" not in _sections(client, device)
    retired = service_conn.execute(
        "select count(*) from public.project_profile_entries"
        " where retired_at is not null and source_memory_id is not null"
    ).fetchone()
    assert retired is not None
    assert retired[0] == 1
    versions = service_conn.execute("select version from public.project_profiles").fetchone()
    assert versions is not None
    assert versions[0] == 3  # built, +gotcha, +retire; the no-op run did not bump it


def _context(client: TestClient, device: Device, budget: int) -> dict[str, Any]:
    response = client.get(
        "/v1/context",
        headers=device.headers,
        params={"repo": "acme/api", "branch": "main", "token_budget": budget, "query": "deploy"},
    )
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def test_context_orders_profile_checkpoint_memories_and_drops_lowest_first(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    post_session(client, device, ["ship it", "convention: squash merge", "next: tag release"])
    _dream(service_conn, FakeLlm())
    # A branch-scoped memory is not part of the repo profile, so it arrives as a memory item.
    service_conn.execute(
        "insert into public.memories (user_id, type, scope, repo, branch, content, embedding,"
        " confidence) values (%s, 'fact', 'branch', 'acme/api', 'main', %s, %s, 0.9)",
        (device.user_id, "deploy via fly on main", str(FakeEmbedder().embed(["deploy"])[0])),
    )

    full = _context(client, device, 4000)
    profile = full["profile"]
    checkpoint = full["checkpoint"]
    assert isinstance(profile, dict)
    assert isinstance(checkpoint, dict)
    profile_texts = [f"[{e['section']}] {e['content']}" for e in profile["entries"]]
    assert profile_texts == ["[conventions] squash merge", "[open_work] [main] tag release"]
    assert [m["content"] for m in full["memories"]] == ["deploy via fly on main"]
    profile_cost = sum(COUNTER.count(t) for t in profile_texts)
    checkpoint_cost = COUNTER.count(
        "\n".join(
            [f"goal: {checkpoint['goal']}", f"state: {checkpoint['state']}"]
            + [f"next: {s}" for s in checkpoint["next_steps"]]
        )
    )
    memory_cost = COUNTER.count("deploy via fly on main")
    assert full["tokens_used"] == profile_cost + checkpoint_cost + memory_cost
    assert full["dropped"] == 0

    no_memories = _context(client, device, profile_cost + checkpoint_cost)
    assert no_memories["checkpoint"] is not None
    assert no_memories["memories"] == []
    assert no_memories["dropped"] == 1

    profile_only = _context(client, device, profile_cost)
    assert profile_only["checkpoint"] is None
    assert profile_only["memories"] == []
    assert profile_only["dropped"] == 2
    assert profile_only["tokens_used"] == profile_cost

    lowest_profile_entry_dropped = _context(client, device, COUNTER.count(profile_texts[0]))
    kept = lowest_profile_entry_dropped["profile"]
    assert isinstance(kept, dict)
    assert [e["content"] for e in kept["entries"]] == ["squash merge"]


def _insert_memory(conn: Conn, user_id: object, memory_id: str, content: str) -> None:
    conn.execute(
        "insert into public.memories (id, user_id, type, scope, repo, branch, content, embedding,"
        " confidence, source_session_ids, created_at, updated_at) values (%s, %s, 'convention',"
        " 'repo', 'acme/api', 'main', %s, array_fill(0.1::real, array[1536])::extensions.vector,"
        " 0.8, '{}', %s, %s)",
        (memory_id, user_id, content, FIXED_NOW, FIXED_NOW),
    )


def test_profile_cursor_keeps_tied_timestamps(device: Device, service_conn: Conn) -> None:
    ids = [f"00000000-0000-4000-8000-00000000000{n}" for n in range(1, 5)]
    for n, memory_id in enumerate(ids[:3]):
        _insert_memory(service_conn, device.user_id, memory_id, f"tied rule {n}")
    assert rebuild_profile(service_conn, device.user_id, "acme/api", FakeLlm(), FIXED_NOW) == 3
    cursor = service_conn.execute(
        "select memories_through, memories_through_id::text from public.project_profiles"
    ).fetchone()
    assert cursor == (FIXED_NOW, ids[2])

    # Same timestamp as the cursor, larger id: a timestamp-only `>` cursor would skip it.
    _insert_memory(service_conn, device.user_id, ids[3], "tied rule late")
    assert rebuild_profile(service_conn, device.user_id, "acme/api", FakeLlm(), FIXED_NOW) == 1
    contents = {
        r[0]
        for r in service_conn.execute(
            "select content from public.project_profile_entries where retired_at is null"
        ).fetchall()
    }
    assert contents == {"tied rule 0", "tied rule 1", "tied rule 2", "tied rule late"}
    assert rebuild_profile(service_conn, device.user_id, "acme/api", FakeLlm(), FIXED_NOW) == 0
