"""Memory browsing and curation for the admin UI (RLS-scoped, no deletes)."""

from datetime import datetime
from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel, Field

from somnia.db.connection import Conn
from somnia.providers.protocols import MemoryScope, MemoryType
from somnia.records import SessionRecord

_COLUMNS = (
    "id, type, scope, repo, branch, content, confidence, use_count, last_used_at,"
    " created_at, updated_at, archived_at, superseded_by, source_session_ids"
)


class MemoryRecord(BaseModel):
    id: UUID
    type: MemoryType
    scope: MemoryScope
    repo: str | None
    branch: str | None
    content: str
    confidence: float
    use_count: int
    last_used_at: datetime | None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    superseded_by: UUID | None
    source_session_ids: list[UUID]


class MemoryFilter(BaseModel):
    repo: str | None = None
    branch: str | None = None
    type: MemoryType | None = None
    scope: MemoryScope | None = None
    q: str | None = None
    include_superseded: bool = False
    include_archived: bool = False
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class MemoryPage(BaseModel):
    items: list[MemoryRecord]
    total: int


class MemoryDetail(BaseModel):
    memory: MemoryRecord
    sources: list[SessionRecord]
    supersedes: list[MemoryRecord]
    superseded_by_chain: list[MemoryRecord]


class MemoryPatch(BaseModel):
    confidence: float | None = Field(default=None, ge=0, le=1)
    archived: bool | None = None


_FILTER_SQL = (
    " from public.memories where (%(repo)s::text is null or repo = %(repo)s)"
    " and (%(branch)s::text is null or branch = %(branch)s)"
    " and (%(type)s::text is null or type = %(type)s)"
    " and (%(scope)s::text is null or scope = %(scope)s)"
    " and (%(q)s::text is null or content ilike '%%' || %(q)s || '%%')"
    " and (%(sup)s or superseded_by is null)"
    " and (%(arch)s or archived_at is null)"
)


def list_memories(conn: Conn, f: MemoryFilter) -> MemoryPage:
    params = {
        "repo": f.repo,
        "branch": f.branch,
        "type": f.type,
        "scope": f.scope,
        "q": f.q or None,
        "sup": f.include_superseded,
        "arch": f.include_archived,
        "limit": f.limit,
        "offset": f.offset,
    }
    with conn.cursor(row_factory=class_row(MemoryRecord)) as cur:
        cur.execute(
            "select "
            + _COLUMNS
            + _FILTER_SQL
            + " order by updated_at desc, id limit %(limit)s offset %(offset)s",
            params,
        )
        items = cur.fetchall()
    row = conn.execute("select count(*)" + _FILTER_SQL, params).fetchone()
    return MemoryPage(items=items, total=int(row[0]) if row else 0)


def get_memory(conn: Conn, memory_id: UUID) -> MemoryRecord | None:
    with conn.cursor(row_factory=class_row(MemoryRecord)) as cur:
        cur.execute("select " + _COLUMNS + " from public.memories where id = %s", (memory_id,))
        return cur.fetchone()


def memory_detail(conn: Conn, memory: MemoryRecord) -> MemoryDetail:
    with conn.cursor(row_factory=class_row(MemoryRecord)) as cur:
        cur.execute(
            "with recursive newer as ("
            "  select m.*, 1 as depth from public.memories m where m.id = %(next)s"
            "  union all select m.*, n.depth + 1 from public.memories m"
            "  join newer n on m.id = n.superseded_by where n.depth < 50)"
            " select " + _COLUMNS + " from newer order by depth",
            {"next": memory.superseded_by},
        )
        newer = cur.fetchall()
        cur.execute(
            "with recursive older as ("
            "  select m.*, 1 as depth from public.memories m where m.superseded_by = %(id)s"
            "  union all select m.*, o.depth + 1 from public.memories m"
            "  join older o on m.superseded_by = o.id where o.depth < 50)"
            " select " + _COLUMNS + " from older order by depth",
            {"id": memory.id},
        )
        older = cur.fetchall()
    with conn.cursor(row_factory=class_row(SessionRecord)) as cur:
        cur.execute(
            "select id, device_id, repo, branch, git_ref, status, started_at, last_event_at,"
            " ended_at from public.sessions where id = any(%s) order by started_at",
            (memory.source_session_ids,),
        )
        sources = cur.fetchall()
    return MemoryDetail(memory=memory, sources=sources, supersedes=older, superseded_by_chain=newer)


def patch_memory(conn: Conn, memory_id: UUID, patch: MemoryPatch) -> MemoryRecord | None:
    with conn.cursor(row_factory=class_row(MemoryRecord)) as cur:
        cur.execute(
            "update public.memories set"
            " confidence = coalesce(%(confidence)s, confidence),"
            " archived_at = case when %(archived)s::boolean is null then archived_at"
            "   when %(archived)s then coalesce(archived_at, now()) else null end,"
            " updated_at = now() where id = %(id)s returning " + _COLUMNS,
            {"confidence": patch.confidence, "archived": patch.archived, "id": memory_id},
        )
        return cur.fetchone()


class RepoBranch(BaseModel):
    repo: str
    branch: str


def list_repo_branches(conn: Conn) -> list[RepoBranch]:
    with conn.cursor(row_factory=class_row(RepoBranch)) as cur:
        cur.execute(
            "select distinct repo, branch from public.sessions"
            " union select distinct repo, coalesce(branch, '') from public.memories"
            "   where repo is not null"
            " order by repo, branch"
        )
        return [r for r in cur.fetchall() if r.branch]
