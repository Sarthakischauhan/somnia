# Contributing to somnia

Legend:
- ✅ **verified**: run successfully on the maintainers' dev box (Linux, local Postgres 17 + pgvector)
  and/or by this repo's CI (`.github/workflows/ci.yml`).
- 📄 **doc-sourced**: copied from the upstream docs linked next to it. **Not verified** in this
  repo's CI or on the dev box: Docker and the Supabase CLI are not available there.

## Prerequisites

| Tool | Version | Used for |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | recent | Python env and deps (`uv.lock`, `agent/uv.lock`) |
| Python | 3.12 (`requires-python = ">=3.12"`; uv picks 3.12) | API, worker, agent CLI |
| Node.js | 22+ (CI uses 22) | `dashboard/` dashboard |
| Docker | any recent | Supabase local stack or the pgvector image (📄) |
| [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started) | recent | `supabase start`, migrations (📄) |

Without Docker you can use any Postgres server that has the `vector` extension installed (that
is how the dev box runs, ✅).

## Repo layout

```
src/somnia/
  api/          FastAPI routes and request authentication
  ingestion/    durable event writes, redaction, chunking and embedding
  memory/       retrieval, inference, consolidation, dreaming and memory management
  sessions/     session state, checkpoints and explicit tasks
  db/           database connections and RLS transactions
  admin/        operator-only device provisioning
  worker.py     worker entry point for ingestion and dreaming
agent/          somnia-agent CLI (hooks, spool, MCP server); its own pyproject and tests
plugins/        harness plugins: claude-code/, codex/, grok/
dashboard/            Next.js dashboard; typed client generated from dashboard/openapi.json
supabase/
  migrations/   ordered SQL migrations (the schema's source of truth)
  seed.sql      local-only dev user, device token and somnia_api password
scripts/        export_openapi.py, seed_demo.py
tests/          unit tests, database integration tests and fixtures
```

## Local setup

```bash
uv sync --locked                     # ✅
cp .env.example .env                 # ✅ then edit the two database URLs if you're not using Supabase
```

### Database, option A: Supabase CLI (📄 not verified here)

From the [Supabase CLI getting-started guide](https://supabase.com/docs/guides/local-development/cli/getting-started)
and the [CLI reference](https://supabase.com/docs/reference/cli/supabase-db-reset). The repo
already contains `supabase/`, so skip `supabase init`:

```bash
supabase start      # starts the stack in Docker; DB at postgresql://postgres:postgres@127.0.0.1:54322/postgres
supabase db reset   # recreates the local DB, applies supabase/migrations, then runs supabase/seed.sql
```

`.env.example` already points at port 54322.

### Database, option B: plain Postgres + pgvector

The pgvector image (📄, from the [pgvector README](https://github.com/pgvector/pgvector#docker),
which shows `docker pull pgvector/pgvector:pg18-trixie`). CI runs `pgvector/pgvector:pg17` as a
service container with `POSTGRES_PASSWORD=postgres` (✅ in CI, but only for tests):

```bash
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres pgvector/pgvector:pg17   # 📄
```

Then create a database and apply the shim, migrations and seed. ✅ on the dev box (local PG 17
with the pgvector package):

```bash
export PGPASSWORD=postgres
psql -h 127.0.0.1 -U postgres -c "create database somnia_dev" \
  -c "alter database somnia_dev set search_path = public, extensions"
U=postgresql://postgres:postgres@127.0.0.1:5432/somnia_dev
psql "$U" -v ON_ERROR_STOP=1 -f tests/sql/supabase_shim.sql   # stand-ins for Supabase's auth schema and roles
for f in supabase/migrations/*.sql; do psql "$U" -v ON_ERROR_STOP=1 -f "$f"; done
psql "$U" -v ON_ERROR_STOP=1 -f supabase/seed.sql
```

The `search_path` line matters: without it, vector operators in `extensions` aren't found. In
`.env`, point `SOMNIA_API_DATABASE_URL` (user `somnia_api`, password `somnia_api_local`) and
`SOMNIA_SERVICE_DATABASE_URL` (user `postgres`) at `127.0.0.1:5432/somnia_dev`.

### Run it (✅)

```bash
uv run somnia-api                    # http://127.0.0.1:8000/docs
# In another terminal, run uv run somnia-worker
# In another terminal, configure dashboard/.env.local per dashboard/README.md, then:
cd dashboard && npm ci && npm run dev       # http://localhost:3000

# Demo data through the real API and dream pipeline (API must be running):
SOMNIA_API_URL=http://127.0.0.1:8000 SOMNIA_ADMIN_TOKEN=smn_dev_local_token_change_me \
  uv run python -m scripts.seed_demo

# A real device token for a user (printed once):
uv run somnia-admin create-device --user-id 00000000-0000-0000-0000-00000000d0e5 --name laptop
```

`seed_demo.py` also needs `SOMNIA_SERVICE_DATABASE_URL`, which it reads from `.env` or the
environment. The demo script uses deterministic test fixtures. For real worker and semantic
retrieval calls, configure `SOMNIA_LLM_*` and the model settings in `.env`.

## Checks (✅ all, the same commands CI runs)

```bash
# server
uv run ruff check . && uv run ruff format --check .
uv run mypy                                        # strict
uv run python scripts/export_openapi.py && git diff --exit-code dashboard/openapi.json
SOMNIA_TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/postgres \
  uv run pytest -m "db or not db"                  # real Postgres + pgvector

# agent CLI
cd agent && uv sync --locked && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy && uv run pytest
bash -n ../plugins/codex/install.sh && bash -n ../plugins/grok/install.sh

# dashboard
cd dashboard && npm ci && npm run gen:api && git diff --exit-code src/lib/api/schema.d.ts
npm run lint && npm run typecheck && npm run build
```

DB tests create and drop a throwaway database, using a superuser URL. Without
`SOMNIA_TEST_DATABASE_URL` they are skipped locally (and fail in CI).

> **Gotcha (✅ observed):** the test fixture runs `alter role somnia_api ... password` and roles
> are cluster-wide. After running tests against the same server as your dev DB, re-run
> `psql "$U" -f supabase/seed.sql` (it resets the password to `somnia_api_local`) and restart
> the API, or it fails with `password authentication failed for user "somnia_api"`.

If you change API models, regenerate both schema artifacts:
`uv run python scripts/export_openapi.py && (cd dashboard && npm run gen:api)`.

## Adding a migration

1. Add `supabase/migrations/<YYYYMMDDHHMMSS>_<what>.sql`. The timestamp must sort after the
   newest file. With the CLI, `supabase migration new <what>` creates the file (📄
   [reference](https://supabase.com/docs/reference/cli/supabase-migration-new)). Creating it by
   hand is the ✅ path used in this repo (e.g. `20261016000007_profile_cursor_ids.sql`).
2. Never edit a migration that has been merged. Add a new one.
3. Every new table: `enable row level security`, owner-scoped policies on
   `user_id = auth.uid()`, and only the grants the API needs for `authenticated`. Privileged
   writes go through a `SECURITY DEFINER` function that checks ownership (see
   `somnia_resolve_conflict`).
4. Apply it locally (`supabase db reset` 📄, or the `psql -f` loop above ✅). The test suite
   applies all migrations to a fresh DB on every run, so `pytest` is the real check.

## Testing a plugin against the dev API (✅)

With the API running and the seeded dev token:

```bash
cd agent
export SOMNIA_API_URL=http://127.0.0.1:8000 SOMNIA_TOKEN=smn_dev_local_token_change_me
export SOMNIA_AGENT_STATE=$(mktemp -d) SOMNIA_AGENT_CONFIG=$(mktemp -u)   # keep your real config/spool untouched
# Feed a recorded hook payload; set "cwd" to a git checkout whose origin is the repo you want.
sed 's#/work/repo#/path/to/checkout#' tests/fixtures/claude_code/session_start.json \
  | uv run somnia-agent context --harness claude-code      # prints the additionalContext JSON
sed 's#/work/repo#/path/to/checkout#' tests/fixtures/claude_code/user_prompt_submit.json \
  | uv run somnia-agent ingest --harness claude-code
uv run somnia-agent flush                                  # upload the spool now
```

Fixtures exist for `claude_code`, `codex` and `grok`. To load the real plugin in a harness, see
`plugins/<harness>/README.md` (e.g. `claude --plugin-dir plugins/claude-code`, 📄 per the
Claude Code plugin docs linked there).

## Conventions

- Python + FastAPI + Pydantic. Fully typed, `mypy --strict` and ruff clean. Use Pydantic models
  rather than loose dicts at boundaries.
- No `getattr` / `hasattr` / dynamic attribute tricks. Prefer small, single-purpose modules.
- Count tokens with tiktoken (`somnia.memory.tokenizer`), never with an estimator.
- **Never hard-delete memories.** Supersede (`superseded_by`), archive (`archived_at`) or
  retire; conflicts keep both sides with provenance.
- **RLS on every new table.** The API connects as `somnia_api` and runs as `authenticated`.
  Only the worker and admin CLI use the service URL.
- Fake providers must stay deterministic. Tests depend on them.
- Every change ships with tests. DB behaviour is tested against real Postgres, not mocks.

## Pull requests

1. Branch off `main` (`feat/…`, `fix/…`, `docs/…`) and push normally. No force-pushes to
   shared branches.
2. Open a PR against `main` describing the change, its tests and any known gaps (update the
   README's *Known gaps* if relevant).
3. **CI must be green** (`check`, `somnia-agent CLI`, `web`) before review or merge. Run the
   checks above locally first.
