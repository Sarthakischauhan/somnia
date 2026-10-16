# somnia

Somnia is a shared memory service for coding agents. Agents post what they do. A worker
redacts, chunks, and embeds those events. A scheduled dream consolidates each session into
durable memories and a checkpoint. The next agent on the same repo and branch starts from a
ranked, token-budgeted context.

The store is Supabase Postgres with pgvector. Harness integrations for Claude Code, Codex,
and Grok Build live in [`plugins/`](plugins/README.md), on top of the
[`somnia-agent`](agent/README.md) CLI (hook ingest, session-start context, checkpoints, and
an MCP server). Any other agent that can send HTTP can use the [API](#api-reference).

To run it locally, start at [Setup](#setup).

## How a turn becomes memory

1. The agent sends `Authorization: Bearer smn_…`. The API hashes the token, resolves the
   device, and runs the request as that user under row-level security.
2. The agent opens a session and posts events, checkpoints, and tasks. Event writes return
   `202`. The `events` table is the outbox.
3. `somnia-worker` claims unprocessed events, redacts secrets, chunks the text, and stores
   embeddings.
4. On an interval, or when `pg_cron` requests one, a dream summarizes new sessions, writes a
   checkpoint, and adds, merges, or supersedes memories. Idle memories decay. Rows are not
   hard-deleted.
5. `GET /v1/context` returns the open checkpoint plus the memories that fit `token_budget`,
   ranked by similarity, confidence, and recency.

## Architecture

```mermaid
flowchart LR
    subgraph agents [Agents]
        laptop[Laptop]
        ci[CI]
    end
    subgraph api [somnia-api]
        auth[Resolve device token]
        write[POST sessions, events, checkpoints, tasks]
        read[GET status and context]
    end
    subgraph data [Postgres and pgvector]
        events[(sessions and events)]
        chunks[(chunks)]
        memories[(memories)]
        checkpoints[(checkpoints)]
        tasks[(tasks)]
        dreamRuns[(dream runs)]
    end
    subgraph worker [somnia-worker]
        ingest[Redact, chunk, embed]
        dream[Summarize, merge, decay]
    end
    model[LLM and embedder]
    cron[pg_cron]

    laptop -->|device token| auth
    ci -->|device token| auth
    auth --> write
    auth --> read
    write --> events
    write --> tasks
    write --> checkpoints
    read --> memories
    read --> checkpoints
    read --> tasks
    read -.->|query embedding| model
    events --> ingest --> chunks
    ingest -.-> model
    events --> dream
    dream --> memories
    dream --> checkpoints
    dream --> dreamRuns
    dream -.-> model
    cron -->|request dream| dreamRuns
```

Solid arrows are data. Dotted arrows are model calls. The API role is `somnia_api`, which
switches to `authenticated` for the request. The worker is the only process with the service
role. The model is an OpenAI-compatible endpoint, or the fake provider in tests.

### Request path

Every request resolves `Authorization: Bearer smn_…` through the `SECURITY DEFINER` function
`somnia_resolve_device(sha256(token))`. Only `somnia_api` may call it, and token hashes are
never readable. The request then runs in one transaction with `SET LOCAL ROLE authenticated`
and `request.jwt.claims.sub = user_id`, so `auth.uid()` and the RLS policies scope every
statement. The API process is only ever configured with `SOMNIA_API_DATABASE_URL`. The
service URL exists only in `WorkerSettings`.

### Ingestion

Payloads are redacted before they are stored. Every string in the event JSON goes through
the shared redactor, and values under secret-looking keys (`api_key`, `password`, `token`,
`authorization`, and similar) are replaced with `[REDACTED]`.

`POST …/events` inserts with `ON CONFLICT (session_id, seq) DO NOTHING` and returns `202`
immediately. The `events` table is the outbox. The worker claims `processed_at IS NULL` rows
with `FOR UPDATE SKIP LOCKED`, renders them to text, and redacts secrets again: private
keys, AWS, GitHub, OpenAI, Slack, and somnia tokens, JWTs, bearer headers, URL passwords,
and `*_KEY=` / `password=` assignments. It then chunks with overlap and embeds into
`chunks`.

### Tasks

Agents enqueue work in `tasks`. Any device of the same user claims a row with
`FOR UPDATE SKIP LOCKED` and a lease. Expired leases are reclaimable. The claimant then
completes the task.

### Retrieval

`GET /v1/context` returns the latest open checkpoint for the repo and branch, plus memories
ranked by:

```text
max(cosine_sim, 0) × confidence × 0.5^(age_days / half_life)
```

Age counts from `last_used_at`, or from `created_at` when the memory has not been used.
pgvector pre-selects `k × candidate_pool_factor` nearest neighbours. Python ranks them.
Greedy packing keeps the checkpoint, then as many top-k memories as fit in `token_budget`.

Tokens are counted with tiktoken using the configured encoding (`SOMNIA_TOKEN_ENCODING`:
`o200k_base`, `cl100k_base`, `p50k_base`, or `r50k_base`; default `o200k_base`). There is
no character heuristic. The response echoes `token_encoding` and the exact `tokens_used`.
Returned memories get `last_used_at` refreshed and `use_count` incremented.

### Dreaming

`somnia-worker` runs a dream every `SOMNIA_DREAM_INTERVAL_S`, and whenever a `dream_runs`
row is `requested`. `pg_cron` calls `somnia_request_dream()` on the schedule installed by
the migration when the extension is enabled.

For each session with new events:

1. **Summarize** the redacted transcript into a goal, state, next steps, files, and memory
   candidates. Write a checkpoint, closing the previous open one for that repo and branch.
2. **Dedupe** against the nearest active memory in the same scope. Below
   `similarity_threshold`, **add** a new memory. Otherwise the LLM chooses **merge** (update
   in place, raise confidence, union `source_session_ids`) or **supersede** (new row
   inherits provenance, and the old row gets `superseded_by`).
3. **Decay** memories idle for `decay_after_days` by `confidence × decay_factor`, with a
   floor of `min_confidence`.

Nothing is hard-deleted. Each user is processed separately. The run is logged as one
`dream_runs` row per user, with that user's counts (or the error), wall-clock `started_at`
and `finished_at`, and the `logical_now` used for decay.

## Stack and why

| Choice | Why |
| --- | --- |
| **Python 3.12 + FastAPI** | Decided for the project. FastAPI derives validation and OpenAPI docs from type hints. |
| **Pydantic v2** | One typed model per request, response, and DB row (`class_row`). Discriminated unions for event kinds. |
| **psycopg 3 + psycopg-pool** | Typed Postgres driver. `SET LOCAL ROLE` and claims per transaction for RLS. `SKIP LOCKED` queues. No ORM: the SQL (vector ops, RLS, upserts) is the point. |
| **pgvector (HNSW, cosine)** | Embeddings live next to the data they describe. RLS applies to them too. |
| **uv, ruff, mypy `--strict`, pytest** | Fast reproducible env (`uv.lock`), one linter and formatter, strict typing with the pydantic plugin, tests against a real database. |

Code rules: small modules named for one job, no `utils`, no `getattr` or `hasattr`, and
providers behind `typing.Protocol`.

## API reference

All endpoints except `/healthz` need `Authorization: Bearer <device token>`. Interactive
docs are at `/docs`.

| Method and path | Body or query | Returns |
| --- | --- | --- |
| `POST /v1/sessions` | `{repo, branch, git_ref?}` | `201` session (`device_id` from the token) |
| `POST /v1/sessions/{id}/events` | `{events: [{seq, kind, payload}]}` (at most 500) | `202 {accepted, duplicates}` |
| `POST /v1/sessions/{id}/checkpoints` | `{goal, state, next_steps[], files_touched[], git_ref?, pushed}` | `201` checkpoint |
| `POST /v1/sessions/{id}/close` | | session |
| `GET /v1/sessions/{id}/status` | | `{session, latest_checkpoint, unprocessed_events}` |
| `POST /v1/tasks` | `{title, payload?, repo?, branch?, session_id?, priority?}` | `201` task |
| `POST /v1/tasks/claim` | `lease_seconds=900` | running task, or `204` when the queue is empty |
| `POST /v1/tasks/{id}/complete` | `{status: done\|failed, result?}` | task |
| `GET /v1/tasks/{id}/status` | | `{task, latest_checkpoint}` |
| `GET /v1/context` | `repo`, `branch`, `token_budget?` (tiktoken tokens), `k=10`, `query?` | checkpoint, ranked memories, and token usage |
| `GET /healthz` | | `{status: ok}` |

`GET /v1/context` responds with `checkpoint`, `token_budget`, `token_encoding`,
`tokens_used`, and `dropped`. Each memory has `id`, `type`, `scope`, `content`,
`confidence`, `similarity`, `recency`, and `score`.

Event kinds and payloads:

| Kind | Payload |
| --- | --- |
| `message` | `{role: user\|assistant\|system\|tool, content}` |
| `tool_call` | `{name, input: {}, output?, is_error?}` |
| `files_touched` | `{paths: [], action: read\|write\|delete}` |
| `git_ref` | `{ref, pushed?}`. Also updates `sessions.git_ref`. |

Open a session, post one message, then read context:

```bash
TOKEN=smn_dev_local_token_change_me
S=$(curl -s -XPOST localhost:8000/v1/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"repo":"acme/api","branch":"main"}' | jq -r .id)
curl -XPOST "localhost:8000/v1/sessions/$S/events" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"events":[{"seq":1,"kind":"message","payload":{"role":"user","content":"remember: run uv run pytest"}}]}'
curl "localhost:8000/v1/context?repo=acme/api&branch=main&token_budget=800" \
  -H "Authorization: Bearer $TOKEN"
```

## Admin UI (`web/`)

Next.js 15 (App Router, TypeScript strict) with plain shadcn/ui. Navigation is a
collapsible sidebar. Light and dark themes come from next-themes: system is the default,
the toggle sits in the sidebar footer, and there is no hydration flash. Radius is
`--radius: 0.25rem`, and `--border` stays low-contrast in both themes.

Every page is a server component. It calls only the FastAPI service, through a typed client
generated from the service OpenAPI schema (`openapi-typescript` and `openapi-fetch`).
`SOMNIA_API_URL` and `SOMNIA_ADMIN_TOKEN` are read server-side (`server-only` modules, no
`NEXT_PUBLIC_`), so the token never reaches the browser. Mutations go through server
actions.

| Page | Shows |
| --- | --- |
| `/memories` | List with repo, branch, type, and scope filters, content search, and toggles for superseded and archived rows |
| `/memories/[id]` | Provenance (`source_session_ids` to sessions), the full `superseded_by` chain in both directions, edit confidence, archive and restore |
| `/dreaming` | `dream_runs` history (sessions, added, merged, superseded, decayed, duration), **Run dream now**, and schedule status (worker interval, pg_cron job, last success, pending requests) |
| `/sessions` | Latest checkpoint per repo and branch, task queue counts, and recent tasks |

Admin endpoints use the same per-device token and RLS scope as the agent API. An admin
token is a device token for that user, so the UI can only see and curate that user's rows.
Column grants allow updates to `confidence`, `archived_at`, `last_used_at`, and
`use_count` only.

| Method and path | Body or query | Returns |
| --- | --- | --- |
| `GET /v1/admin/memories` | `repo`, `branch`, `type`, `scope`, `q`, `include_superseded`, `include_archived`, `limit`, `offset` | `{items: Memory[], total}` |
| `GET /v1/admin/memories/{id}` | | `{memory, sources: Session[], supersedes: Memory[], superseded_by_chain: Memory[]}` |
| `PATCH /v1/admin/memories/{id}` | `{confidence?: 0..1, archived?: bool}` | memory. Archive is soft (`archived_at`). |
| `GET /v1/admin/repos` | | `[{repo, branch}]` for filters |
| `GET /v1/admin/dream-runs` | `limit` | `DreamRun[]` |
| `POST /v1/admin/dream-runs` | | `202` requested run. The worker picks it up. |
| `GET /v1/admin/dream-schedule` | | `{pg_cron_schedule, worker_interval_s, last_run, last_success_at, pending_requests}` |
| `GET /v1/admin/checkpoints/latest` | | latest checkpoint per repo and branch |
| `GET /v1/admin/tasks` | `status` (repeatable), `limit` | `{counts: {queued, running, done, failed}, items}` |

Archived memories are excluded from retrieval, dedupe, and decay. Every `dream_runs` row
that carries stats belongs to one user (RLS is owner-only). A scheduled or pg_cron run
writes one row per user it processed. `parent_run_id` links those rows to a global request
marker, which carries no stats (enforced by a CHECK). `started_at` and `finished_at` are
wall-clock. `logical_now` is the time used for decay.

```bash
cd web && cp .env.example .env.local && npm ci
npm run dev   # http://localhost:3000

# Demo data through the real API and dream pipeline. The API must already be running.
SOMNIA_API_URL=http://127.0.0.1:8000 \
SOMNIA_ADMIN_TOKEN=smn_dev_local_token_change_me \
SOMNIA_SERVICE_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/postgres \
  uv run python scripts/seed_demo.py

# After changing API models:
uv run python scripts/export_openapi.py && (cd web && npm run gen:api)
```

## Schema

Migrations live in `supabase/migrations/`. RLS is enabled on every table with
`user_id = auth.uid()` policies and column-level grants. Agents, for example, may only
update `memories.last_used_at` and `memories.use_count`.

| Table | What it holds |
| --- | --- |
| `devices` | Hashed device tokens |
| `sessions` | One agent session on a repo and branch |
| `events` | Outbox. Unique on `(session_id, seq)` |
| `chunks` | Redacted text and embeddings |
| `tasks` | Work queue with leases |
| `memories` | Type, scope, repo, branch, content, embedding, confidence, `last_used_at`, `superseded_by`, `source_session_ids` |
| `checkpoints` | Goal, state, next steps, files touched, git ref, pushed |
| `dream_runs` | One logged dream per user |

## Setup

```bash
uv sync                                   # Python 3.12 venv and deps from uv.lock
cp .env.example .env

# Local Supabase. Docker is required.
supabase start                            # uses supabase/config.toml
supabase db reset                         # migrations plus supabase/seed.sql
                                          # seed: dev user, device token smn_dev_local_token_change_me,
                                          #       somnia_api login password somnia_api_local

uv run somnia-api                         # http://localhost:8000/docs
uv run somnia-worker                      # ingest and dream loop, or pass --once
uv run somnia-admin create-device --user-id <auth.users id> --name laptop   # prints the token once
```

**Production (hosted Supabase).** Run the migrations (`supabase db push`), then
`alter role somnia_api login password '<strong secret>'` and point
`SOMNIA_API_DATABASE_URL` at that role. Give `SOMNIA_SERVICE_DATABASE_URL` (postgres or
the service role) only to the worker. Enable `pg_cron` before migrating if you want
database-side dream scheduling. Set `SOMNIA_PROVIDER=openai` plus `SOMNIA_LLM_*` for any
OpenAI-compatible endpoint. Embeddings must be 1536-d. The `dimensions` parameter is sent.

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy                               # strict
SOMNIA_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres uv run pytest
# for example: docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres pgvector/pgvector:pg17
```

DB tests create a throwaway database, apply `tests/sql/supabase_shim.sql` (stand-ins for
Supabase's `auth` schema and roles; a no-op on real Supabase) plus the real migrations, and
drop it afterwards. Without `SOMNIA_TEST_DATABASE_URL` they are skipped locally and fail in
CI.

## Known gaps

- The admin UI has no separate admin role. It acts as one user through a device token, and
  RLS limits what that token can see.
- Agent tasks use the table and `SKIP LOCKED`. A pgmq backend is not implemented yet.
- tiktoken downloads each encoding once on first use and caches it under
  `TIKTOKEN_CACHE_DIR`. Air-gapped hosts must pre-seed that cache.
- The embedding dimension is fixed at 1536 by the migration.
