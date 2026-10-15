"""`somnia-worker`: ingest loop + scheduled / requested dream runs (service role only)."""

import argparse
import logging
import time
from datetime import UTC, datetime

import psycopg

from somnia.config import ProviderSettings, WorkerSettings
from somnia.db.connection import Conn
from somnia.dreaming.dream import run_dream
from somnia.dreaming.policy import DreamPolicy
from somnia.dreaming.run_log import claim_requested_run
from somnia.ingest.pipeline import process_pending_events
from somnia.providers.factory import Providers, build_providers

log = logging.getLogger("somnia.worker")


def _tick(conn: Conn, settings: WorkerSettings, providers: Providers, dream_due: bool) -> int:
    ingested = process_pending_events(
        conn,
        providers.embedder,
        settings.ingest_batch_size,
        settings.chunk_max_chars,
        settings.chunk_overlap_chars,
    )
    policy = DreamPolicy.from_settings(settings)
    requested = claim_requested_run(conn)
    if requested is not None:
        run_dream(
            conn, providers.llm, providers.embedder, policy, datetime.now(UTC), run_id=requested
        )
    elif dream_due:
        run_dream(conn, providers.llm, providers.embedder, policy, datetime.now(UTC))
    return ingested


def main() -> None:
    parser = argparse.ArgumentParser(prog="somnia-worker")
    parser.add_argument("--once", action="store_true", help="ingest + dream once, then exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    settings = WorkerSettings()  # values come from the environment
    providers = build_providers(ProviderSettings())
    with psycopg.connect(settings.service_database_url.get_secret_value(), autocommit=True) as conn:
        if args.once:
            while _tick(conn, settings, providers, dream_due=False):
                pass
            _tick(conn, settings, providers, dream_due=True)
            return
        last_dream = 0.0
        while True:
            due = time.monotonic() - last_dream >= settings.dream_interval_s
            if due:
                last_dream = time.monotonic()
            if _tick(conn, settings, providers, dream_due=due) == 0:
                time.sleep(settings.poll_interval_s)
