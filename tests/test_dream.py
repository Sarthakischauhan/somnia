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


def _dream(conn: Conn, offset_days: float = 0) -> list[uuid.UUID]:
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
    assert [runs[0][0]] == run1

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


def _user_runs(conn: Conn, user_id: uuid.UUID) -> list[tuple[object, ...]]:
    return [
        tuple(r)
        for r in conn.execute(
            "select sessions_processed, memories_added, checkpoints_created from public.dream_runs"
            " where user_id = %s order by started_at",
            (user_id,),
        ).fetchall()
    ]


def test_scheduled_run_writes_one_row_per_user_and_rls_hides_others(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    from tests.conftest import make_device

    other = make_device(service_conn, "user-b")
    _run_session(client, device, ["a1", "remember: user a uses poetry"])
    _run_session(client, device, ["a2", "remember: user a deploys to fly"])
    _run_session(client, other, ["b1", "remember: user b uses bazel"])

    ids = _dream(service_conn)
    assert len(ids) == 2
    assert _user_runs(service_conn, device.user_id) == [(2, 2, 2)]
    assert _user_runs(service_conn, other.user_id) == [(1, 1, 1)]
    row = service_conn.execute(
        "select count(*) from public.dream_runs where user_id is null"
    ).fetchone()
    assert row is not None
    assert row[0] == 0

    a_view = client.get("/v1/admin/dream-runs", headers=device.headers).json()
    b_view = client.get("/v1/admin/dream-runs", headers=other.headers).json()
    assert [(r["sessions_processed"], r["user_id"]) for r in a_view] == [(2, str(device.user_id))]
    assert [(r["sessions_processed"], r["user_id"]) for r in b_view] == [(1, str(other.user_id))]
    assert {r["id"] for r in a_view}.isdisjoint({r["id"] for r in b_view})


def test_global_cron_request_fans_out_per_user_and_marker_has_no_stats(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    from somnia.dreaming.run_log import claim_requested_run
    from tests.conftest import make_device

    other = make_device(service_conn, "user-b")
    _run_session(client, device, ["a", "remember: a fact"])
    _run_session(client, other, ["b", "remember: b fact"])
    service_conn.execute("select public.somnia_request_dream('pg_cron')")
    marker = claim_requested_run(service_conn)
    assert marker is not None
    ids = run_dream(service_conn, FakeLlm(), FakeEmbedder(), POLICY, FIXED_NOW, run_id=marker)
    rows = service_conn.execute(
        "select user_id, trigger, parent_run_id, sessions_processed from public.dream_runs"
        " where id = any(%s) order by user_id",
        (ids,),
    ).fetchall()
    assert {r[0] for r in rows} == {device.user_id, other.user_id}
    assert all(r[1] == "pg_cron" and r[2] == marker and r[3] == 1 for r in rows)
    mark = service_conn.execute(
        "select status, user_id, sessions_processed, memories_added from public.dream_runs"
        " where id = %s",
        (marker,),
    ).fetchone()
    assert mark == ("succeeded", None, 0, 0)
    for d in (device, other):
        seen = client.get("/v1/admin/dream-runs", headers=d.headers).json()
        assert [r["user_id"] for r in seen] == [str(d.user_id)]
    import psycopg

    with pytest.raises(psycopg.errors.CheckViolation):
        service_conn.execute(
            "insert into public.dream_runs (trigger, status, memories_added)"
            " values ('schedule', 'succeeded', 3)"
        )


def test_run_timestamps_are_wall_clock_not_logical_now(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    _run_session(client, device, ["x", "remember: wall clock matters"])
    logical = FIXED_NOW + timedelta(days=365)
    (run_id,) = run_dream(service_conn, FakeLlm(), FakeEmbedder(), POLICY, logical)
    row = service_conn.execute(
        "select started_at, finished_at, logical_now, clock_timestamp() from public.dream_runs"
        " where id = %s",
        (run_id,),
    ).fetchone()
    assert row is not None
    started, finished, logical_now, db_now = row
    assert finished >= started
    assert (finished - started).total_seconds() > 0
    assert logical_now == logical
    assert abs((db_now - finished).total_seconds()) < 60
    body = client.get("/v1/admin/dream-runs", headers=device.headers).json()[0]
    assert body["finished_at"] >= body["started_at"]
    assert body["logical_now"] is not None
