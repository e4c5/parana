"""Pydantic models for the Parana REST API and chat service."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Coverage / snapshot models
# ---------------------------------------------------------------------------


class CodebaseOut(BaseModel):
    """A single row from the `codebase` table."""

    id: int
    git_origin: str


class SnapshotOut(BaseModel):
    """A single row from the `coverage_snapshot` table."""

    id: int
    codebase_id: int
    git_branch: str
    git_commit_hash: str
    uncommitted_files_hash: str
    captured_at: datetime


class CoverageRowOut(BaseModel):
    """One comparison result row — one entity (file / class / method) per snapshot pair."""

    entity_name: str
    covered_lines_before: int
    covered_lines_after: int
    delta_covered_lines: int
    covered_branches_before: int
    covered_branches_after: int
    delta_covered_branches: int
    coverage_pct_before: float
    coverage_pct_after: float
    delta_coverage_pct: float


# ---------------------------------------------------------------------------
# Chat models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    """Request body for `POST /chat`."""

    session_id: str = Field(..., description="Client-generated session identifier.")
    message: str = Field(..., description="Plain-English question from the user.")


class ResultPayload(BaseModel):
    """Structured result to be rendered in the frontend."""

    result_type: Literal["table", "text"]
    columns: list[str] | None = None
    rows: list[dict[str, Any]] | None = None


class SSEChunk(BaseModel):
    """A single Server-Sent Event chunk from `POST /chat`."""

    type: Literal["text_delta", "result", "done", "error"]
    data: str | ResultPayload | None = None


# ---------------------------------------------------------------------------
# Auth models
# ---------------------------------------------------------------------------


class User(BaseModel):
    """An application user."""

    id: int
    username: str
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    """Request body for user registration."""

    username: str
    password: str


class Token(BaseModel):
    """JWT access token response."""

    access_token: str
    token_type: str


class TokenData(BaseModel):
    """Data decoded from a JWT."""

    username: str | None = None
