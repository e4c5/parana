"""Database connection pool management for the Parana server.

The async connection pool is created once on app startup and stored on the
FastAPI ``app.state`` object.  The ``get_conn`` dependency yields a connection
from the pool for each request and returns it afterward.
"""

from __future__ import annotations

from typing import AsyncGenerator

import psycopg
from psycopg_pool import AsyncConnectionPool


# Kept in sync with ``parana_importer.db.MIGRATIONS``: both services apply the
# same idempotent statements so their upgrade order does not matter.
MIGRATIONS: tuple[str, ...] = (
    """
    ALTER TABLE coverage_snapshot
    ADD COLUMN IF NOT EXISTS format VARCHAR(32) NOT NULL DEFAULT 'jacoco'
    """,
    """
    DO $$
    DECLARE old_name TEXT;
    BEGIN
        SELECT c.conname INTO old_name
        FROM pg_constraint c
        WHERE c.conrelid = 'coverage_snapshot'::regclass
          AND c.contype = 'u'
          AND c.conname <> 'uq_snapshot_identity'
          AND NOT ((SELECT attnum FROM pg_attribute
                    WHERE attrelid = c.conrelid AND attname = 'format') = ANY (c.conkey));
        IF old_name IS NOT NULL THEN
            EXECUTE format('ALTER TABLE coverage_snapshot DROP CONSTRAINT %I', old_name);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint
                       WHERE conrelid = 'coverage_snapshot'::regclass
                         AND conname = 'uq_snapshot_identity') THEN
            ALTER TABLE coverage_snapshot ADD CONSTRAINT uq_snapshot_identity
                UNIQUE (codebase_id, git_commit_hash, uncommitted_files_hash, format);
        END IF;
    END $$
    """,
)


async def create_pool(dsn: str, min_size: int = 2, max_size: int = 10) -> AsyncConnectionPool:
    """Create and open an async connection pool."""
    pool = AsyncConnectionPool(dsn, min_size=min_size, max_size=max_size, open=False)
    await pool.open()
    return pool


async def apply_migrations(conn: psycopg.AsyncConnection) -> None:
    """Apply additive schema migrations; no-op if the schema has not been created yet."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT to_regclass('coverage_snapshot')")
        if (await cur.fetchone())[0] is None:
            return
        for stmt in MIGRATIONS:
            await cur.execute(stmt)
    await conn.commit()


async def get_conn(app_state) -> AsyncGenerator[psycopg.AsyncConnection, None]:
    """FastAPI dependency that yields a connection from the pool.

    Usage in a route::

        from fastapi import Depends, Request
        from .db import get_conn

        @router.get("/example")
        async def example(conn=Depends(get_conn)):
            ...

    The dependency is registered at the app level (see ``main.py``) using a
    closure so that ``app.state.pool`` is captured.
    """
    async with app_state.pool.connection() as conn:
        yield conn
