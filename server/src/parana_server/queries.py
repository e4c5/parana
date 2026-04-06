"""Async database query layer for the Parana REST API.

All public functions accept an open :class:`psycopg.AsyncConnection`.  The
FastAPI app injects connections from the shared async connection pool.
"""

from __future__ import annotations

from typing import Optional

import psycopg

from .models import CodebaseOut, CoverageRowOut, SnapshotOut


# ---------------------------------------------------------------------------
# Codebases
# ---------------------------------------------------------------------------


async def list_codebases(conn: psycopg.AsyncConnection) -> list[CodebaseOut]:
    """Return all rows from the `codebase` table ordered by id."""
    async with conn.cursor() as cur:
        await cur.execute("SELECT id, git_origin FROM codebase ORDER BY id")
        rows = await cur.fetchall()
    return [CodebaseOut(id=r[0], git_origin=r[1]) for r in rows]


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


async def list_snapshots(
    conn: psycopg.AsyncConnection,
    codebase_id: int,
    limit: int = 20,
    offset: int = 0,
) -> list[SnapshotOut]:
    """Return snapshots for *codebase_id*, newest first, with pagination."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT id, codebase_id, git_branch, git_commit_hash,
                   uncommitted_files_hash, captured_at
            FROM   coverage_snapshot
            WHERE  codebase_id = %s
            ORDER  BY captured_at DESC
            LIMIT  %s OFFSET %s
            """,
            (codebase_id, limit, offset),
        )
        rows = await cur.fetchall()
    return [
        SnapshotOut(
            id=r[0],
            codebase_id=r[1],
            git_branch=r[2],
            git_commit_hash=r[3],
            uncommitted_files_hash=r[4],
            captured_at=r[5],
        )
        for r in rows
    ]


async def get_snapshot(
    conn: psycopg.AsyncConnection,
    snapshot_id: int,
) -> Optional[SnapshotOut]:
    """Return a single snapshot by *snapshot_id*, or ``None`` if not found."""
    async with conn.cursor() as cur:
        await cur.execute(
            """
            SELECT id, codebase_id, git_branch, git_commit_hash,
                   uncommitted_files_hash, captured_at
            FROM   coverage_snapshot
            WHERE  id = %s
            """,
            (snapshot_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return SnapshotOut(
        id=row[0],
        codebase_id=row[1],
        git_branch=row[2],
        git_commit_hash=row[3],
        uncommitted_files_hash=row[4],
        captured_at=row[5],
    )


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------


def _coverage_pct(covered: int, missed: int) -> float:
    total = covered + missed
    return round(covered / total, 6) if total > 0 else 0.0


def _build_coverage_row(
    entity_name: str,
    cl_before: int,
    cl_after: int,
    cb_before: int,
    cb_after: int,
    ml_before: int,
    ml_after: int,
) -> CoverageRowOut:
    pct_before = _coverage_pct(cl_before, ml_before)
    pct_after = _coverage_pct(cl_after, ml_after)
    return CoverageRowOut(
        entity_name=entity_name,
        covered_lines_before=cl_before,
        covered_lines_after=cl_after,
        delta_covered_lines=cl_after - cl_before,
        covered_branches_before=cb_before,
        covered_branches_after=cb_after,
        delta_covered_branches=cb_after - cb_before,
        coverage_pct_before=pct_before,
        coverage_pct_after=pct_after,
        delta_coverage_pct=round(pct_after - pct_before, 6),
    )


async def compare_snapshots_file(
    conn: psycopg.AsyncConnection,
    before_id: int,
    after_id: int,
    filter_text: Optional[str] = None,
) -> list[CoverageRowOut]:
    """Compare file-level coverage between two snapshots.

    Only entities present in *both* snapshots are returned (INNER JOIN).
    *filter_text* (optional) restricts to rows where the package name or
    file name contains the substring (case-insensitive).
    """
    filter_clause = ""
    params: list = [before_id, after_id]
    if filter_text:
        filter_clause = "AND (p.name ILIKE %s OR sf.name ILIKE %s)"
        like = f"%{filter_text}%"
        params += [like, like]

    sql = f"""
        SELECT
            p.name || '/' || sf.name                           AS entity_name,
            a.covered_lines                                    AS cl_before,
            b.covered_lines                                    AS cl_after,
            a.covered_branches                                 AS cb_before,
            b.covered_branches                                 AS cb_after,
            a.missed_lines                                     AS ml_before,
            b.missed_lines                                     AS ml_after
        FROM       file_coverage  a
        JOIN       file_coverage  b  ON b.source_file_id = a.source_file_id
        JOIN       source_file    sf ON sf.id = a.source_file_id
        JOIN       package        p  ON p.id  = sf.package_id
        WHERE      a.snapshot_id = %s
          AND      b.snapshot_id = %s
          {filter_clause}
        ORDER BY   entity_name
    """

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()

    return [_build_coverage_row(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows]


async def compare_snapshots_class(
    conn: psycopg.AsyncConnection,
    before_id: int,
    after_id: int,
    filter_text: Optional[str] = None,
) -> list[CoverageRowOut]:
    """Compare class-level coverage between two snapshots."""
    filter_clause = ""
    params: list = [before_id, after_id]
    if filter_text:
        filter_clause = "AND c.name ILIKE %s"
        params.append(f"%{filter_text}%")

    sql = f"""
        SELECT
            c.name                                             AS entity_name,
            a.covered_lines                                    AS cl_before,
            b.covered_lines                                    AS cl_after,
            a.covered_branches                                 AS cb_before,
            b.covered_branches                                 AS cb_after,
            a.missed_lines                                     AS ml_before,
            b.missed_lines                                     AS ml_after
        FROM       class_coverage  a
        JOIN       class_coverage  b  ON b.class_id = a.class_id
        JOIN       java_class      c  ON c.id = a.class_id
        WHERE      a.snapshot_id = %s
          AND      b.snapshot_id = %s
          {filter_clause}
        ORDER BY   c.name
    """

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()

    return [_build_coverage_row(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows]


async def compare_snapshots_method(
    conn: psycopg.AsyncConnection,
    before_id: int,
    after_id: int,
    filter_text: Optional[str] = None,
) -> list[CoverageRowOut]:
    """Compare method-level coverage between two snapshots."""
    filter_clause = ""
    params: list = [before_id, after_id]
    if filter_text:
        filter_clause = "AND (c.name ILIKE %s OR m.name ILIKE %s)"
        like = f"%{filter_text}%"
        params += [like, like]

    sql = f"""
        SELECT
            c.name || '.' || m.name || m.descriptor            AS entity_name,
            a.covered_lines                                    AS cl_before,
            b.covered_lines                                    AS cl_after,
            a.covered_branches                                 AS cb_before,
            b.covered_branches                                 AS cb_after,
            a.missed_lines                                     AS ml_before,
            b.missed_lines                                     AS ml_after
        FROM       method_coverage  a
        JOIN       method_coverage  b  ON b.method_id = a.method_id
        JOIN       method           m  ON m.id = a.method_id
        JOIN       java_class       c  ON c.id = m.class_id
        WHERE      a.snapshot_id = %s
          AND      b.snapshot_id = %s
          {filter_clause}
        ORDER BY   c.name, m.name
    """

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        rows = await cur.fetchall()

    return [_build_coverage_row(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows]
