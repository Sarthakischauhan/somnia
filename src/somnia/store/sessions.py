"""Session rows."""

from uuid import UUID

from psycopg.rows import class_row

from somnia.auth.principal import Principal
from somnia.db.connection import Conn
from somnia.records import SessionRecord

_COLUMNS = "id, device_id, repo, branch, git_ref, status, started_at, last_event_at, ended_at"


def create_session(
    conn: Conn, principal: Principal, repo: str, branch: str, git_ref: str | None
) -> SessionRecord:
    with conn.cursor(row_factory=class_row(SessionRecord)) as cur:
        cur.execute(
            "insert into public.sessions (user_id, device_id, repo, branch, git_ref)"
            " values (%s, %s, %s, %s, %s) returning " + _COLUMNS,
            (principal.user_id, principal.device_id, repo, branch, git_ref),
        )
        row = cur.fetchone()
    if row is None:
        raise RuntimeError("session insert returned no row")
    return row


def get_session(conn: Conn, session_id: UUID) -> SessionRecord | None:
    with conn.cursor(row_factory=class_row(SessionRecord)) as cur:
        cur.execute("select " + _COLUMNS + " from public.sessions where id = %s", (session_id,))
        return cur.fetchone()


def close_session(conn: Conn, session_id: UUID) -> SessionRecord | None:
    with conn.cursor(row_factory=class_row(SessionRecord)) as cur:
        cur.execute(
            "update public.sessions set status = 'closed', ended_at = coalesce(ended_at, now())"
            " where id = %s returning " + _COLUMNS,
            (session_id,),
        )
        return cur.fetchone()


def touch_session(conn: Conn, session_id: UUID, git_ref: str | None) -> None:
    conn.execute(
        "update public.sessions set last_event_at = now(), git_ref = coalesce(%s, git_ref)"
        " where id = %s",
        (git_ref, session_id),
    )
