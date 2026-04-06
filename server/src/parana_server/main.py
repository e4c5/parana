"""FastAPI application bootstrap for the Parana server.

Environment variables (loaded from ``.env`` if present):
    DATABASE_URL   — psycopg connection string / URI (required)
    PORT           — TCP port to listen on (default: 8000)
    LLM_API_KEY    — OpenAI (or compatible) API key for the chat endpoint
    LLM_MODEL      — model name (default: gpt-4o-mini)
    FRONTEND_ORIGIN — allowed CORS origin (default: http://localhost:5173)
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .db import create_pool, get_conn as _get_conn_base
from .routers import coverage, chat

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(dsn: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        dsn: psycopg connection string.  Falls back to ``DATABASE_URL`` env var.

    Returns:
        A fully configured :class:`fastapi.FastAPI` instance.
    """
    resolved_dsn = dsn or os.environ.get("DATABASE_URL", "")
    frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:5173")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.pool = await create_pool(resolved_dsn)
        logger.info("Database connection pool opened")
        yield
        await app.state.pool.close()
        logger.info("Database connection pool closed")

    app = FastAPI(
        title="Parana Coverage API",
        description="JaCoCo coverage tracking REST API with natural-language chat interface.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # --- CORS -----------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Dependency: per-request DB connection --------------------------------

    async def get_conn(request: Request):
        async with request.app.state.pool.connection() as conn:
            yield conn

    # --- Routers --------------------------------------------------------------
    app.include_router(coverage.router, tags=["coverage"])
    app.include_router(chat.router, tags=["chat"])

    # Override the ``get_conn`` dependency across all routes so that the
    # pool attached to *this* app instance is used.
    app.dependency_overrides[_get_conn_base] = get_conn

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run() -> None:
    """Start the uvicorn server (used by the ``parana-server`` console script)."""
    app = create_app()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


# Allow ``python -m parana_server.main`` as well.
if __name__ == "__main__":
    run()
