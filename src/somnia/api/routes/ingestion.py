"""Durable agent event ingestion."""

from collections.abc import Callable, Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from somnia.api.auth import Scoped
from somnia.api.routes.sessions import require_session
from somnia.api.schemas import EventBatch
from somnia.ingestion.event_models import GitRefEvent
from somnia.ingestion.events import InsertOutcome, insert_events
from somnia.sessions.sessions import touch_session


def build_ingestion_router(scoped: Callable[..., Iterator[Scoped]]) -> APIRouter:
    router = APIRouter(prefix="/v1/sessions", tags=["sessions"])
    Db = Annotated[Scoped, Depends(scoped, scope="function")]  # noqa: N806 - type alias

    @router.post("/{session_id}/events", status_code=status.HTTP_202_ACCEPTED)
    def post_events(session_id: UUID, body: EventBatch, db: Db) -> InsertOutcome:
        require_session(db, session_id)
        outcome = insert_events(db.conn, db.principal.user_id, session_id, body.events)
        refs = [e.payload.ref for e in body.events if isinstance(e, GitRefEvent)]
        if outcome.accepted:
            touch_session(db.conn, session_id, refs[-1] if refs else None)
        return outcome

    return router
