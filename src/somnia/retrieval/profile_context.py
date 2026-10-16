"""The caller's project profile for a repo (RLS-scoped), highest-priority entries first."""

from datetime import datetime
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.connection import Conn
from somnia.providers.protocols import ProfileSection

# Order sections appear in (and are kept in) when packing under a token budget.
SECTION_PRIORITY: tuple[ProfileSection, ...] = (
    "stack",
    "conventions",
    "architecture",
    "decisions",
    "pitfalls",
    "open_work",
)


class ProfileEntryOut(BaseModel):
    id: UUID
    section: ProfileSection
    content: str
    confidence: float
    source_memory_id: UUID | None
    source_checkpoint_id: UUID | None
    source_session_ids: list[UUID]
    updated_at: datetime
    disputed: bool = False


class ProjectProfileOut(BaseModel):
    repo: str
    version: int
    updated_at: datetime
    entries: list[ProfileEntryOut]


class _ProfileHead(BaseModel):
    id: UUID
    repo: str
    version: int
    updated_at: datetime


def entry_text(entry: ProfileEntryOut) -> str:
    return f"[{entry.section}] {entry.content}"


def load_profile(conn: Conn, repo: str) -> ProjectProfileOut | None:
    with conn.cursor(row_factory=class_row(_ProfileHead)) as cur:
        cur.execute(
            "select id, repo, version, updated_at from public.project_profiles where repo = %s",
            (repo,),
        )
        head = cur.fetchone()
    if head is None:
        return None
    with conn.cursor(row_factory=class_row(ProfileEntryOut)) as cur:
        cur.execute(
            "select id, section, content, confidence, source_memory_id, source_checkpoint_id,"
            " source_session_ids, updated_at from public.project_profile_entries"
            " where profile_id = %s and retired_at is null"
            " order by array_position(%s::text[], section), confidence desc, updated_at desc",
            (head.id, list(SECTION_PRIORITY)),
        )
        entries = cur.fetchall()
    return ProjectProfileOut(
        repo=head.repo, version=head.version, updated_at=head.updated_at, entries=entries
    )
