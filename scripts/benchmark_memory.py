"""Run each synthetic history against an isolated, migrated Somnia database."""

import argparse
import json
import os
import statistics
from collections.abc import Iterator, Sequence
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx
import psycopg
from core_ai import StreamEvent
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo
from pydantic import SecretStr

from somnia.api.app import create_app
from somnia.config import ApiSettings, DreamPolicy, ProviderSettings
from somnia.ingestion.pipeline import process_pending_events
from somnia.memory.dreaming import run_dream
from somnia.memory.inference import OpenAiEmbedder, SymphonyLlm, embedding_client
from somnia.memory.models import (
    Embedder,
    Llm,
    ProfileItem,
    ProfileSection,
    ReconcileDecision,
    SessionDigest,
)
from somnia.memory.tokenizer import TiktokenCounter
from tests.conftest import ROOT, make_device
from tests.fixtures.providers import FakeEmbedder, FakeLlm

FACTS = [
    "Quartz ledger rebuild uses the amber snapshot manifest",
    "Juniper notification retries use the cobalt queue",
    "Maple audit exports require the violet schema",
    "Birch metrics processing uses the silver cursor",
]
OLD = "Webhook delivery policy requires retries for every transient gateway timeout"
NEW = "Webhook delivery policy never requires retries for every transient gateway timeout"
LATE = "Opal cleanup uses the crimson retention index"
PRIVATE = "Private obsidian deployment requires the scarlet handoff"
BRANCH = "Unmerged topaz branch uses the green migration ledger"


class MeteredOfflineLlm(FakeLlm):
    """Count provider-boundary tokens for offline runs using Somnia's tokenizer."""

    def __init__(self, counter: TiktokenCounter) -> None:
        self.counter = counter
        self.input_tokens = self.output_tokens = self.calls = 0

    def record(self, prompt: str, completion: str) -> None:
        self.input_tokens += self.counter.count(prompt)
        self.output_tokens += self.counter.count(completion)
        self.calls += 1

    def summarize_session(self, transcript: str) -> SessionDigest:
        result = super().summarize_session(transcript)
        self.record(transcript, result.model_dump_json())
        return result

    def reconcile(self, existing: str, candidate: str, candidate_scope: Any) -> ReconcileDecision:
        result = super().reconcile(existing, candidate, candidate_scope)
        self.record(f"{existing}\n{candidate_scope}\n{candidate}", result.model_dump_json())
        return result

    def classify_profile(self, items: Sequence[ProfileItem]) -> list[ProfileSection]:
        result = super().classify_profile(items)
        if items:
            self.record("\n".join(item.model_dump_json() for item in items), json.dumps(result))
        return result


class Usage:
    def __init__(self) -> None:
        self.input_tokens = self.output_tokens = self.calls = 0
        self.missing_usage = 0

    def record(self, event: StreamEvent) -> None:
        self.calls += 1
        if event.prompt_tokens is None or event.completion_tokens is None:
            self.missing_usage += 1
        self.input_tokens += event.prompt_tokens or 0
        self.output_tokens += event.completion_tokens or 0


@contextmanager
def database(url: str) -> Iterator[tuple[str, str]]:
    name = f"somnia_bench_{uuid4().hex}"
    with psycopg.connect(url, autocommit=True) as admin:
        admin.execute(f'create database "{name}"')
        try:
            service = make_conninfo(url, dbname=name)
            with psycopg.connect(service, autocommit=True) as conn:
                conn.execute((ROOT / "tests/sql/supabase_shim.sql").read_text())
                for migration in sorted((ROOT / "supabase/migrations").glob("*.sql")):
                    conn.execute(migration.read_text())
                api_password = os.getenv("SOMNIA_BENCH_API_PASSWORD", "somnia_bench")
                conn.execute(
                    sql.SQL("alter role somnia_api login password {}").format(
                        sql.Literal(api_password)
                    )
                )
                conn.execute(f'alter database "{name}" set search_path = public, extensions')
            yield service, make_conninfo(service, user="somnia_api", password=api_password)
        finally:
            admin.execute(f'drop database "{name}" with (force)')


def message(seq: int, text: str) -> dict[str, Any]:
    return {"seq": seq, "kind": "message", "payload": {"role": "user", "content": text}}


def history(size: int) -> list[list[dict[str, Any]]]:
    sessions = []
    for start in range(0, size, 100):
        events = [message(1, f"Investigate build diagnostics for session {start // 100}")]
        for seq in range(3, min(100, size - start) + 2):
            if seq <= 6:
                fact = FACTS[seq - 3]
                events.append(message(seq, f"remember: {fact}"))
            elif seq == 7 and start == 0:
                events.append(message(seq, f"decision: {OLD}"))
            elif seq % 3 == 0:
                events.append(
                    {
                        "seq": seq,
                        "kind": "files_touched",
                        "payload": {"paths": [f"src/component_{seq % 13}.py"], "action": "read"},
                    }
                )
            else:
                events.append(
                    {
                        "seq": seq,
                        "kind": "tool_call",
                        "payload": {
                            "name": "pytest",
                            "output": f"test_component_{seq % 13} passed",
                        },
                    }
                )
        sessions.append(events)
    return sessions


def payload(response: httpx.Response) -> Any:
    response.raise_for_status()
    return response.json()


def run_case(url: str, sessions: list[list[dict[str, Any]]], mode: str) -> dict[str, Any]:
    now = datetime.now(UTC)
    counter = TiktokenCounter("o200k_base")
    offline = MeteredOfflineLlm(counter)
    live = Usage()
    metering = offline if mode == "offline" else live
    settings = ProviderSettings()
    if mode == "live" and not settings.llm_api_key.get_secret_value():
        raise ValueError("Set SOMNIA_LLM_API_KEY for live benchmarks")
    metrics: dict[str, Any] = {"expected_facts": len(FACTS)}
    with (
        database(url) as (service, api),
        psycopg.connect(service, autocommit=True) as conn,
        ExitStack() as resources,
    ):
        embedder: Embedder
        llm: Llm
        if mode == "offline":
            embedder, llm = FakeEmbedder(), offline
        else:
            provider = resources.enter_context(embedding_client(settings))
            embedder = OpenAiEmbedder(provider, settings.embedding_model)
            llm = resources.enter_context(SymphonyLlm(settings, live.record))
        owner = make_device(conn)
        stranger = make_device(conn)
        app = create_app(ApiSettings(api_database_url=SecretStr(api)), embedder, clock=lambda: now)
        policy = DreamPolicy()

        def dream() -> None:
            nonlocal now
            now += timedelta(microseconds=1)
            run_dream(conn, llm, embedder, policy, now)

        def scalar(sql: str, params: tuple[Any, ...] = ()) -> Any:
            row = conn.execute(sql, params).fetchone()
            assert row is not None
            return row[0]

        def context(client: TestClient, query: str, headers: dict[str, str]) -> Any:
            return payload(
                client.get(
                    "/v1/context",
                    headers=headers,
                    params={"repo": "bench/memory", "branch": "main", "query": query, "k": 5},
                )
            )

        def new_session(client: TestClient, headers: dict[str, str], branch: str = "main") -> str:
            return str(
                payload(
                    client.post(
                        "/v1/sessions",
                        headers=headers,
                        json={"repo": "bench/memory", "branch": branch},
                    )
                )["id"]
            )

        def send(
            client: TestClient, session: str, headers: dict[str, str], events: list[dict[str, Any]]
        ) -> None:
            payload(
                client.post(
                    f"/v1/sessions/{session}/events",
                    headers=headers,
                    json={"events": events},
                )
            )

        def drain() -> None:
            while process_pending_events(conn, embedder, 100, 1200, 150):
                pass

        def score(client: TestClient, phase: str) -> None:
            timings = []
            hits = []
            for fact in FACTS:
                for query in (fact, " ".join(reversed(fact.split()))):
                    started = perf_counter()
                    result = context(client, query, owner.headers)
                    timings.append((perf_counter() - started) * 1000)
                    texts = [item["content"] for item in result["memories"]]
                    texts.extend(
                        item["content"] for item in (result["profile"] or {}).get("entries", [])
                    )
                    hits.append(any(fact.lower() in text.lower() for text in texts))
            metrics[f"{phase}_recall"] = statistics.mean(hits)
            metrics[f"{phase}_median_ms"] = statistics.median(timings)
            metrics[f"{phase}_max_ms"] = max(timings)

        with TestClient(app) as client:
            started = perf_counter()
            ids = []
            for events in sessions:
                session = new_session(client, owner.headers)
                ids.append(session)
                send(client, session, owner.headers, events)
            metrics["upload_ms"] = (perf_counter() - started) * 1000
            started = perf_counter()
            drain()
            metrics["ingestion_ms"] = (perf_counter() - started) * 1000
            metrics["chunks"] = scalar("select count(*) from public.chunks")
            score(client, "before_dream")
            started = perf_counter()
            dream()
            metrics["dream_ms"] = (perf_counter() - started) * 1000
            metrics["initial_calls"] = metering.calls
            metrics["initial_input_tokens"] = metering.input_tokens
            metrics["initial_output_tokens"] = metering.output_tokens
            score(client, "after_dream")
            memory_rows = conn.execute(
                "select content from public.memories where superseded_by is null"
            ).fetchall()
            metrics["durable_facts_found"] = sum(
                any(fact.lower() in row[0].lower() for row in memory_rows) for fact in FACTS
            )
            metrics["initial_memory_precision"] = (
                sum(
                    any(fact.lower() in row[0].lower() for fact in [*FACTS, OLD])
                    for row in memory_rows
                )
                / len(memory_rows)
                if memory_rows
                else 0.0
            )
            metrics["duplicate_fact_rows"] = sum(
                max(0, sum(fact.lower() in row[0].lower() for row in memory_rows) - 1)
                for fact in FACTS
            )
            chunk_tokens = sum(
                counter.count(row[0]) for row in conn.execute("select content from public.chunks")
            )
            memory_tokens = sum(counter.count(row[0]) for row in memory_rows)
            metrics["chunk_to_active_memory_token_ratio"] = (
                chunk_tokens / memory_tokens if memory_tokens else None
            )
            checkpoints = scalar("select count(*) from public.checkpoints")
            metrics["initial_checkpoints"] = checkpoints
            calls = metering.calls
            dream()
            metrics["noop_calls"] = metering.calls - calls
            metrics["noop_checkpoints"] = (
                scalar("select count(*) from public.checkpoints") - checkpoints
            )
            send(client, ids[0], owner.headers, [message(2, f"remember: {LATE}")])
            send(client, ids[-1], owner.headers, [message(102, f"decision: {NEW}")])
            other = new_session(client, stranger.headers)
            send(client, other, stranger.headers, [message(1, f"remember: {PRIVATE}")])
            branch = new_session(client, owner.headers, "topic")
            send(client, branch, owner.headers, [message(1, f"remember: {BRANCH}")])
            drain()
            metrics["late_visible_before_dream"] = (
                LATE.lower() in json.dumps(context(client, LATE, owner.headers)).lower()
            )
            metrics["cross_branch_chunk"] = (
                BRANCH.lower() in json.dumps(context(client, BRANCH, owner.headers)).lower()
            )
            metrics["cross_user_before_dream"] = (
                PRIVATE.lower() in json.dumps(context(client, PRIVATE, owner.headers)).lower()
            )
            started = perf_counter()
            dream()
            metrics["incremental_ms"] = (perf_counter() - started) * 1000
            metrics["incremental_checkpoints"] = (
                scalar("select count(*) from public.checkpoints") - checkpoints
            )
            metrics["late_memory"] = scalar(
                "select exists(select 1 from public.memories where content ilike %s)",
                (f"%{LATE}%",),
            )
            metrics["late_retrievable_after_dream"] = (
                LATE.lower() in json.dumps(context(client, LATE, owner.headers)).lower()
            )
            metrics["contradictions"] = scalar("select count(*) from public.memory_conflicts")
            metrics["cross_user_after_dream"] = (
                PRIVATE.lower() in json.dumps(context(client, PRIVATE, owner.headers)).lower()
            )
            metrics["other_user_recall"] = (
                PRIVATE.lower() in json.dumps(context(client, PRIVATE, stranger.headers)).lower()
            )
        with TestClient(
            create_app(ApiSettings(api_database_url=SecretStr(api)), embedder, clock=lambda: now)
        ) as restarted:
            score(restarted, "restart")
        run_dream(conn, llm, embedder, policy, now + timedelta(days=30))
        metrics["decayed_memories"] = scalar(
            "select count(*) from public.memories where last_decayed_at is not null"
        )
    metrics["provider_calls"] = metering.calls
    metrics["input_tokens"] = metering.input_tokens
    metrics["output_tokens"] = metering.output_tokens
    metrics["missing_usage_responses"] = live.missing_usage
    return metrics


def main() -> None:
    import pixeltable as pxt

    from scripts.benchmark_evaluation import passes_lifecycle

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", nargs="+", type=int, default=[100, 1000, 10000])
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = os.environ["SOMNIA_BENCH_DATABASE_URL"]
    if min(args.sizes) < 100 or any(size % 100 for size in args.sizes):
        parser.error("sizes must be positive multiples of 100")
    table_name = f"somnia_bench_{uuid4().hex}"
    table = pxt.create_table(
        table_name, {"size_events": pxt.Int, "events_json": pxt.Json, "metrics": pxt.Json}
    )

    table.add_computed_column(lifecycle_ok=passes_lifecycle(table.metrics))
    print(f"Pixeltable results: {table_name}", flush=True)
    results = []
    for size in args.sizes:
        table.insert([{"size_events": size, "events_json": history(size), "metrics": {}}])
        sessions = (
            table.where(table.size_events == size)
            .select(table.events_json)
            .collect()[0]["events_json"]
        )
        metrics = run_case(url, sessions, args.mode)
        table.where(table.size_events == size).update({"metrics": metrics})
        result = (
            table.where(table.size_events == size)
            .select(table.size_events, table.metrics, table.lifecycle_ok)
            .collect()[0]
        )
        results.append(dict(result))
        print(json.dumps(result), flush=True)
        args.output.write_text(json.dumps({"mode": args.mode, "results": results}, indent=2) + "\n")


if __name__ == "__main__":
    main()
