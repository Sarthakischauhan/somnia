# Somnia production refactor

Baseline is Somnia main at `0c4f879148e37a3db177df4de65038933a0008e8`. Symphony
main was inspected at `fde4d1710258f303f777e4f9d97d3e1d54952189`. The refactor
uses the released `symphony-core==0.0.8` and `symphony-harness==0.0.10` APIs.

## Architecture

| Area | Before | After |
| --- | --- | --- |
| Deployment | Custom process supervisor on one Render service | Separate API and worker services on Render, built from the same Dockerfile. Dashboard deploys independently. |
| Authentication | Supabase access tokens for dashboard routes and Somnia device tokens for agent routes | Shared user-scoped management and retrieval with either credential. Device-backed writes still use the existing agent token and keep device provenance. |
| Ingestion | Durable events table, one INSERT per event | One INSERT per request batch, with commit before the 202 response. Workers continue to claim pending events with SKIP LOCKED. |
| Inference | Custom chat client with an in-package fake provider | Symphony Core AI streaming plus Pydantic validation. Deterministic providers are test fixtures. |
| Dreaming | Incremental event cursor, SQL reconciliation, custom chat calls | Same incremental cursor and memory lifecycle. Core Harness investigates unresolved contradictions using bounded, read-only, user-scoped evidence. |
| Session continuity | Checkpoint, profiles and semantic results | Checkpoint, profiles and semantic results plus explicit branch-relevant open tasks rendered by the agent CLI. |
| Management | User-scoped operations under a store package and admin routes | Queries organized by memory, sessions, ingestion and dreaming. Dashboard uses canonical /v1 endpoints. The deployed dashboard can still use the old routes during rollout. |

Simple session digests, classification and reconciliation use one model turn. The harness
runs only when reconciliation flags an ambiguous contradiction. Its tool returns redacted
source events from the same user. Somnia applies validated model decisions through its
existing database transactions. Core AI currently exposes neither provider-enforced JSON
schemas nor embeddings. The OpenAI-compatible 1,536-dimension embedding adapter preserves
the existing vector format and model selection. A JSON shape described in the prompt and
Pydantic validation constrain Somnia's model output.

## Directory tree

The tree shows backend source and its deployment, integration and verification directories.
Historical SQL migrations and the existing dashboard are retained.

```text
somnia/
  src/somnia/
    admin/           cli.py
    api/             app.py, dependencies.py, serve.py, schemas.py,
                     routes_context.py, routes_management.py,
                     routes_sessions.py, routes_tasks.py
    auth/            principal.py, supabase.py, tokens.py
    db/              connection.py, vectors.py
    dreaming/        consolidate.py, dream.py, management.py, memory_store.py,
                     profile_builder.py, run_log.py, triggers.py
    ingest/          chunking.py, event_models.py, event_text.py, events.py,
                     payload_redaction.py, pipeline.py, redaction.py
    memory/          conflicts.py, inference.py, manage.py, models.py
    retrieval/       context.py, disputes.py, hybrid.py, packing.py,
                     profile_context.py, ranking.py, tokenizer.py
    sessions/        checkpoints.py, models.py, overview.py, sessions.py, tasks.py
    config.py
    worker.py
  supabase/migrations/
  agent/
  plugins/
  web/
  scripts/
  tests/fixtures/
  benchmarks/
  .env.example
  Dockerfile
  pyproject.toml
  render.yaml
```

## Removal and code counts

- Removed the process supervisor and its dedicated tests. Render owns process lifecycle.
- Removed the provider factory and handwritten chat transport. Core AI owns the transport,
  while Pydantic validates Somnia's digest, reconciliation and classification models.
- Relocated the deterministic providers to test fixtures. Production uses configured models.
- Removed the generic `store/` package. Memory, conflict, dream, session, task and event
  queries moved beside their use cases. This changes ownership and imports without deleting
  the active dashboard features.
- Removed the duplicated dream policy configuration and collapsed the worker entry point
  into one module. Device provisioning remains an operator-only function with active CLI consumers.
- No runtime dependency was removed. The direct runtime dependency count went from 8 to 10
  with the two Symphony packages. PostgreSQL, pgvector, Supabase and the existing tokenizer remain.

| Scope | Baseline | Refactor | Reduction |
| --- | ---: | ---: | ---: |
| `src/**.py` physical lines | 3,627 | 3,544 | 2.29% |
| Python and handwritten migration SQL lines | 4,138 | 4,093 | 1.09% |
| Python and migration SQL files | 69 | 63 | 8.70% |

Physical lines include comments and blanks. The combined count includes all historical
migrations and the new migration. Generated clients, lockfiles, tests, demo data,
benchmarks and the separate agent and web clients are outside the backend count.
The 50% goal was not reached. On this baseline it required removing another 2,024
lines after the refactor. The code remaining owns active workflows that Symphony and
Supabase do not supply, including scoped hybrid retrieval, project profile maintenance,
memory lineage, contradiction resolution, redaction, device-backed agent hooks, and the
dashboard's memory, sessions and task views. This PR preserves those workflows.

## Benchmark

PostgreSQL 17.12 with pgvector 0.8.0, one local run per size, Python 3.12, in-process
HTTP and deterministic providers. Both checkouts ran their actual API, ingestion,
retrieval and dreaming functions. SQL counts use `pg_stat_statements` and include
schema setup in the total. Upload timings are the total for the initial workload, including
session creation. Event INSERT counts include later scenario events and additional users.
Pixeltable reporting was bypassed for both checkouts.

| Events | API upload ms | Worker ingestion ms | First dream ms | Retrieval before dream median ms | Retrieval after dream median ms | SQL calls | Event INSERT calls |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 34.4 → 19.0 | 64.3 → 59.7 | 22.9 → 20.7 | 7.0 → 7.4 | 7.2 → 6.9 | 901 → 840 | 104 → 5 |
| 1,000 | 221.4 → 125.2 | 681.9 → 705.1 | 92.1 → 81.0 | 14.4 → 14.9 | 7.3 → 8.4 | 2,958 → 2,016 | 1,004 → 14 |
| 10,000 | 2,089.5 → 999.8 | 8,232.5 → 8,115.8 | 703.1 → 679.8 | 71.8 → 78.2 | 9.4 → 9.4 | 23,478 → 13,716 | 10,004 → 104 |

Recall and memory precision were 100% on this corpus in both versions at all sizes.
Both retained all four seeded facts, stored zero duplicate fact rows, excluded cross-user
and cross-branch data, recorded the contradiction, persisted across API restart and did
zero new model work on an unchanged history. The first dream used 2, 11 and 101
deterministic model calls at the three sizes in both versions. Estimated input/output tokens
were 1,581/263, 15,054/2,207 and 149,784/21,647 respectively. See
[the raw measurements](refactor-comparison.json) for later phases and full results.
The results measure local replay and synthetic quality. Live credentials, real usage,
billed tokens and managed-service latency were unavailable.

To reproduce, start a disposable PostgreSQL instance with pgvector. Preload
`pg_stat_statements` and create that extension in the maintenance database. Set
`SOMNIA_BENCH_DATABASE_URL` to that database. From each checkout, run
`PYTHONPATH=. uv run --locked python /path/to/refactor/benchmarks/measure_workload.py`.
Use the same copy of the runner and the same database instance for both checkouts.

## Verification and deployment

- Main baseline passed 69 backend tests. The refactor passed 62 backend tests against
  PostgreSQL and pgvector with the Supabase Auth shim. New regressions cover concurrent
  workers, dream retries, open-task handoff to a second device, and mock-streamed Core AI
  and Core Harness integration. The counts differ because the subprocess launcher tests
  were removed with the launcher.
- The agent CLI passed 65 tests. Ruff, backend and agent mypy, generated OpenAPI and TypeScript
  client, and dashboard lint, typecheck and production build were checked.
- Stop the old worker before applying `20261016000009_tasks_and_dream_retries.sql`.
  It adds task scope enforcement and an open-task index, adds retry metadata, and handles
  existing stranded dream claims. It leaves user data and vectors intact.
- Follow the [Render deployment steps](../README.md#deploy-on-render) for the API, worker,
  dashboard, role-specific database URLs, provider key and Supabase OAuth setup.
- Render deployment and managed Supabase OAuth were not exercised here. Core AI inference
  was verified with mocked streams only. The worker still holds database transactions during
  inference for claimed work. Event ingestion retries failed embedding batches as a unit.
  Device provisioning remains manual, and integrations must submit tasks to the task API
  to have them listed explicitly in handoffs. The task list is outside the semantic token budget.
