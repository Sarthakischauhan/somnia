"""Dream runs: per user, consolidate sessions and decay unused memories, logging one
dream_runs row per user so stats never mix across users."""

from datetime import datetime
from uuid import UUID

from somnia.db.connection import Conn
from somnia.dreaming.consolidate import consolidate_session, sessions_needing_dream
from somnia.dreaming.memory_store import decay_unused
from somnia.dreaming.policy import DreamPolicy
from somnia.dreaming.profile_builder import profile_repos, rebuild_profile
from somnia.dreaming.run_log import DreamCounts, finish_run, load_request, start_user_run
from somnia.providers.protocols import Embedder, Llm


def dream_users(conn: Conn) -> list[UUID]:
    """Users with sessions to consolidate or active memories that may decay."""
    rows = conn.execute(
        "select s.user_id from public.sessions s where exists (select 1 from public.events e"
        "   where e.session_id = s.id and e.seq > s.dreamed_through_seq)"
        " union select m.user_id from public.memories m"
        "   where m.superseded_by is null and m.archived_at is null"
        " order by 1"
    ).fetchall()
    return [UUID(str(r[0])) for r in rows]


def run_dream(
    conn: Conn,
    llm: Llm,
    embedder: Embedder,
    policy: DreamPolicy,
    now: datetime,
    *,
    trigger: str = "schedule",
    run_id: UUID | None = None,
) -> list[UUID]:
    """Requires the service connection (autocommit). `now` is the logical time used for
    decay. With `run_id` (a claimed request): a user-owned request is processed for that
    user in place; a global request fans out to per-user rows linked by parent_run_id.
    Returns the per-user dream_runs ids."""
    if run_id is not None:
        request = load_request(conn, run_id)
        if request.user_id is not None:
            _dream_for_user(conn, llm, embedder, policy, now, request.user_id, run_id, request.repo)
            return [run_id]
        try:
            ids = _fan_out(conn, llm, embedder, policy, now, request.trigger, run_id)
        except Exception as exc:
            finish_run(conn, run_id, DreamCounts(), f"{type(exc).__name__}: {exc}", now)
            raise
        finish_run(conn, run_id, DreamCounts(), None, now)
        return ids
    return _fan_out(conn, llm, embedder, policy, now, trigger, None)


def _fan_out(
    conn: Conn,
    llm: Llm,
    embedder: Embedder,
    policy: DreamPolicy,
    now: datetime,
    trigger: str,
    parent_run_id: UUID | None,
) -> list[UUID]:
    ids = []
    for user_id in dream_users(conn):
        user_run = start_user_run(conn, user_id, trigger, now, parent_run_id)
        _dream_for_user(conn, llm, embedder, policy, now, user_id, user_run)
        ids.append(user_run)
    return ids


def _dream_for_user(
    conn: Conn,
    llm: Llm,
    embedder: Embedder,
    policy: DreamPolicy,
    now: datetime,
    user_id: UUID,
    run_id: UUID,
    repo: str | None = None,
) -> None:
    """`repo` set: an event-triggered run consolidates and re-profiles only that repo."""
    counts = DreamCounts()
    try:
        with conn.transaction():
            for session in sessions_needing_dream(conn, user_id, repo):
                consolidate_session(conn, session, llm, embedder, policy, counts, now)
            counts.memories_decayed = decay_unused(
                conn,
                user_id,
                now,
                policy.decay_after_days,
                policy.decay_factor,
                policy.min_confidence,
            )
            for profile_repo in [repo] if repo is not None else profile_repos(conn, user_id):
                counts.profile_entries_changed += rebuild_profile(
                    conn, user_id, profile_repo, llm, now
                )
    except Exception as exc:
        finish_run(conn, run_id, DreamCounts(), f"{type(exc).__name__}: {exc}", now)
        raise
    finish_run(conn, run_id, counts, None, now)
