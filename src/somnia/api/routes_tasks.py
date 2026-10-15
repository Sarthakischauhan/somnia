"""Agent task queue endpoints."""

from collections.abc import Callable, Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from somnia.api.dependencies import Scoped
from somnia.api.schemas import TaskCompletion, TaskStatus
from somnia.records import CheckpointRecord, TaskRecord
from somnia.store.checkpoints import latest_checkpoint_for_session, latest_open_checkpoint
from somnia.store.tasks import TaskDraft, claim_task, complete_task, enqueue_task, get_task


def build_tasks_router(scoped: Callable[..., Iterator[Scoped]]) -> APIRouter:
    router = APIRouter(prefix="/v1/tasks", tags=["tasks"])
    Db = Annotated[Scoped, Depends(scoped)]  # noqa: N806 - type alias

    @router.post("", status_code=status.HTTP_201_CREATED)
    def post_task(body: TaskDraft, db: Db) -> TaskRecord:
        return enqueue_task(db.conn, db.principal, body)

    @router.post("/claim", response_model=None)
    def post_claim(
        db: Db, lease_seconds: Annotated[int, Query(ge=10, le=86400)] = 900
    ) -> TaskRecord | Response:
        task = claim_task(db.conn, db.principal.device_id, lease_seconds)
        return task if task is not None else Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/{task_id}/complete")
    def post_complete(task_id: UUID, body: TaskCompletion, db: Db) -> TaskRecord:
        task = complete_task(db.conn, task_id, body.status, body.result)
        if task is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
        return task

    @router.get("/{task_id}/status")
    def get_status(task_id: UUID, db: Db) -> TaskStatus:
        task = get_task(db.conn, task_id)
        if task is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "task not found")
        checkpoint: CheckpointRecord | None = None
        if task.session_id is not None:
            checkpoint = latest_checkpoint_for_session(db.conn, task.session_id)
        elif task.repo is not None and task.branch is not None:
            checkpoint = latest_open_checkpoint(db.conn, task.repo, task.branch)
        return TaskStatus(task=task, latest_checkpoint=checkpoint)

    return router
