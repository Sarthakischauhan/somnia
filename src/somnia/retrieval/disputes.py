"""Open flagged conflicts as seen by retrieval (RLS-scoped).

Until a human resolves a flagged pair, retrieval serves only the newer memory (by
created_at, the candidate on a tie) and marks it disputed; the older one is withheld.
Resolved pairs fall out of this set and are served normally again.
"""

from uuid import UUID

from psycopg.rows import class_row
from pydantic import BaseModel

from somnia.db.connection import Conn


class OpenDisputes(BaseModel):
    withheld: frozenset[UUID]
    disputed: frozenset[UUID]


class _PairRow(BaseModel):
    newer: UUID
    older: UUID


def load_open_disputes(conn: Conn) -> OpenDisputes:
    with conn.cursor(row_factory=class_row(_PairRow)) as cur:
        cur.execute(
            "select case when e.created_at > n.created_at then e.id else n.id end as newer,"
            " case when e.created_at > n.created_at then n.id else e.id end as older"
            " from public.memory_conflicts c"
            " join public.memories e on e.id = c.existing_memory_id"
            " join public.memories n on n.id = c.candidate_memory_id"
            " where c.status = 'open' and c.outcome = 'flagged'"
        )
        pairs = cur.fetchall()
    withheld = frozenset(p.older for p in pairs)
    return OpenDisputes(
        withheld=withheld,
        disputed=frozenset(p.newer for p in pairs) - withheld,
    )
