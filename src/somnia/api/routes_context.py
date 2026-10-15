"""Session-start context endpoint."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from somnia.api.dependencies import Scoped
from somnia.config import ApiSettings
from somnia.providers.protocols import Embedder
from somnia.retrieval.context import ContextRequest, SessionContext, build_session_context


def build_context_router(
    scoped: Callable[..., Iterator[Scoped]],
    embedder: Embedder,
    settings: ApiSettings,
    clock: Callable[[], datetime],
) -> APIRouter:
    router = APIRouter(prefix="/v1", tags=["retrieval"])
    Db = Annotated[Scoped, Depends(scoped)]  # noqa: N806 - type alias

    @router.get("/context")
    def get_context(
        db: Db,
        repo: Annotated[str, Query(min_length=1)],
        branch: Annotated[str, Query(min_length=1)],
        token_budget: Annotated[int | None, Query(ge=1, le=200_000)] = None,
        k: Annotated[int, Query(ge=1, le=100)] = 10,
        query: Annotated[str | None, Query()] = None,
    ) -> SessionContext:
        request = ContextRequest(
            repo=repo,
            branch=branch,
            k=k,
            query=query,
            token_budget=token_budget or settings.default_token_budget,
        )
        return build_session_context(
            db.conn,
            embedder,
            request,
            clock(),
            settings.recency_half_life_days,
            candidate_pool=k * settings.candidate_pool_factor,
        )

    return router


def utc_now() -> datetime:
    return datetime.now(UTC)
