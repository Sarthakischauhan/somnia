"""Report when the current event backlog and queued dreams finish.

The monitor watches the rows visible when it starts. Dreams requested later are
not allowed to keep it waiting forever.
"""

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from somnia.config import ApiSettings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(prog="monitor-dream-queue")
    parser.add_argument("--poll-seconds", type=float, default=30)
    parser.add_argument("--timeout-minutes", type=float, default=180)
    args = parser.parse_args()
    settings = ApiSettings()
    deadline = time.monotonic() + args.timeout_minutes * 60
    with psycopg.connect(
        settings.api_database_url.get_secret_value(),
        autocommit=True,
        connect_timeout=8,
        row_factory=dict_row,
    ) as conn:
        baseline = conn.execute(
            "select coalesce(max(e.id), 0) as event_id,"
            " (select array_agg(r.id) from public.dream_runs r where r.status in"
            " ('requested', 'running')) as runs from public.events e"
        ).fetchone()
        event_id = int(baseline["event_id"])
        run_ids = baseline["runs"] or []
        print(
            f"watching events<={event_id} and {len(run_ids)} queued dreams",
            flush=True,
        )
        while True:
            status = _status(conn, event_id, run_ids)
            print(_line(status), flush=True)
            if status["pending"] == 0 and status["active"] == 0:
                print("QUEUE_COMPLETE", flush=True)
                _report(conn)
                return
            if time.monotonic() >= deadline:
                raise SystemExit("timed out before the queue finished")
            time.sleep(args.poll_seconds)


def _status(conn: psycopg.Connection, event_id: int, run_ids: list[object]) -> dict[str, int]:
    row = conn.execute(
        "select count(*) filter (where processed_at is null) as pending,"
        " count(*) filter (where dreamed) as dreamed"
        " from public.events where id <= %s",
        (event_id,),
    ).fetchone()
    active = 0
    failed = 0
    if run_ids:
        runs = conn.execute(
            "select count(*) filter (where status in ('requested', 'running')) as active,"
            " count(*) filter (where status = 'failed') as failed"
            " from public.dream_runs where id = any(%s)",
            (run_ids,),
        ).fetchone()
        active = int(runs["active"])
        failed = int(runs["failed"])
    return {
        "pending": int(row["pending"]),
        "dreamed": int(row["dreamed"]),
        "active": active,
        "failed": failed,
    }


def _line(status: dict[str, int]) -> str:
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    return (
        f"{stamp} pending={status['pending']} dreamed={status['dreamed']}"
        f" active_dreams={status['active']} failed_dreams={status['failed']}"
    )


def _report(conn: psycopg.Connection) -> None:
    memories = conn.execute(
        "select count(*) as total from public.memories"
        " where superseded_by is null and archived_at is null"
    ).fetchone()
    usage = conn.execute(
        "select count(*) as requests, coalesce(sum(cost_usd), 0) as cost from public.model_usage"
    ).fetchone()
    print(f"active_memories={memories['total']}", flush=True)
    print(
        f"recorded_requests={usage['requests']} estimated_cost_usd={usage['cost']}",
        flush=True,
    )


if __name__ == "__main__":
    main()
