"""Event-triggered repo dreams, swept by the worker (pg_cron stays as the backstop).

Session end is enqueued by a database trigger (see the migration). The worker adds:
- idle: an open session with undreamt events and no event for `idle_minutes`;
- chunk_threshold: a repo whose undreamt chunks reach `chunk_threshold`.
All go through somnia_enqueue_repo_dream, which keeps one pending run per (user, repo)
and counts later triggers in `coalesced` instead of queueing duplicates.
"""

from datetime import datetime
from uuid import UUID

from somnia.db.connection import Conn

_UNDREAMT = (
    "exists (select 1 from public.events e where e.session_id = s.id"
    " and e.seq > s.dreamed_through_seq)"
)
# A sweep runs every worker tick: skip repos that already have a run queued or running.
_NOT_IN_FLIGHT = (
    "not exists (select 1 from public.dream_runs r where r.user_id = s.user_id"
    " and r.repo = s.repo and r.status in ('requested', 'running'))"
)


def _enqueue(conn: Conn, rows: list[tuple[object, ...]], trigger: str) -> list[UUID]:
    ids = []
    for user_id, repo in rows:
        row = conn.execute(
            "select public.somnia_enqueue_repo_dream(%s, %s, %s)", (user_id, repo, trigger)
        ).fetchone()
        if row is not None:
            ids.append(UUID(str(row[0])))
    return ids


def enqueue_idle_sessions(conn: Conn, now: datetime, idle_minutes: float) -> list[UUID]:
    rows = conn.execute(
        "select distinct s.user_id, s.repo from public.sessions s"
        " where s.status = 'open'"
        " and coalesce(s.last_event_at, s.started_at) < %s - make_interval(secs => %s)"
        " and " + _UNDREAMT + " and " + _NOT_IN_FLIGHT,
        (now, idle_minutes * 60),
    ).fetchall()
    return _enqueue(conn, [tuple(r) for r in rows], "idle")


def enqueue_chunk_thresholds(conn: Conn, threshold: int) -> list[UUID]:
    rows = conn.execute(
        "select s.user_id, s.repo from public.chunks c"
        " join public.events e on e.id = c.event_id"
        " join public.sessions s on s.id = c.session_id"
        " where e.seq > s.dreamed_through_seq and "
        + _NOT_IN_FLIGHT
        + " group by s.user_id, s.repo having count(*) >= %s",
        (threshold,),
    ).fetchall()
    return _enqueue(conn, [tuple(r) for r in rows], "chunk_threshold")
