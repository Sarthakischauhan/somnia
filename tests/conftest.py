"""Fixtures. DB tests need SOMNIA_TEST_DATABASE_URL pointing at a postgres+pgvector
server where the user may create databases (e.g. postgres://postgres:postgres@localhost/postgres).
A throwaway database is created, migrated with the real Supabase migrations, and dropped."""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import conninfo
from pydantic import SecretStr

from somnia.api.app import create_app
from somnia.auth.tokens import generate_device_token, hash_device_token
from somnia.config import ApiSettings
from somnia.db.connection import Conn
from somnia.providers.fake import FakeEmbedder

ROOT = Path(__file__).resolve().parent.parent
API_PASSWORD = "somnia_api_test"
FIXED_NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class TestDatabase:
    service_url: str
    api_url: str


@dataclass(frozen=True, slots=True)
class Device:
    user_id: uuid.UUID
    device_id: uuid.UUID
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}


@pytest.fixture(scope="session")
def database() -> Iterator[TestDatabase]:
    admin_url = os.environ.get("SOMNIA_TEST_DATABASE_URL")
    if not admin_url:
        if os.environ.get("CI"):
            pytest.fail("SOMNIA_TEST_DATABASE_URL must be set in CI")
        pytest.skip("SOMNIA_TEST_DATABASE_URL not set; skipping real-database tests")
    name = f"somnia_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
    service_url = conninfo.make_conninfo(admin_url, dbname=name)
    with psycopg.connect(service_url, autocommit=True) as conn:
        conn.execute((ROOT / "tests/sql/supabase_shim.sql").read_text())
        for migration in sorted((ROOT / "supabase/migrations").glob("*.sql")):
            conn.execute(migration.read_text())
        conn.execute(f"alter role somnia_api login password '{API_PASSWORD}'")
        conn.execute(f'alter database "{name}" set search_path = public, extensions')
    api_url = conninfo.make_conninfo(service_url, user="somnia_api", password=API_PASSWORD)
    yield TestDatabase(service_url=service_url, api_url=api_url)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'drop database "{name}" with (force)')


@pytest.fixture
def service_conn(database: TestDatabase) -> Iterator[Conn]:
    with psycopg.connect(database.service_url, autocommit=True) as conn:
        conn.execute(
            "truncate public.dream_runs, public.checkpoints, public.memories, public.chunks,"
            " public.tasks, public.events, public.sessions, public.devices, auth.users cascade"
        )
        yield conn


def make_device(conn: Conn, name: str = "laptop") -> Device:
    user_id = uuid.uuid4()
    token = generate_device_token()
    conn.execute("insert into auth.users (id) values (%s)", (user_id,))
    row = conn.execute(
        "insert into public.devices (user_id, name, token_hash) values (%s, %s, %s) returning id",
        (user_id, name, hash_device_token(token)),
    ).fetchone()
    assert row is not None
    return Device(user_id=user_id, device_id=row[0], token=token)


@pytest.fixture
def device(service_conn: Conn) -> Device:
    return make_device(service_conn)


@pytest.fixture
def client(database: TestDatabase, service_conn: Conn) -> Iterator[TestClient]:
    settings = ApiSettings(api_database_url=SecretStr(database.api_url))
    app = create_app(settings, FakeEmbedder(), clock=lambda: FIXED_NOW)
    with TestClient(app) as test_client:
        yield test_client


def post_session(
    client: TestClient,
    device: Device,
    messages: list[str],
    repo: str = "acme/api",
    branch: str = "main",
) -> str:
    """Create a session through the API and post `messages` as user message events."""
    session = client.post(
        "/v1/sessions", headers=device.headers, json={"repo": repo, "branch": branch}
    )
    assert session.status_code == 201, session.text
    session_id = str(session.json()["id"])
    events = [
        {"seq": i + 1, "kind": "message", "payload": {"role": "user", "content": m}}
        for i, m in enumerate(messages)
    ]
    posted = client.post(
        f"/v1/sessions/{session_id}/events", headers=device.headers, json={"events": events}
    )
    assert posted.status_code == 202, posted.text
    return session_id
