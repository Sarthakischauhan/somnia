"""Latest checkpoint per repo/branch and task queue status for the admin UI."""

from collections.abc import Sequence

from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.connection import Conn
from somnia.records import CheckpointRecord, TaskRecord
from somnia.store.checkpoints import CHECKPOINT_COLUMNS
from somnia.store.tasks import TASK_COLUMNS


class TaskCounts(BaseModel):
    queued: int = 0
    running: int = 0
    done: int = 0
    failed: int = 0


class TaskQueue(BaseModel):
    counts: TaskCounts
    items: list[TaskRecord]


def latest_checkpoints(conn: Conn) -> list[CheckpointRecord]:
    with conn.cursor(row_factory=class_row(CheckpointRecord)) as cur:
        cur.execute(
            "select distinct on (repo, branch) "
            + CHECKPOINT_COLUMNS
            + " from public.checkpoints order by repo, branch, created_at desc"
        )
        return cur.fetchall()


def task_queue(conn: Conn, statuses: Sequence[str], limit: int) -> TaskQueue:
    rows = conn.execute("select status, count(*) from public.tasks group by status").fetchall()
    by_status = {str(r[0]): int(r[1]) for r in rows}
    counts = TaskCounts(
        queued=by_status.get("queued", 0),
        running=by_status.get("running", 0),
        done=by_status.get("done", 0),
        failed=by_status.get("failed", 0),
    )
    with conn.cursor(row_factory=class_row(TaskRecord)) as cur:
        cur.execute(
            "select " + TASK_COLUMNS + " from public.tasks where status = any(%s)"
            " order by updated_at desc limit %s",
            (list(statuses), limit),
        )
        return TaskQueue(counts=counts, items=cur.fetchall())
