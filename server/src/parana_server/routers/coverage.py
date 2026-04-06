"""Coverage REST endpoints.

Routes:
  GET /codebases
  GET /codebases/{id}/snapshots
  GET /snapshots/{id}
  GET /compare
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_conn
from ..models import CodebaseOut, CoverageRowOut, SnapshotOut
from .. import queries

router = APIRouter()


# ---------------------------------------------------------------------------
# GET /codebases
# ---------------------------------------------------------------------------


@router.get("/codebases", response_model=list[CodebaseOut])
async def list_codebases(conn=Depends(get_conn)):
    """Return all tracked codebases."""
    return await queries.list_codebases(conn)


# ---------------------------------------------------------------------------
# GET /codebases/{id}/snapshots
# ---------------------------------------------------------------------------


@router.get("/codebases/{codebase_id}/snapshots", response_model=list[SnapshotOut])
async def list_snapshots(
    codebase_id: int,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    conn=Depends(get_conn),
):
    """Return snapshots for a codebase, newest first."""
    return await queries.list_snapshots(conn, codebase_id, limit=limit, offset=offset)


# ---------------------------------------------------------------------------
# GET /snapshots/{id}
# ---------------------------------------------------------------------------


@router.get("/snapshots/{snapshot_id}", response_model=SnapshotOut)
async def get_snapshot(snapshot_id: int, conn=Depends(get_conn)):
    """Return a single snapshot; 404 if not found."""
    snap = await queries.get_snapshot(conn, snapshot_id)
    if snap is None:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return snap


# ---------------------------------------------------------------------------
# GET /compare
# ---------------------------------------------------------------------------


@router.get("/compare", response_model=list[CoverageRowOut])
async def compare(
    before: Annotated[int, Query(description="ID of the earlier snapshot")],
    after: Annotated[int, Query(description="ID of the later snapshot")],
    level: Annotated[
        Literal["file", "class", "method"],
        Query(description="Granularity level"),
    ] = "file",
    filter: Annotated[
        Optional[str],
        Query(description="Optional substring filter on entity name"),
    ] = None,
    conn=Depends(get_conn),
):
    """Compare coverage between two snapshots at file, class, or method level."""
    if level == "file":
        return await queries.compare_snapshots_file(conn, before, after, filter)
    if level == "class":
        return await queries.compare_snapshots_class(conn, before, after, filter)
    return await queries.compare_snapshots_method(conn, before, after, filter)
