"""`somnia-worker`: ingest loop + scheduled / requested dream runs (service role only)."""

import argparse
import logging
import signal
import time
from datetime import UTC, datetime
from threading import Event

import psycopg

from somnia.config import ProviderSettings, WorkerSettings
from somnia.db.client import Conn
from somnia.ingestion.pipeline import process_pending_events
from somnia.memory.dreaming import run_dream
from somnia.memory.inference import OpenAiEmbedder, SymphonyLlm, embedding_client
from somnia.memory.models import Embedder, Llm
from somnia.memory.run_log import claim_requested_run, retry_run
from somnia.memory.triggers import enqueue_chunk_thresholds, enqueue_idle_sessions

log = logging.getLogger("somnia.worker")


def _tick(
    conn: Conn, settings: WorkerSettings, llm: Llm, embedder: Embedder, dream_due: bool
) -> int:
    ingested = process_pending_events(
        conn,
        embedder,
        settings.ingest_batch_size,
        settings.chunk_max_chars,
        settings.chunk_overlap_chars,
    )
    enqueue_idle_sessions(conn, datetime.now(UTC), settings.idle_minutes)
    enqueue_chunk_thresholds(conn, settings.chunk_threshold)
    # Keep the claim locked until results or retry state have committed.
    with conn.transaction():
        requested = claim_requested_run(conn)
        if requested is not None:
            try:
                with conn.transaction():
                    run_dream(conn, llm, embedder, settings, datetime.now(UTC), run_id=requested)
            except Exception as exc:
                retry_run(conn, requested, type(exc).__name__)
                log.warning("dream %s failed (%s)", requested, type(exc).__name__)
    if requested is None and dream_due:
        run_dream(conn, llm, embedder, settings, datetime.now(UTC))
    return ingested


def main() -> None:
    parser = argparse.ArgumentParser(prog="somnia-worker")
    parser.add_argument("--once", action="store_true", help="ingest + dream once, then exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = WorkerSettings()  # values come from the environment
    provider = ProviderSettings()
    stopped = Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with embedding_client(provider) as client, SymphonyLlm(provider) as llm:
        embedder = OpenAiEmbedder(client, provider.embedding_model)
        last_dream = float("-inf")
        while not stopped.is_set():
            try:
                with psycopg.connect(
                    settings.service_database_url.get_secret_value(),
                    autocommit=True,
                    connect_timeout=5,
                ) as conn:
                    while not stopped.is_set():
                        due = time.monotonic() - last_dream >= settings.dream_interval_s
                        if args.once:
                            if not _tick(conn, settings, llm, embedder, dream_due=False):
                                _tick(conn, settings, llm, embedder, dream_due=True)
                                return
                            continue
                        ingested = _tick(conn, settings, llm, embedder, dream_due=due)
                        if due:
                            last_dream = time.monotonic()
                        if not ingested:
                            stopped.wait(settings.poll_interval_s)
            except Exception as exc:
                if args.once:
                    raise
                log.warning("worker tick failed (%s); retrying", type(exc).__name__)
                stopped.wait(max(5.0, settings.poll_interval_s))
