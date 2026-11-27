"""Dashboard authentication and owner isolation at the API boundary."""

from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr

from somnia.api.app import create_app
from somnia.auth.supabase import resolve_dashboard_user
from somnia.config import ApiSettings
from somnia.db.connection import Conn
from somnia.dreaming.dream import run_dream
from somnia.dreaming.policy import DreamPolicy
from somnia.providers.fake import FakeEmbedder, FakeLlm
from tests.conftest import FIXED_NOW, make_device, post_session
from tests.conftest import TestDatabase as Database


@pytest.mark.parametrize(
    ("code", "body", "expected"),
    [
        (401, {}, 401),
        (200, {"id": str(uuid4()), "is_anonymous": True}, 401),
        (200, {"id": "bad"}, 503),
        (429, {}, 503),
        (302, {}, 503),
    ],
)
def test_auth_provider_fails_closed(code: int, body: dict[str, object], expected: int) -> None:
    with (
        httpx.Client(
            base_url="https://example.test/auth/v1/",
            transport=httpx.MockTransport(lambda _: httpx.Response(code, json=body)),
        ) as auth,
        pytest.raises(HTTPException) as exc,
    ):
        resolve_dashboard_user(auth, "invalid")
    assert exc.value.status_code == expected


@pytest.mark.db
def test_dashboard_and_devices_share_only_their_owners_data(
    database: Database,
    service_conn: Conn,
) -> None:
    alice, bob = make_device(service_conn), make_device(service_conn)
    identities = {"Bearer alice.jwt": alice.user_id, "Bearer bob.jwt": bob.user_id}

    def auth_user(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://example.test/auth/v1/user"
        assert request.headers["apikey"] == "test-key"
        identity = identities.get(request.headers["Authorization"])
        if identity is None:
            return httpx.Response(401)
        return httpx.Response(200, json={"id": str(identity), "is_anonymous": False})

    settings = ApiSettings.model_validate(
        {
            "api_database_url": SecretStr(database.api_url),
            "supabase_url": "https://example.test",
            "supabase_publishable_key": SecretStr("test-key"),
        }
    )
    app = create_app(settings, FakeEmbedder(), auth_transport=httpx.MockTransport(auth_user))
    with TestClient(app) as client:
        post_session(client, alice, ["remember: Alice uses uv"])
        post_session(client, bob, ["remember: Bob uses npm"])
        run_dream(service_conn, FakeLlm(), FakeEmbedder(), DreamPolicy(), FIXED_NOW)
        memories = "/v1/admin/memories"
        alice_jwt = {"Authorization": "Bearer alice.jwt"}
        bob_jwt = {"Authorization": "Bearer bob.jwt"}
        assert client.get(memories).status_code == 401
        forged = {"Authorization": "Bearer forged.jwt"}
        assert client.get(memories, headers=forged).status_code == 401
        first = client.get(memories, headers=alice_jwt).json()["items"]
        second = client.get(memories, headers=bob_jwt).json()["items"]
        assert [m["content"] for m in first] == ["Alice uses uv"]
        assert [m["content"] for m in second] == ["Bob uses npm"]
        assert client.get(memories, headers=alice.headers).json()["items"] == first
        target = f"{memories}/{first[0]['id']}"
        assert client.get(target, headers=bob_jwt).status_code == 404
        assert client.patch(target, headers=bob_jwt, json={"archived": True}).status_code == 404
        assert client.patch(target, headers=alice_jwt, json={"archived": True}).status_code == 200
        assert client.get(memories, headers=alice_jwt).json()["items"] == []
        assert (
            client.post(
                "/v1/sessions",
                headers=alice_jwt,
                json={"repo": "acme/api", "branch": "main"},
            ).status_code
            == 401
        )
