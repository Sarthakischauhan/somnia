# somnia

Dreaming and memory implementation: a **shared memory service for coding agents**, backed by
Supabase Postgres + pgvector. Agents post what they do; a worker redacts, chunks and embeds it;
a scheduled "dream" consolidates sessions into durable memories and checkpoints; the next agent
on the same repo/branch starts with a ranked, token-budgeted context.

Harness integrations (Claude, Codex, Symphony plugins…) are intentionally **out of scope**:
any agent that can make HTTP calls can use the API below.

## Stack and why

| Choice | Why |
| --- | --- |
| **Python 3.12 + FastAPI** | Decided for the project; FastAPI derives validation and OpenAPI docs from type hints. |
| **Pydantic v2** | One typed model per request, response and DB row (`class_row`), discriminated unions for event kinds. |
| **psycopg 3 + psycopg-pool** | Typed, first-class Postgres driver; `SET LOCAL ROLE` + claims per transaction for RLS; `SKIP LOCKED` queues. No ORM: the SQL (vector ops, RLS, upserts) is the point. |
| **pgvector (HNSW, cosine)** | Embeddings live next to the data they describe; RLS applies to them too. |
| **uv, ruff, mypy `--strict`, pytest** | Fast reproducible env (`uv.lock`), one linter/formatter, strict typing with the pydantic plugin, tests against a real database. |

Code rules: small modules named for one job, no `utils`, no `getattr`/`hasattr`, providers behind
`typing.Protocol`.

## Architecture

```mermaid
flowchart LR
    subgraph Agents
        A1[agent on laptop]
        A2[agent in CI]
    end
    subgraph API["somnia-api (FastAPI, role: somnia_api → authenticated)"]
        AUTH[bearer token → sha256 → somnia_resolve_device()]
        ING[POST sessions / events / checkpoints / tasks]
        RET[GET status / context]
    end
    subgraph DB["Supabase Postgres + pgvector (RLS by user_id)"]
        EV[(sessions, events)]
        CH[(chunks + embeddings)]
        MEM[(memories + embeddings)]
        CP[(checkpoints)]
        TK[(tasks queue)]
        DR[(dream_runs)]
    end
    subgraph Worker["somnia-worker (service role only)"]
        PIPE[ingest: redact → chunk → embed]
        DREAM[dream: summarize → add/merge/supersede → decay]
    end
    LLM[[LLM + embedder Protocol<br/>OpenAI-compatible or fake]]
    CRON[[pg_cron: somnia_request_dream]]

    A1 & A2 -->|Bearer smn_…| AUTH --> ING & RET
    ING --> EV & TK & CP
    RET --> MEM & CP & TK
    RET -.query embedding.-> LLM
    EV --> PIPE --> CH
    PIPE -.-> LLM
    EV --> DREAM --> MEM & CP & DR
    DREAM -.-> LLM
    CRON --> DR
```

**Request path.** Every request resolves `Authorization: Bearer smn_…` through the
`SECURITY DEFINER` function `somnia_resolve_device(sha256(token))` (only `somnia_api` may call
it; token hashes are never readable). The request then runs in one transaction with
`SET LOCAL ROLE authenticated` and `request.jwt.claims.sub = user_id`, so `auth.uid()` and the RLS
policies scope every statement. The API process is only ever configured with
`SOMNIA_API_DATABASE_URL`; the service URL exists only in `WorkerSettings`.

**Ingestion.** `POST …/events` inserts with `ON CONFLICT (session_id, seq) DO NOTHING` and
returns `202` immediately. The `events` table is the outbox: the worker claims
`processed_at IS NULL` rows with `FOR UPDATE SKIP LOCKED`, renders them to text, redacts secrets
(private keys, AWS/GitHub/OpenAI/Slack/somnia tokens, JWTs, bearer headers, URL passwords,
`*_KEY=`/`password=` assignments), chunks with overlap and embeds into `chunks`.

**Tasks.** Agents enqueue work in `tasks`; any device of the same user claims it with
`FOR UPDATE SKIP LOCKED` and a lease (expired leases are reclaimable), then completes it.

**Retrieval.** `GET /v1/context` returns the latest open checkpoint for repo/branch plus memories
ranked by `max(cosine_sim, 0) × confidence × 0.5^(age_days / half_life)` where age counts from
`last_used_at` (or `created_at`). pgvector pre-selects `k × candidate_pool_factor` nearest
neighbours, Python ranks them, and greedy packing keeps the checkpoint plus as many top-k memories
as fit in `token_budget` (≈4 chars/token). Returned memories get `last_used_at` refreshed.

**Dreaming.** `somnia-worker` runs a dream every `SOMNIA_DREAM_INTERVAL_S` and whenever a
`dream_runs` row is `requested` (from `pg_cron` via `somnia_request_dream()`, scheduled by
the migration when the extension is enabled). Per session with new events:
1. *summarize* the redacted transcript → goal/state/next steps/files + memory candidates; write a
   checkpoint (closing the previous open one for that repo/branch);
2. *dedupe*: nearest active memory in the same scope; below `similarity_threshold` → **add**,
   otherwise the LLM decides **merge** (update in place, confidence boost, union
   `source_session_ids`) or **supersede** (new row inheriting provenance, old row gets
   `superseded_by`);
3. *decay*: memories idle for `decay_after_days` get `confidence × decay_factor` (floor
   `min_confidence`).

Nothing is hard-deleted. Each run is logged in `dream_runs` with counts or the error.

## API reference

All endpoints except `/healthz` need `Authorization: Bearer <device token>`. Interactive docs:
`/docs`.

| Method & path | Body / query | Returns |
| --- | --- | --- |
| `POST /v1/sessions` | `{repo, branch, git_ref?}` | `201` session (`device_id` from the token) |
| `POST /v1/sessions/{id}/events` | `{events: [{seq, kind, payload}]}` (≤500) | `202 {accepted, duplicates}` |
| `POST /v1/sessions/{id}/checkpoints` | `{goal, state, next_steps[], files_touched[], git_ref?, pushed}` | `201` checkpoint |
| `POST /v1/sessions/{id}/close` | – | session |
| `GET /v1/sessions/{id}/status` | – | `{session, latest_checkpoint, unprocessed_events}` |
| `POST /v1/tasks` | `{title, payload?, repo?, branch?, session_id?, priority?}` | `201` task |
| `POST /v1/tasks/claim` | `?lease_seconds=900` | running task, or `204` when empty |
| `POST /v1/tasks/{id}/complete` | `{status: done\|failed, result?}` | task |
| `GET /v1/tasks/{id}/status` | – | `{task, latest_checkpoint}` |
| `GET /v1/context` | `repo, branch, token_budget?, k=10, query?` | `{checkpoint, memories[{id,type,scope,content,confidence,similarity,recency,score}], token_budget, tokens_used, dropped}` |
| `GET /healthz` | – | `{status: ok}` |

Event kinds and payloads:

| kind | payload |
| --- | --- |
| `message` | `{role: user\|assistant\|system\|tool, content}` |
| `tool_call` | `{name, input: {}, output?, is_error?}` |
| `files_touched` | `{paths: [..], action: read\|write\|delete}` |
| `git_ref` | `{ref, pushed?}` (also updates `sessions.git_ref`) |

```bash
TOKEN=smn_dev_local_token_change_me
S=$(curl -s -XPOST localhost:8000/v1/sessions -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"repo":"acme/api","branch":"main"}' | jq -r .id)
curl -XPOST localhost:8000/v1/sessions/$S/events -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"events":[{"seq":1,"kind":"message","payload":{"role":"user","content":"remember: run uv run pytest"}}]}'
curl "localhost:8000/v1/context?repo=acme/api&branch=main&token_budget=800" -H "Authorization: Bearer $TOKEN"
```

## Schema

Supabase migrations in `supabase/migrations/`:
`devices` (hashed tokens) · `sessions` · `events` (unique `(session_id, seq)`) · `chunks` ·
`tasks` · `memories` (type, scope, repo, branch, content, embedding, confidence, last_used_at,
superseded_by, source_session_ids) · `checkpoints` (goal, state, next_steps, files_touched,
git_ref, pushed) · `dream_runs`. RLS is enabled on all of them with `user_id = auth.uid()`
policies and column-level grants (e.g. agents may only touch `memories.last_used_at/use_count`).

## Setup

```bash
uv sync                                   # Python 3.12 venv + deps from uv.lock
cp .env.example .env

# Local Supabase (Docker required)
supabase start                            # uses supabase/config.toml
supabase db reset                         # applies migrations + supabase/seed.sql
                                          # seed: dev user, device token smn_dev_local_token_change_me,
                                          #       somnia_api login password somnia_api_local

uv run somnia-api                         # http://localhost:8000/docs
uv run somnia-worker                      # ingest + dream loop (or --once)
uv run somnia-admin create-device --user-id <auth.users id> --name laptop   # prints token once
```

**Production (hosted Supabase):** run the migrations (`supabase db push`), then
`alter role somnia_api login password '<strong secret>'` and point `SOMNIA_API_DATABASE_URL`
at it. Give `SOMNIA_SERVICE_DATABASE_URL` (postgres/service role) only to the worker. Enable
`pg_cron` before migrating if you want DB-side dream scheduling. Set `SOMNIA_PROVIDER=openai`
plus `SOMNIA_LLM_*` for any OpenAI-compatible endpoint; embeddings must be 1536-d (the
`dimensions` parameter is sent).

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy                               # strict
SOMNIA_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres uv run pytest
# e.g. docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres pgvector/pgvector:pg17
```

DB tests create a throwaway database, apply `tests/sql/supabase_shim.sql` (stand-ins for
Supabase's `auth` schema and roles; a no-op on real Supabase) plus the real migrations, and drop
it afterwards. Without `SOMNIA_TEST_DATABASE_URL` they are skipped locally and fail in CI.

## Known gaps

- Agent tasks use the table + `SKIP LOCKED` backend; a pgmq backend is not implemented yet.
- Raw `events.payload` is stored as sent (RLS-protected); redaction applies to chunks, dream
  transcripts and memories.
- Token counting is a 4-chars/token estimate, not a model tokenizer.
- Embedding dimension is fixed at 1536 by the migration.
