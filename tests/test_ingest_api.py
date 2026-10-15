"""Ingestion over HTTP against a real database (RLS path)."""

import pytest
from fastapi.testclient import TestClient

from somnia.db.connection import Conn
from somnia.ingest.pipeline import process_pending_events
from somnia.providers.fake import FakeEmbedder
from tests.conftest import Device, make_device

pytestmark = pytest.mark.db


def _session(client: TestClient, device: Device) -> str:
    response = client.post(
        "/v1/sessions",
        headers=device.headers,
        json={"repo": "acme/api", "branch": "main", "git_ref": "abc123"},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _events(*seqs: int) -> dict[str, object]:
    return {
        "events": [
            {"seq": s, "kind": "message", "payload": {"role": "user", "content": f"step {s}"}}
            for s in seqs
        ]
    }


def test_rejects_missing_or_bad_token(client: TestClient) -> None:
    assert client.post("/v1/sessions", json={"repo": "r", "branch": "b"}).status_code == 401
    bad = {"Authorization": "Bearer smn_nope"}
    assert (
        client.post("/v1/sessions", headers=bad, json={"repo": "r", "branch": "b"}).status_code
        == 401
    )


def test_repeated_seq_is_idempotent(client: TestClient, device: Device, service_conn: Conn) -> None:
    session_id = _session(client, device)
    url = f"/v1/sessions/{session_id}/events"
    first = client.post(url, headers=device.headers, json=_events(1, 2, 3))
    assert first.status_code == 202
    assert first.json() == {"accepted": 3, "duplicates": 0}

    retry = client.post(url, headers=device.headers, json=_events(2, 3, 4, 4))
    assert retry.json() == {"accepted": 1, "duplicates": 3}

    rows = service_conn.execute(
        "select seq from public.events where session_id = %s order by seq", (session_id,)
    ).fetchall()
    assert [r[0] for r in rows] == [1, 2, 3, 4]


def test_worker_redacts_chunks_and_embeds(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    session_id = _session(client, device)
    secret = "sk-" + "z" * 30
    body = {
        "events": [
            {
                "seq": 1,
                "kind": "tool_call",
                "payload": {"name": "bash", "input": {"cmd": f"export OPENAI_API_KEY={secret}"}},
            },
            {"seq": 2, "kind": "git_ref", "payload": {"ref": "def456", "pushed": True}},
        ]
    }
    assert (
        client.post(
            f"/v1/sessions/{session_id}/events", headers=device.headers, json=body
        ).status_code
        == 202
    )

    status = client.get(f"/v1/sessions/{session_id}/status", headers=device.headers).json()
    assert status["unprocessed_events"] == 2
    assert status["session"]["git_ref"] == "def456"

    assert process_pending_events(service_conn, FakeEmbedder(), 50, 1200, 150) == 2
    assert process_pending_events(service_conn, FakeEmbedder(), 50, 1200, 150) == 0
    contents = [
        r[0]
        for r in service_conn.execute(
            "select content from public.chunks where session_id = %s", (session_id,)
        ).fetchall()
    ]
    assert len(contents) == 2
    assert all(secret not in c for c in contents)
    assert any("[REDACTED" in c for c in contents)


def test_rls_isolates_users(client: TestClient, device: Device, service_conn: Conn) -> None:
    session_id = _session(client, device)
    intruder = make_device(service_conn, "other")
    url = f"/v1/sessions/{session_id}"
    assert client.get(url + "/status", headers=intruder.headers).status_code == 404
    assert (
        client.post(url + "/events", headers=intruder.headers, json=_events(9)).status_code == 404
    )


def test_task_queue_claim_complete_and_status(client: TestClient, device: Device) -> None:
    session_id = _session(client, device)
    low = client.post(
        "/v1/tasks", headers=device.headers, json={"title": "low", "session_id": session_id}
    ).json()
    high = client.post(
        "/v1/tasks", headers=device.headers, json={"title": "high", "priority": 5}
    ).json()
    claimed = client.post("/v1/tasks/claim", headers=device.headers).json()
    assert claimed["id"] == high["id"]
    assert claimed["status"] == "running"
    assert client.post("/v1/tasks/claim", headers=device.headers).json()["id"] == low["id"]
    assert client.post("/v1/tasks/claim", headers=device.headers).status_code == 204

    client.post(
        f"/v1/sessions/{session_id}/checkpoints",
        headers=device.headers,
        json={"goal": "ship", "state": "halfway", "next_steps": ["tests"]},
    )
    done = client.post(
        f"/v1/tasks/{low['id']}/complete",
        headers=device.headers,
        json={"status": "done", "result": {"ok": True}},
    )
    assert done.json()["status"] == "done"
    status = client.get(f"/v1/tasks/{low['id']}/status", headers=device.headers).json()
    assert status["task"]["status"] == "done"
    assert status["latest_checkpoint"]["goal"] == "ship"


def test_secrets_are_redacted_before_events_are_stored(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    session_id = _session(client, device)
    openai_key = "sk-" + "q" * 32
    github_token = "ghp_" + "b" * 36
    body = {
        "events": [
            {
                "seq": 1,
                "kind": "tool_call",
                "payload": {
                    "name": "bash",
                    "input": {
                        "cmd": f"export OPENAI_API_KEY={openai_key}",
                        "api_key": "plainvalue1",
                        "nested": [{"note": f"token {github_token}"}],
                    },
                    "output": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123",
                },
            },
            {
                "seq": 2,
                "kind": "message",
                "payload": {"role": "user", "content": "db is postgres://app:hunter2secret@db/x"},
            },
        ]
    }
    url = f"/v1/sessions/{session_id}/events"
    assert client.post(url, headers=device.headers, json=body).json() == {
        "accepted": 2,
        "duplicates": 0,
    }
    assert client.post(url, headers=device.headers, json=body).json() == {
        "accepted": 0,
        "duplicates": 2,
    }

    rows = service_conn.execute(
        "select payload::text from public.events where session_id = %s order by seq",
        (session_id,),
    ).fetchall()
    assert len(rows) == 2
    stored = " ".join(r[0] for r in rows)
    for secret in (
        openai_key,
        github_token,
        "plainvalue1",
        "hunter2secret",
        "abcdefghijklmnopqrstuvwxyz0123",
    ):
        assert secret not in stored
    assert '"api_key": "[REDACTED]"' in stored
    assert '"name": "bash"' in stored
