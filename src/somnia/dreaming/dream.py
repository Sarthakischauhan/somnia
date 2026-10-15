"""One dream run: consolidate sessions, decay unused memories, log to dream_runs."""

from datetime import datetime
from uuid import UUID

from somnia.db.connection import Conn
from somnia.dreaming.consolidate import consolidate_session, sessions_needing_dream
from somnia.dreaming.memory_store import decay_unused
from somnia.dreaming.policy import DreamPolicy
from somnia.dreaming.run_log import DreamCounts, finish_run, start_run
from somnia.providers.protocols import Embedder, Llm


def run_dream(
    conn: Conn,
    llm: Llm,
    embedder: Embedder,
    policy: DreamPolicy,
    now: datetime,
    *,
    trigger: str = "schedule",
    run_id: UUID | None = None,
) -> UUID:
    """Requires the service connection (autocommit). Returns the dream_runs id."""
    if run_id is None:
        run_id = start_run(conn, trigger, now)
    counts = DreamCounts()
    try:
        with conn.transaction():
            for session in sessions_needing_dream(conn):
                consolidate_session(conn, session, llm, embedder, policy, counts, now)
            counts.memories_decayed = decay_unused(
                conn, now, policy.decay_after_days, policy.decay_factor, policy.min_confidence
            )
    except Exception as exc:
        finish_run(conn, run_id, DreamCounts(), f"{type(exc).__name__}: {exc}", now)
        raise
    finish_run(conn, run_id, counts, None, now)
    return run_id
