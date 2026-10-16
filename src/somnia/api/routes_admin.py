"""Admin endpoints backing the web UI. Same device-token auth and RLS scope as the
agent API: an admin sees and curates only their own user's data."""

from collections.abc import Callable, Iterator
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from somnia.api.dependencies import Scoped
from somnia.config import ApiSettings
from somnia.providers.protocols import MemoryScope, MemoryType
from somnia.records import CheckpointRecord
from somnia.retrieval.profile_context import ProjectProfileOut, load_profile
from somnia.store.admin_conflicts import (
    ConflictAlreadyResolvedError,
    ConflictOutcome,
    ConflictResolution,
    ConflictStatus,
    ConflictView,
    list_conflicts,
    resolve_conflict,
)
from somnia.store.admin_dreams import (
    DreamRunRecord,
    DreamSchedule,
    dream_schedule,
    list_dream_runs,
    request_dream,
)
from somnia.store.admin_memories import (
    MemoryDetail,
    MemoryFilter,
    MemoryPage,
    MemoryPatch,
    MemoryRecord,
    RepoBranch,
    get_memory,
    list_memories,
    list_repo_branches,
    memory_detail,
    patch_memory,
)
from somnia.store.admin_overview import TaskQueue, latest_checkpoints, task_queue

TaskStatusName = Literal["queued", "running", "done", "failed"]


def build_admin_router(scoped: Callable[..., Iterator[Scoped]], settings: ApiSettings) -> APIRouter:
    router = APIRouter(prefix="/v1/admin", tags=["admin"])
    Db = Annotated[Scoped, Depends(scoped)]  # noqa: N806 - type alias

    @router.get("/memories")
    def get_memories(
        db: Db,
        repo: str | None = None,
        branch: str | None = None,
        type: MemoryType | None = None,
        scope: MemoryScope | None = None,
        q: str | None = None,
        include_superseded: bool = False,
        include_archived: bool = False,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> MemoryPage:
        return list_memories(
            db.conn,
            MemoryFilter(
                repo=repo,
                branch=branch,
                type=type,
                scope=scope,
                q=q,
                include_superseded=include_superseded,
                include_archived=include_archived,
                limit=limit,
                offset=offset,
            ),
        )

    @router.get("/memories/{memory_id}")
    def get_memory_detail(memory_id: UUID, db: Db) -> MemoryDetail:
        memory = get_memory(db.conn, memory_id)
        if memory is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found")
        return memory_detail(db.conn, memory)

    @router.patch("/memories/{memory_id}")
    def patch_memory_route(memory_id: UUID, body: MemoryPatch, db: Db) -> MemoryRecord:
        updated = patch_memory(db.conn, memory_id, body)
        if updated is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "memory not found")
        return updated

    @router.get("/repos")
    def get_repos(db: Db) -> list[RepoBranch]:
        return list_repo_branches(db.conn)

    @router.get("/dream-runs")
    def get_dream_runs(
        db: Db, limit: Annotated[int, Query(ge=1, le=200)] = 50
    ) -> list[DreamRunRecord]:
        return list_dream_runs(db.conn, limit)

    @router.post("/dream-runs", status_code=status.HTTP_202_ACCEPTED)
    def post_dream_run(db: Db) -> DreamRunRecord:
        return request_dream(db.conn)

    @router.get("/dream-schedule")
    def get_dream_schedule(db: Db) -> DreamSchedule:
        return dream_schedule(db.conn, settings.dream_interval_s)

    @router.get("/checkpoints/latest")
    def get_latest_checkpoints(db: Db) -> list[CheckpointRecord]:
        return latest_checkpoints(db.conn)

    @router.get("/tasks")
    def get_tasks(
        db: Db,
        status_in: Annotated[list[TaskStatusName] | None, Query(alias="status")] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> TaskQueue:
        statuses = status_in or ["queued", "running", "done", "failed"]
        return task_queue(db.conn, statuses, limit)

    @router.get("/project-profile")
    def get_project_profile(db: Db, repo: Annotated[str, Query(min_length=1)]) -> ProjectProfileOut:
        profile = load_profile(db.conn, repo)
        if profile is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "no profile for this repo yet")
        return profile

    @router.get("/conflicts")
    def get_conflicts(
        db: Db,
        status_in: Annotated[list[ConflictStatus] | None, Query(alias="status")] = None,
        outcome: Annotated[list[ConflictOutcome] | None, Query()] = None,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
    ) -> list[ConflictView]:
        return list_conflicts(
            db.conn,
            status_in or ["open"],
            outcome or ["superseded", "coexist", "flagged"],
            limit,
        )

    @router.post("/conflicts/{conflict_id}/resolve")
    def post_resolve_conflict(conflict_id: UUID, body: ConflictResolution, db: Db) -> ConflictView:
        try:
            resolved = resolve_conflict(db.conn, conflict_id, body.resolution)
        except ConflictAlreadyResolvedError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, "conflict already resolved") from exc
        if resolved is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "conflict not found")
        return resolved

    return router
