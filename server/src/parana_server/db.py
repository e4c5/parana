"""Database connection pool management for the Parana server.

The async connection pool is created once on app startup and stored on the
FastAPI ``app.state`` object.  The ``get_conn`` dependency yields a connection
from the pool for each request and returns it afterward.
"""

from __future__ import annotations

from typing import AsyncGenerator

import psycopg
from psycopg_pool import AsyncConnectionPool


async def create_pool(dsn: str, min_size: int = 2, max_size: int = 10) -> AsyncConnectionPool:
    """Create and open an async connection pool."""
    pool = AsyncConnectionPool(dsn, min_size=min_size, max_size=max_size, open=False)
    await pool.open()
    return pool


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
