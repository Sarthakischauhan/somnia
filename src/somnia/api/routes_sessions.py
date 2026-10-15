"""Session + event ingestion endpoints."""

from collections.abc import Callable, Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from somnia.api.dependencies import Scoped
from somnia.api.schemas import EventBatch, SessionCreate, SessionStatus
from somnia.ingest.event_models import GitRefEvent
from somnia.records import CheckpointRecord, SessionRecord
from somnia.store.checkpoints import (
    CheckpointDraft,
    create_checkpoint,
    latest_checkpoint_for_session,
)
from somnia.store.events import InsertOutcome, count_unprocessed, insert_events
from somnia.store.sessions import close_session, create_session, get_session, touch_session


def _require_session(scoped: Scoped, session_id: UUID) -> SessionRecord:
    session = get_session(scoped.conn, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
    return session


def build_sessions_router(scoped: Callable[..., Iterator[Scoped]]) -> APIRouter:
    router = APIRouter(prefix="/v1/sessions", tags=["sessions"])
    Db = Annotated[Scoped, Depends(scoped)]  # noqa: N806 - type alias

    @router.post("", status_code=status.HTTP_201_CREATED)
    def post_session(body: SessionCreate, db: Db) -> SessionRecord:
        return create_session(db.conn, db.principal, body.repo, body.branch, body.git_ref)

    @router.post("/{session_id}/events", status_code=status.HTTP_202_ACCEPTED)
    def post_events(session_id: UUID, body: EventBatch, db: Db) -> InsertOutcome:
        _require_session(db, session_id)
        outcome = insert_events(db.conn, db.principal.user_id, session_id, body.events)
        refs = [e.payload.ref for e in body.events if isinstance(e, GitRefEvent)]
        touch_session(db.conn, session_id, refs[-1] if refs else None)
        return outcome

    @router.post("/{session_id}/checkpoints", status_code=status.HTTP_201_CREATED)
    def post_checkpoint(session_id: UUID, body: CheckpointDraft, db: Db) -> CheckpointRecord:
        session = _require_session(db, session_id)
        return create_checkpoint(
            db.conn,
            user_id=db.principal.user_id,
            session_id=session.id,
            repo=session.repo,
            branch=session.branch,
            draft=body,
            source="agent",
        )

    @router.post("/{session_id}/close")
    def post_close(session_id: UUID, db: Db) -> SessionRecord:
        closed = close_session(db.conn, session_id)
        if closed is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "session not found")
        return closed

    @router.get("/{session_id}/status")
    def get_status(session_id: UUID, db: Db) -> SessionStatus:
        session = _require_session(db, session_id)
        return SessionStatus(
            session=session,
            latest_checkpoint=latest_checkpoint_for_session(db.conn, session_id),
            unprocessed_events=count_unprocessed(db.conn, session_id),
        )

    return router
