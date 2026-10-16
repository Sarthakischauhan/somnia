"""Contradiction reconciliation: supersede, coexist (narrower scope) and flag; both memories
are always kept with provenance, and flagged conflicts are resolved through the admin API."""

from datetime import timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from somnia.db.connection import Conn
from somnia.dreaming.dream import run_dream
from somnia.dreaming.policy import DreamPolicy
from somnia.providers.fake import FakeEmbedder, FakeLlm
from tests.conftest import FIXED_NOW, Device, make_device, post_session

pytestmark = pytest.mark.db

POLICY = DreamPolicy(similarity_threshold=0.5)


def _teach(
    client: TestClient, device: Device, conn: Conn, existing: str, candidate: str
) -> tuple[str, str]:
    first = post_session(client, device, ["one", f"remember: {existing}"])
    run_dream(conn, FakeLlm(), FakeEmbedder(), POLICY, FIXED_NOW)
    second = post_session(client, device, ["two", f"remember: {candidate}"])
    run_dream(conn, FakeLlm(), FakeEmbedder(), POLICY, FIXED_NOW + timedelta(days=1))
    return first, second


MemoryRow = tuple[UUID, str, str | None, UUID | None, list[UUID]]


def _memories(conn: Conn) -> dict[str, MemoryRow]:
    """content -> (id, scope, branch, superseded_by, source_session_ids)"""
    rows = conn.execute(
        "select content, id, scope, branch, superseded_by, source_session_ids from public.memories"
    ).fetchall()
    return {str(r[0]): (r[1], r[2], r[3], r[4], list(r[5])) for r in rows}


def _conflicts(conn: Conn) -> list[tuple[object, ...]]:
    return [
        tuple(r)
        for r in conn.execute(
            "select outcome, status, existing_memory_id, candidate_memory_id, rationale"
            " from public.memory_conflicts"
        ).fetchall()
    ]


def test_supersede_keeps_both_and_records_the_update(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    _teach(client, device, service_conn, "tests run with pytest", "tests run with tox today now")
    memories = _memories(service_conn)
    old_id, new_id = (
        memories["tests run with pytest"][0],
        memories["tests run with tox today now"][0],
    )
    assert memories["tests run with pytest"][3] == new_id  # superseded, not deleted
    ((outcome, status, existing, candidate, rationale),) = _conflicts(service_conn)
    assert (outcome, status, existing, candidate) == ("superseded", "resolved", old_id, new_id)
    assert rationale


def test_coexist_stores_candidate_with_narrower_scope(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    _teach(
        client, device, service_conn, "tests run with pytest", "tests run with pytest only on ci"
    )
    memories = _memories(service_conn)
    existing = memories["tests run with pytest"]
    candidate = memories["tests run with pytest only on ci"]
    assert (existing[1], existing[3]) == ("repo", None)  # untouched, still active
    assert (candidate[1], candidate[2], candidate[3]) == ("branch", "main", None)
    ((outcome, status, *_),) = _conflicts(service_conn)
    assert (outcome, status) == ("coexist", "resolved")
    run = service_conn.execute(
        "select memories_coexisting, conflicts_flagged from public.dream_runs"
        " order by started_at desc limit 1"
    ).fetchone()
    assert run == (1, 0)


def test_flagged_conflict_is_listed_and_resolved_via_admin_api(
    client: TestClient, device: Device, service_conn: Conn
) -> None:
    s1, s2 = _teach(client, device, service_conn, "deploys use fly.io", "deploys do not use fly.io")
    memories = _memories(service_conn)
    old, new = memories["deploys use fly.io"], memories["deploys do not use fly.io"]
    assert old[3] is None  # both stay active until a human decides
    assert new[3] is None
    assert [str(s) for s in old[4]] == [s1]
    assert [str(s) for s in new[4]] == [s2]

    listed = client.get("/v1/admin/conflicts", headers=device.headers)
    assert listed.status_code == 200, listed.text
    (view,) = listed.json()
    conflict = view["conflict"]
    assert (conflict["outcome"], conflict["status"], conflict["session_id"]) == (
        "flagged",
        "open",
        s2,
    )
    assert view["existing"]["content"] == "deploys use fly.io"
    assert view["candidate"]["content"] == "deploys do not use fly.io"
    run = service_conn.execute(
        "select conflicts_flagged from public.dream_runs order by started_at desc limit 1"
    ).fetchone()
    assert run == (1,)

    other = make_device(service_conn, "user-b")
    assert client.get("/v1/admin/conflicts", headers=other.headers).json() == []
    stolen = client.post(
        f"/v1/admin/conflicts/{conflict['id']}/resolve",
        headers=other.headers,
        json={"resolution": "keep_candidate"},
    )
    assert stolen.status_code == 404

    resolved = client.post(
        f"/v1/admin/conflicts/{conflict['id']}/resolve",
        headers=device.headers,
        json={"resolution": "keep_candidate"},
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert (body["conflict"]["status"], body["conflict"]["resolution"]) == (
        "resolved",
        "keep_candidate",
    )
    assert body["existing"]["superseded_by"] == body["candidate"]["id"]
    assert len(_memories(service_conn)) == 2  # nothing deleted

    again = client.post(
        f"/v1/admin/conflicts/{conflict['id']}/resolve",
        headers=device.headers,
        json={"resolution": "keep_existing"},
    )
    assert again.status_code == 409
    assert client.get("/v1/admin/conflicts", headers=device.headers).json() == []
    history = client.get(
        "/v1/admin/conflicts", headers=device.headers, params={"status": "resolved"}
    ).json()
    assert [h["conflict"]["resolution"] for h in history] == ["keep_candidate"]


@pytest.mark.parametrize(
    ("resolution", "superseded"),
    [("keep_existing", "candidate"), ("keep_both", None)],
)
def test_other_resolutions(
    client: TestClient,
    device: Device,
    service_conn: Conn,
    resolution: str,
    superseded: str | None,
) -> None:
    _teach(client, device, service_conn, "the cache is shared", "the cache is not shared")
    (view,) = client.get("/v1/admin/conflicts", headers=device.headers).json()
    body = client.post(
        f"/v1/admin/conflicts/{view['conflict']['id']}/resolve",
        headers=device.headers,
        json={"resolution": resolution},
    ).json()
    if superseded == "candidate":
        assert body["candidate"]["superseded_by"] == body["existing"]["id"]
        assert body["existing"]["superseded_by"] is None
    else:
        assert body["candidate"]["superseded_by"] is None
        assert body["existing"]["superseded_by"] is None
    bad = client.post(
        f"/v1/admin/conflicts/{view['conflict']['id']}/resolve",
        headers=device.headers,
        json={"resolution": "delete_both"},
    )
    assert bad.status_code == 422
