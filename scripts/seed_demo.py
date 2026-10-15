"""Populate a local somnia DB with realistic demo data through the real API and dream
pipeline (fake providers). Run after `supabase db reset` with the API up:

    SOMNIA_API_URL=http://127.0.0.1:8000 SOMNIA_ADMIN_TOKEN=smn_dev_local_token_change_me \
    SOMNIA_SERVICE_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \
    uv run python scripts/seed_demo.py
"""

import os
from datetime import UTC, datetime, timedelta

import httpx
import psycopg

from somnia.db.vectors import to_vector_literal
from somnia.dreaming.dream import run_dream
from somnia.dreaming.policy import DreamPolicy
from somnia.providers.fake import FakeEmbedder, FakeLlm

SESSIONS: list[tuple[str, str, list[str], list[str]]] = [
    (
        "acme/api",
        "main",
        [
            "Fix flaky integration tests in the billing module",
            "remember: integration tests run with uv run pytest against local postgres",
            "remember: billing webhooks are verified with the stripe signing secret from env",
            "next: add a retry around the ledger write",
        ],
        ["src/billing/webhooks.py", "tests/test_billing.py"],
    ),
    (
        "acme/web",
        "main",
        [
            "Migrate the settings page to the app router",
            "remember: the web app uses pnpm and next 15 app router",
            "next: port the billing settings form",
        ],
        ["app/settings/page.tsx"],
    ),
    (
        "acme/api",
        "main",
        [
            "Speed up the test suite",
            "remember: integration tests run with uv run pytest against local postgres container",
            "remember: migrations live in supabase/migrations and run with supabase db reset",
        ],
        ["pyproject.toml", "supabase/migrations/0007_ledger.sql"],
    ),
    (
        "acme/api",
        "feat/retries",
        [
            "Add exponential backoff to outbound webhooks",
            "remember: outbound webhooks retry 5 times with exponential backoff",
            "next: document the retry policy in the README",
        ],
        ["src/webhooks/retry.py"],
    ),
    (
        "acme/api",
        "main",
        [
            "Switch the test runner",
            "remember: integration tests now run with tox",
            "next: update CI to call tox",
        ],
        ["tox.ini", ".github/workflows/ci.yml"],
    ),
]

EXTRA_MEMORIES = [
    ("convention", "repo", "acme/api", None, "API errors return RFC 7807 problem+json", 0.8),
    (
        "gotcha",
        "repo",
        "acme/api",
        None,
        "the ledger table has a deferred FK; insert parent rows first",
        0.7,
    ),
    ("decision", "global", None, None, "prefer squash merges for feature branches", 0.65),
    ("todo", "branch", "acme/api", "feat/retries", "add jitter to webhook backoff", 0.5),
]


def main() -> None:
    api = httpx.Client(
        base_url=os.environ["SOMNIA_API_URL"],
        headers={"Authorization": f"Bearer {os.environ['SOMNIA_ADMIN_TOKEN']}"},
    )
    policy = DreamPolicy(similarity_threshold=0.5)
    start = datetime.now(UTC) - timedelta(days=30)
    with psycopg.connect(os.environ["SOMNIA_SERVICE_DATABASE_URL"], autocommit=True) as conn:
        for day, (repo, branch, messages, files) in enumerate(SESSIONS):
            session = api.post(
                "/v1/sessions", json={"repo": repo, "branch": branch, "git_ref": f"{day:02d}a1b2c"}
            ).json()
            events: list[dict[str, object]] = [
                {"seq": i + 1, "kind": "message", "payload": {"role": "user", "content": m}}
                for i, m in enumerate(messages)
            ]
            events.append(
                {"seq": len(events) + 1, "kind": "files_touched", "payload": {"paths": files}}
            )
            events.append(
                {
                    "seq": len(events) + 1,
                    "kind": "git_ref",
                    "payload": {"ref": f"{day:02d}f00d", "pushed": day % 2 == 0},
                }
            )
            api.post(
                f"/v1/sessions/{session['id']}/events", json={"events": events}
            ).raise_for_status()
            api.post(f"/v1/sessions/{session['id']}/close").raise_for_status()
            run_dream(conn, FakeLlm(), FakeEmbedder(), policy, start + timedelta(days=day * 3))

        row = conn.execute("select id from auth.users order by id limit 1").fetchone()
        assert row is not None
        for mtype, scope, m_repo, m_branch, content, confidence in EXTRA_MEMORIES:
            conn.execute(
                "insert into public.memories (user_id, type, scope, repo, branch, content,"
                " embedding, confidence, created_at) values (%s, %s, %s, %s, %s, %s,"
                " %s::extensions.vector, %s, now() - interval '2 days')",
                (
                    row[0],
                    mtype,
                    scope,
                    m_repo,
                    m_branch,
                    content,
                    to_vector_literal(FakeEmbedder().embed([content])[0]),
                    confidence,
                ),
            )
        run_dream(conn, FakeLlm(), FakeEmbedder(), policy, datetime.now(UTC))

    for title, priority in [
        ("Port billing settings form", 1),
        ("Update CI to call tox", 3),
        ("Document retry policy", 0),
        ("Backfill ledger", 2),
    ]:
        api.post(
            "/v1/tasks",
            json={"title": title, "repo": "acme/api", "branch": "main", "priority": priority},
        ).raise_for_status()
    claimed = api.post("/v1/tasks/claim").json()
    api.post(
        f"/v1/tasks/{claimed['id']}/complete", json={"status": "done", "result": {"pr": 42}}
    ).raise_for_status()
    api.post("/v1/tasks/claim").raise_for_status()
    api.post("/v1/admin/dream-runs").raise_for_status()
    print("seeded demo data")


if __name__ == "__main__":
    main()
