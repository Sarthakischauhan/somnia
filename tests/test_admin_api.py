"""Admin endpoints (RLS-scoped) against the real database."""

import uuid

import pytest
from fastapi.testclient import TestClient

from somnia.db.connection import Conn
from somnia.dreaming.dream import run_dream
from somnia.dreaming.policy import DreamPolicy
from somnia.dreaming.run_log import claim_requested_run
from somnia.providers.fake import FakeEmbedder, FakeLlm
from tests.conftest import FIXED_NOW, Device, make_device

pytestmark = pytest.mark.db


def _dreamed_session(client: TestClient, device: Device, seq_text: list[str]) -> str:
    session = client.post(
        "/v1/sessions", headers=device.headers, json={"repo": "acme/api", "branch": "main"}
    ).json()
    events = [
        {"seq": i + 1, "kind": "message", "payload": {"role": "user", "content": t}}
        for i, t in enumerate(seq_text)
    ]
    client.post(
        f"/v1/sessions/{session['id']}/events", headers=device.headers, json={"events": events}
    )
    return str(session["id"])


def _seed_chain(client: TestClient, device: Device, conn: Conn) -> tuple[str, str]:
    policy = DreamPolicy(similarity_threshold=0.5)
    s1 = _dreamed_session(client, device, ["a", "remember: tests run with uv run pytest"])
    run_dream(conn, FakeLlm(), FakeEmbedder(), policy, FIXED_NOW)
    s2 = _dreamed_session(client, device, ["b", "remember: tests run with tox now"])
    from datetime import timedelta

    run_dream(conn, FakeLlm(), FakeEmbedder(), policy, FIXED_NOW + timedelta(days=1))
    return s1, s2


def test_memory_list_filters_detail_chain_and_provenance(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    s1, s2 = _seed_chain(client, device, service_conn)
    h = device.headers

    active = client.get("/v1/admin/memories", headers=h).json()
    assert active["total"] == 1
    assert active["items"][0]["content"] == "tests run with tox now"
    everything = client.get(
        "/v1/admin/memories", headers=h, params={"include_superseded": True}
    ).json()
    assert everything["total"] == 2
    assert (
        client.get(
            "/v1/admin/memories",
            headers=h,
            params={"q": "TOX", "repo": "acme/api", "type": "fact", "scope": "repo"},
        ).json()["total"]
        == 1
    )
    assert (
        client.get("/v1/admin/memories", headers=h, params={"repo": "nope/repo"}).json()["total"]
        == 0
    )
    assert client.get("/v1/admin/memories", headers=h, params={"type": "bogus"}).status_code == 422

    new_id = active["items"][0]["id"]
    old_id = next(m["id"] for m in everything["items"] if m["id"] != new_id)
    detail = client.get(f"/v1/admin/memories/{new_id}", headers=h).json()
    assert [m["id"] for m in detail["supersedes"]] == [old_id]
    assert detail["superseded_by_chain"] == []
    assert {s["id"] for s in detail["sources"]} == {s1, s2}
    old = client.get(f"/v1/admin/memories/{old_id}", headers=h).json()
    assert [m["id"] for m in old["superseded_by_chain"]] == [new_id]
    assert old["memory"]["superseded_by"] == new_id

    assert client.get("/v1/admin/repos", headers=h).json() == [
        {"repo": "acme/api", "branch": "main"}
    ]


def test_edit_confidence_and_archive_is_soft(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    _seed_chain(client, device, service_conn)
    h = device.headers
    memory_id = client.get("/v1/admin/memories", headers=h).json()["items"][0]["id"]
    url = f"/v1/admin/memories/{memory_id}"

    assert client.patch(url, headers=h, json={"confidence": 1.5}).status_code == 422
    edited = client.patch(url, headers=h, json={"confidence": 0.95}).json()
    assert edited["confidence"] == pytest.approx(0.95)

    archived = client.patch(url, headers=h, json={"archived": True}).json()
    assert archived["archived_at"] is not None
    assert client.get("/v1/admin/memories", headers=h).json()["total"] == 0
    context = client.get(
        "/v1/context", headers=h, params={"repo": "acme/api", "branch": "main"}
    ).json()
    assert context["memories"] == []
    row = service_conn.execute(
        "select count(*) from public.memories where id = %s", (memory_id,)
    ).fetchone()
    assert row is not None
    assert row[0] == 1, "archive never deletes"

    restored = client.patch(url, headers=h, json={"archived": False}).json()
    assert restored["archived_at"] is None


def test_admin_is_scoped_to_the_callers_user(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    _seed_chain(client, device, service_conn)
    other = make_device(service_conn, "intruder")
    memory_id = client.get("/v1/admin/memories", headers=device.headers).json()["items"][0]["id"]
    assert client.get("/v1/admin/memories", headers=other.headers).json()["total"] == 0
    assert client.get(f"/v1/admin/memories/{memory_id}", headers=other.headers).status_code == 404
    assert (
        client.patch(
            f"/v1/admin/memories/{memory_id}", headers=other.headers, json={"confidence": 0.1}
        ).status_code
        == 404
    )
    assert client.get("/v1/admin/memories").status_code == 401


def test_dream_history_trigger_and_schedule(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    _seed_chain(client, device, service_conn)
    h = device.headers
    runs = client.get("/v1/admin/dream-runs", headers=h).json()
    assert [(r["memories_added"], r["memories_superseded"]) for r in runs] == [(0, 1), (1, 0)]

    requested = client.post("/v1/admin/dream-runs", headers=h)
    assert requested.status_code == 202
    body = requested.json()
    assert body["status"] == "requested"
    assert body["trigger"] == "manual"
    assert body["user_id"] == str(device.user_id)

    schedule = client.get("/v1/admin/dream-schedule", headers=h).json()
    assert schedule["pending_requests"] == 1
    assert schedule["pg_cron_schedule"] is None
    assert schedule["worker_interval_s"] == 3600.0
    assert schedule["last_success_at"] is not None

    claimed = claim_requested_run(service_conn)
    assert claimed == uuid.UUID(body["id"])
    run_dream(service_conn, FakeLlm(), FakeEmbedder(), DreamPolicy(), FIXED_NOW, run_id=claimed)
    assert client.get("/v1/admin/dream-schedule", headers=h).json()["pending_requests"] == 0


def test_latest_checkpoints_and_task_queue(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    h = device.headers
    for repo, branch in [("acme/api", "main"), ("acme/api", "feat/x"), ("acme/web", "main")]:
        s = client.post("/v1/sessions", headers=h, json={"repo": repo, "branch": branch}).json()
        for goal in ("first", "second"):
            client.post(
                f"/v1/sessions/{s['id']}/checkpoints",
                headers=h,
                json={"goal": f"{goal} {repo}@{branch}", "state": "wip"},
            )
    latest = client.get("/v1/admin/checkpoints/latest", headers=h).json()
    assert len(latest) == 3
    assert all(c["goal"].startswith("second") for c in latest)

    for title in ("t1", "t2", "t3"):
        client.post("/v1/tasks", headers=h, json={"title": title})
    claimed = client.post("/v1/tasks/claim", headers=h).json()
    client.post(f"/v1/tasks/{claimed['id']}/complete", headers=h, json={"status": "failed"})
    client.post("/v1/tasks/claim", headers=h)
    queue = client.get("/v1/admin/tasks", headers=h).json()
    assert queue["counts"] == {"queued": 1, "running": 1, "done": 0, "failed": 1}
    assert len(queue["items"]) == 3
    only_failed = client.get("/v1/admin/tasks", headers=h, params={"status": "failed"}).json()
    assert [t["status"] for t in only_failed["items"]] == ["failed"]
