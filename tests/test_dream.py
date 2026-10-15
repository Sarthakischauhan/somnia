"""Dream run: add, merge and supersede with provenance; dream_runs logged."""

import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from somnia.db.connection import Conn
from somnia.dreaming.dream import run_dream
from somnia.dreaming.policy import DreamPolicy
from somnia.providers.fake import FakeEmbedder, FakeLlm
from tests.conftest import FIXED_NOW, Device

pytestmark = pytest.mark.db

POLICY = DreamPolicy(similarity_threshold=0.5)


def _run_session(client: TestClient, device: Device, messages: list[str]) -> str:
    session = client.post(
        "/v1/sessions",
        headers=device.headers,
        json={"repo": "acme/api", "branch": "main", "git_ref": "a1"},
    ).json()
    events = [
        {"seq": i + 1, "kind": "message", "payload": {"role": "user", "content": m}}
        for i, m in enumerate(messages)
    ]
    events.append(
        {"seq": len(events) + 1, "kind": "files_touched", "payload": {"paths": ["src/app.py"]}}
    )
    response = client.post(
        f"/v1/sessions/{session['id']}/events", headers=device.headers, json={"events": events}
    )
    assert response.status_code == 202
    return str(session["id"])


def _dream(conn: Conn, offset_days: float = 0) -> uuid.UUID:
    return run_dream(
        conn, FakeLlm(), FakeEmbedder(), POLICY, FIXED_NOW + timedelta(days=offset_days)
    )


def test_dream_merges_supersedes_and_keeps_provenance(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    s1 = _run_session(
        client,
        device,
        [
            "fix flaky tests",
            "remember: tests run with uv run pytest against local postgres",
            "next: add CI",
        ],
    )
    run1 = _dream(service_conn)
    first = service_conn.execute(
        "select id, content, source_session_ids from public.memories"
    ).fetchall()
    assert len(first) == 1
    original_id = first[0][0]
    assert first[0][2] == [uuid.UUID(s1)]

    s2 = _run_session(
        client,
        device,
        [
            "speed up tests",
            "remember: tests run with uv run pytest against local postgres container",
        ],
    )
    _dream(service_conn, 1)
    merged = service_conn.execute(
        "select id, content, source_session_ids, confidence, superseded_by from public.memories"
    ).fetchall()
    assert len(merged) == 1, "near-duplicate must merge, not add"
    assert merged[0][0] == original_id
    assert merged[0][1].endswith("postgres container")
    assert set(merged[0][2]) == {uuid.UUID(s1), uuid.UUID(s2)}
    assert merged[0][3] == pytest.approx(0.7)

    s3 = _run_session(
        client,
        device,
        [
            "switch runner",
            "remember: tests run with tox now",
        ],
    )
    _dream(service_conn, 2)
    rows = service_conn.execute(
        "select id, content, source_session_ids, superseded_by from public.memories"
        " order by created_at"
    ).fetchall()
    assert len(rows) == 2, "supersede keeps the old row (no hard delete)"
    old, new = rows
    assert old[0] == original_id
    assert old[3] == new[0]
    assert new[1] == "tests run with tox now"
    assert new[3] is None
    assert set(new[2]) == {uuid.UUID(s1), uuid.UUID(s2), uuid.UUID(s3)}

    checkpoints = service_conn.execute(
        "select session_id, status, goal, files_touched from public.checkpoints order by created_at"
    ).fetchall()
    assert [c[1] for c in checkpoints] == ["closed", "closed", "open"]
    assert checkpoints[-1][0] == uuid.UUID(s3)
    assert checkpoints[0][3] == ["src/app.py"]

    runs = service_conn.execute(
        "select id, status, sessions_processed, memories_added, memories_merged,"
        " memories_superseded, checkpoints_created from public.dream_runs"
        " order by started_at"
    ).fetchall()
    assert [r[1:] for r in runs] == [
        ("succeeded", 1, 1, 0, 0, 1),
        ("succeeded", 1, 0, 1, 0, 1),
        ("succeeded", 1, 0, 0, 1, 1),
    ]
    assert runs[0][0] == run1

    # Idempotent: nothing new to consolidate.
    _dream(service_conn, 3)
    last = service_conn.execute(
        "select sessions_processed from public.dream_runs order by started_at desc limit 1"
    ).fetchone()
    assert last is not None
    assert last[0] == 0

    context = client.get(
        "/v1/context", headers=device.headers, params={"repo": "acme/api", "branch": "main"}
    ).json()
    assert context["checkpoint"]["session_id"] == s3
    assert [m["content"] for m in context["memories"]] == ["tests run with tox now"]


def test_dream_decays_unused_memories_without_deleting(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    _run_session(client, device, ["start", "remember: deploys go through fly.io"])
    _dream(service_conn)
    _dream(service_conn, 30)
    row = service_conn.execute("select confidence, last_decayed_at from public.memories").fetchone()
    assert row is not None
    assert row[0] == pytest.approx(0.6 * 0.9, rel=1e-4)
    _dream(service_conn, 31)  # decayed recently: unchanged
    again = service_conn.execute(
        "select confidence, count(*) over () from public.memories"
    ).fetchone()
    assert again is not None
    assert again[0] == pytest.approx(row[0])
    assert again[1] == 1
    runs = service_conn.execute(
        "select memories_decayed from public.dream_runs order by started_at"
    ).fetchall()
    assert [r[0] for r in runs] == [0, 1, 0]


def test_requested_dream_run_is_claimed(service_conn: Conn) -> None:
    from somnia.dreaming.run_log import claim_requested_run

    row = service_conn.execute("select public.somnia_request_dream('manual')").fetchone()
    assert row is not None
    claimed = claim_requested_run(service_conn)
    assert claimed == row[0]
    assert claim_requested_run(service_conn) is None
    run_dream(service_conn, FakeLlm(), FakeEmbedder(), POLICY, FIXED_NOW, run_id=claimed)
    status = service_conn.execute(
        "select status, trigger from public.dream_runs where id = %s", (claimed,)
    ).fetchone()
    assert status == ("succeeded", "manual")
