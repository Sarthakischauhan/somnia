"""Event-triggered repo dreams (session end, idle, chunk threshold) with per-repo debounce."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from somnia.db.connection import Conn
from somnia.dreaming.dream import run_dream
from somnia.dreaming.policy import DreamPolicy
from somnia.dreaming.run_log import claim_requested_run
from somnia.dreaming.triggers import enqueue_chunk_thresholds, enqueue_idle_sessions
from somnia.ingest.pipeline import process_pending_events
from somnia.providers.fake import FakeEmbedder, FakeLlm
from tests.conftest import FIXED_NOW, Device, post_session

pytestmark = pytest.mark.db


def _pending(conn: Conn) -> list[tuple[object, ...]]:
    return [
        tuple(r)
        for r in conn.execute(
            "select repo, trigger, coalesced from public.dream_runs"
            " where status = 'requested' order by repo"
        ).fetchall()
    ]


def _close(client: TestClient, device: Device, session_id: str) -> None:
    response = client.post(f"/v1/sessions/{session_id}/close", headers=device.headers)
    assert response.status_code == 200, response.text


def test_session_end_enqueues_one_debounced_dream_per_repo(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    a1 = post_session(client, device, ["a1"])
    a2 = post_session(client, device, ["a2"])
    b1 = post_session(client, device, ["b1"], repo="acme/web")
    _close(client, device, a1)
    assert _pending(service_conn) == [("acme/api", "session_end", 0)]
    _close(client, device, a2)  # same repo while one is pending: coalesced
    _close(client, device, a1)  # already closed: no trigger
    _close(client, device, b1)
    assert _pending(service_conn) == [
        ("acme/api", "session_end", 1),
        ("acme/web", "session_end", 0),
    ]
    owner = service_conn.execute(
        "select distinct user_id from public.dream_runs where status = 'requested'"
    ).fetchall()
    assert [r[0] for r in owner] == [device.user_id]


def test_claimed_repo_dream_only_touches_that_repo(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    api = post_session(client, device, ["api work", "remember: api facts"])
    post_session(client, device, ["web work", "remember: web facts"], repo="acme/web")
    _close(client, device, api)
    run_id = claim_requested_run(service_conn)
    assert run_id is not None
    run_dream(service_conn, FakeLlm(), FakeEmbedder(), DreamPolicy(), FIXED_NOW, run_id=run_id)
    dreamt: dict[str, int] = dict(
        service_conn.execute("select repo, dreamed_through_seq from public.sessions").fetchall()
    )
    assert dreamt == {"acme/api": 2, "acme/web": 0}
    run = service_conn.execute(
        "select status, trigger, repo, sessions_processed from public.dream_runs where id = %s",
        (run_id,),
    ).fetchone()
    assert run == ("succeeded", "session_end", "acme/api", 1)
    profiles = service_conn.execute("select repo from public.project_profiles").fetchall()
    assert [r[0] for r in profiles] == ["acme/api"]
    # A trigger after the claim queues a fresh run (the claimed one is no longer pending).
    later = post_session(client, device, ["more api work"])
    _close(client, device, later)
    assert _pending(service_conn) == [("acme/api", "session_end", 0)]


def test_idle_sessions_enqueue_after_configured_minutes_and_skip_in_flight(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    post_session(client, device, ["working"])
    now = datetime.now(UTC)
    assert enqueue_idle_sessions(service_conn, now + timedelta(minutes=10), 30) == []
    assert _pending(service_conn) == []
    (run_id,) = enqueue_idle_sessions(service_conn, now + timedelta(minutes=31), 30)
    assert _pending(service_conn) == [("acme/api", "idle", 0)]
    # Already pending: the sweep does not pile on (no new row, no coalesce noise).
    assert enqueue_idle_sessions(service_conn, now + timedelta(minutes=45), 30) == []
    assert _pending(service_conn) == [("acme/api", "idle", 0)]
    # Running counts as in flight too.
    assert claim_requested_run(service_conn) == run_id
    assert enqueue_idle_sessions(service_conn, now + timedelta(minutes=60), 30) == []
    run_dream(service_conn, FakeLlm(), FakeEmbedder(), DreamPolicy(), FIXED_NOW, run_id=run_id)
    # Dreamt: nothing undreamt left, so idleness alone does not re-trigger.
    assert enqueue_idle_sessions(service_conn, now + timedelta(days=1), 30) == []


def test_chunk_threshold_enqueues_per_repo(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    post_session(client, device, [f"step {i}" for i in range(5)])
    post_session(client, device, ["web step"], repo="acme/web")
    while process_pending_events(service_conn, FakeEmbedder(), 100, 1200, 150):
        pass
    assert enqueue_chunk_thresholds(service_conn, 6) == []
    ids = enqueue_chunk_thresholds(service_conn, 5)
    assert len(ids) == 1
    assert _pending(service_conn) == [("acme/api", "chunk_threshold", 0)]
    # Session end on the same repo coalesces into the pending threshold run.
    session = service_conn.execute(
        "select id from public.sessions where repo = 'acme/api'"
    ).fetchone()
    assert session is not None
    _close(client, device, str(UUID(str(session[0]))))
    assert _pending(service_conn) == [("acme/api", "chunk_threshold", 1)]
