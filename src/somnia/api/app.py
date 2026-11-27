"""FastAPI application factory. Uses only the RLS-scoped API database role."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

import httpx
from fastapi import FastAPI, HTTPException
from psycopg import Error
from psycopg_pool import ConnectionPool

from somnia.api.dependencies import scoped_dependency, user_database_dependency
from somnia.api.routes_context import build_context_router, utc_now
from somnia.api.routes_management import build_management_router
from somnia.api.routes_sessions import build_sessions_router
from somnia.api.routes_tasks import build_tasks_router
from somnia.config import ApiSettings
from somnia.db.connection import Conn
from somnia.memory.models import Embedder


def create_app(
    settings: ApiSettings,
    embedder: Embedder,
    clock: Callable[[], datetime] = utc_now,
    *,
    auth_transport: httpx.BaseTransport | None = None,
) -> FastAPI:
    pool: ConnectionPool[Conn] = ConnectionPool(
        settings.api_database_url.get_secret_value(),
        max_size=settings.pool_max_size,
        kwargs={"autocommit": True},
        open=False,
    )

    auth_client = None
    if settings.supabase_url and settings.supabase_publishable_key:
        auth_client = httpx.Client(
            base_url=f"{str(settings.supabase_url).rstrip('/')}/auth/v1/",
            headers={"apikey": settings.supabase_publishable_key.get_secret_value()},
            transport=auth_transport,
            timeout=5.0,
        )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            pool.open(wait=True)
            yield
        finally:
            pool.close()
            if auth_client is not None:
                auth_client.close()

    app = FastAPI(title="somnia", version="0.1.0", lifespan=lifespan)
    scoped = scoped_dependency(pool)
    app.include_router(build_sessions_router(scoped))
    app.include_router(build_tasks_router(scoped))
    user_db = user_database_dependency(pool, scoped, auth_client)
    management = build_management_router(user_db, settings)
    app.include_router(management, prefix="/v1")
    app.include_router(management, prefix="/v1/admin", include_in_schema=False)
    app.include_router(build_context_router(user_db, embedder, settings, clock))

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict[str, str]:
        try:
            with pool.connection(timeout=1) as conn:
                conn.execute("select 1")
        except Error as exc:
            raise HTTPException(503, "database unavailable") from exc
        return {"status": "ok"}

    return app
