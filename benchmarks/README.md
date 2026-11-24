# Somnia memory benchmark

The runner uploads synthetic histories via FastAPI, drains the actual worker ingestion
function, runs the production consolidation and profile builder, and retrieves context
through the authenticated API. It restarts the API and its connection pool against the
same database to check persistence. Pixeltable stores each input and its measurements
and evaluates the scenario. Somnia uses PostgreSQL and pgvector throughout.

## Run locally

From the repository root, start a dedicated PostgreSQL instance with pgvector, for example:

```bash
docker run --name somnia-bench-pg -d -p 127.0.0.1:55432:5432 \
  -e POSTGRES_PASSWORD=postgres pgvector/pgvector:pg18-trixie
docker exec somnia-bench-pg pg_isready -U postgres
docker exec somnia-bench-pg createdb -U postgres pixeltable
export SOMNIA_BENCH_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:55432/postgres
export PIXELTABLE_DB_CONNECT_STR=postgresql://postgres:postgres@127.0.0.1:55432/pixeltable
uv run --locked --with pixeltable==0.7.26 python -m scripts.benchmark_memory --output results.json
SOMNIA_TEST_DATABASE_URL="$SOMNIA_BENCH_DATABASE_URL" uv run --locked pytest -q
```

Wait for `pg_isready` to succeed before creating the catalog. Each case creates,
migrates and drops a disposable Somnia database. The runner sets the cluster-wide
`somnia_api` role password, so use a dedicated instance. The runner leaves the named
Pixeltable results table available for inspection. For the baseline, check out
`f7c927b49c5626e88721836e63ff0d293216b088` in a separate worktree, copy
`scripts/__init__.py`, `scripts/benchmark_memory.py` and
`scripts/benchmark_evaluation.py` from the PR, then run the same command there.

The default offline run uses Somnia's deterministic providers. For actual model usage,
set `SOMNIA_LLM_API_KEY` and add `--mode live`. Configure
`SOMNIA_LLM_BASE_URL`, `SOMNIA_CHAT_MODEL` and `SOMNIA_EMBEDDING_MODEL` as
needed. The live runner records provider-reported chat usage, including how many
responses omitted it. The embedding endpoint must support the 1,536 dimensions Somnia
requests. For a small check, add `--sizes 100`.

For the application, apply the new migration before restarting the API and workers.
Follow the [local application setup](../CONTRIBUTING.md) for the API URL, service URL,
seed data and worker commands. The migration preserves progress from the old
watermark. Events already skipped by the old logic cannot be distinguished reliably
from events previously consolidated, so the migration backfills them as dreamt.

## What the measurements cover

- Each size uses 100-event sessions with tool calls, file reads and repeated durable
  facts. The late event, contradiction, secondary branch and second user are added
  after the initial phases.
- Retrieval recall is the fraction of eight queries whose expected fact appears in
  returned chunks, memories or profile entries. The matching is lexical and requires
  the expected phrase. Memory precision is the share of active memory rows containing
  an expected seeded fact or decision. The workload tests this synthetic corpus only.
- Latencies are one local run per size. Retrieval median and maximum cover eight
  calls per phase. The API runs in process. The ingestion phase excludes HTTP upload,
  which is recorded separately.
- Compression divides chunk content tokens by active memory content tokens after the
  first dream. It excludes checkpoints, profiles, indexes and disk usage. Raw data
  remains in PostgreSQL.
- Offline input and output tokens count provider-boundary text and serialized
  responses using `o200k_base`. Live chat metering includes the provider's prompt
  overhead and can report different counts. Live model quality and billing were
  unmeasured because this run had no provider credentials.

## Measured results

PostgreSQL 18.4, pgvector 0.8.5, Python 3.12, Pixeltable 0.7.26. Values are baseline → fixed.

| Events | Ingestion ms | First dream ms | Median retrieval ms before dream | Median retrieval ms after dream | First dream provider calls | First dream input / output tokens | Chunk / memory tokens |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 82.3 → 86.5 | 26.1 → 25.8 | 7.5 → 8.7 | 5.7 → 7.2 | 2 → 2 | 1,581 / 263 → 1,581 / 263 | 33.3× (both) |
| 1,000 | 719.6 → 669.4 | 100.6 → 80.0 | 16.8 → 12.6 | 8.2 → 6.9 | 47 → 11 | 15,738 / 3,251 → 15,054 / 2,207 | 332.9× (both) |
| 10,000 | 8187.3 → 8641.7 | 896.4 → 749.8 | 151.8 → 74.4 | 83.5 → 9.4 | 497 → 101 | 157,308 / 33,131 → 149,784 / 21,647 | 3,328.6× (both) |

At every size, both versions recalled all eight queries before dreaming, after
dreaming and after restarting the API. Both stored all four expected facts with
zero duplicate rows, recorded one contradiction, decayed idle memories and kept
the second user's data isolated. An unchanged history produced zero new
checkpoints and zero additional model calls.

The baseline missed the late event in both retrieval and dreaming at every size
and returned an undreamt chunk from the other branch. The fixed version retrieved
and consolidated the late event and excluded the other branch's chunk at all
three sizes. The fixed suites also verify that served profile memories refresh
their usage and that identical candidates retain provenance without a
reconciliation call.

Raw measurements are in [baseline.json](baseline.json) and [fixed.json](fixed.json).
