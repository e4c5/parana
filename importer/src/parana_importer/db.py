"""Database access layer for the Parana importer.

All public functions accept an open :class:`psycopg.Connection`.  The caller
is responsible for transaction management — typically wrapping a complete import
run in a single ``with conn.transaction():`` block.
"""

from __future__ import annotations

import importlib.resources
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import psycopg
from yoyo import get_backend, read_migrations


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------


def connect(dsn: str) -> psycopg.Connection:
    """Open and return a synchronous psycopg connection."""
    return psycopg.connect(dsn)


# ---------------------------------------------------------------------------
# Schema bootstrap
# ---------------------------------------------------------------------------


def ensure_schema(dsn: str) -> None:
    """Apply any pending database migrations using yoyo-migrations.

    Migrations are located in the ``migrations/`` directory.
    """
    # Locate the migrations directory
    migrations_dir = Path(__file__).parent / "migrations"

    backend = get_backend(dsn)
    migrations = read_migrations(str(migrations_dir))

    if not migrations:
        raise RuntimeError(f"No migrations found in {migrations_dir}")

    with backend.lock():
        # Apply any migrations that haven't been run yet
        backend.apply_migrations(backend.to_apply(migrations))


# ---------------------------------------------------------------------------
# Reference tables (write-once lookup rows, idempotent upserts)
# ---------------------------------------------------------------------------


def upsert_codebase(conn: psycopg.Connection, git_origin: str) -> int:
    """Insert or return the id of the codebase identified by *git_origin*."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO codebase (git_origin)
            VALUES (%s)
            ON CONFLICT (git_origin) DO UPDATE SET git_origin = EXCLUDED.git_origin
            RETURNING id
            """,
            (git_origin,),
        )
        return cur.fetchone()[0]


def upsert_package(conn: psycopg.Connection, codebase_id: int, name: str) -> int:
    """Insert or return the id of a package scoped to *codebase_id*."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO package (codebase_id, name)
            VALUES (%s, %s)
            ON CONFLICT (codebase_id, name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (codebase_id, name),
        )
        return cur.fetchone()[0]


def upsert_source_file(conn: psycopg.Connection, package_id: int, name: str) -> int:
    """Insert or return the id of a source file scoped to *package_id*."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_file (package_id, name)
            VALUES (%s, %s)
            ON CONFLICT (package_id, name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (package_id, name),
        )
        return cur.fetchone()[0]


def upsert_java_class(conn: psycopg.Connection, source_file_id: int, name: str) -> int:
    """Insert or return the id of a class scoped to *source_file_id*."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO java_class (source_file_id, name)
            VALUES (%s, %s)
            ON CONFLICT (source_file_id, name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (source_file_id, name),
        )
        return cur.fetchone()[0]


def upsert_method(
    conn: psycopg.Connection,
    class_id: int,
    name: str,
    descriptor: str,
    start_line: int,
) -> int:
    """Insert or return the id of a method scoped to *class_id*."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO method (class_id, name, descriptor, start_line)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (class_id, name, descriptor)
            DO UPDATE SET start_line = EXCLUDED.start_line
            RETURNING id
            """,
            (class_id, name, descriptor, start_line),
        )
        return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def insert_snapshot(
    conn: psycopg.Connection,
    codebase_id: int,
    git_branch: str,
    git_commit_hash: str,
    uncommitted_files_hash: str,
    captured_at: datetime,
) -> tuple[int, bool]:
    """Insert a new coverage snapshot row.

    Returns:
        A ``(snapshot_id, is_new)`` tuple.  *is_new* is ``False`` when a row
        with the same ``(codebase_id, git_commit_hash, uncommitted_files_hash)``
        already exists — in that case no new row is inserted and the caller
        should skip all subsequent writes.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO coverage_snapshot
                (codebase_id, git_branch, git_commit_hash,
                 uncommitted_files_hash, captured_at)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (codebase_id, git_commit_hash, uncommitted_files_hash)
            DO NOTHING
            RETURNING id
            """,
            (codebase_id, git_branch, git_commit_hash, uncommitted_files_hash, captured_at),
        )
        row = cur.fetchone()
        if row is not None:
            return row[0], True  # freshly inserted

        # Row already exists; retrieve its id.
        cur.execute(
            """
            SELECT id FROM coverage_snapshot
            WHERE codebase_id = %s
              AND git_commit_hash = %s
              AND uncommitted_files_hash = %s
            """,
            (codebase_id, git_commit_hash, uncommitted_files_hash),
        )
        return cur.fetchone()[0], False


# ---------------------------------------------------------------------------
# Bulk inserts — coverage data
# ---------------------------------------------------------------------------


def _counter_map(counters: list[Counter]) -> dict[str, tuple[int, int]]:
    """Build a {type: (missed, covered)} dict from a list of Counter objects."""
    return {c.type: (c.missed, c.covered) for c in counters}


def bulk_insert_line_sequences(
    conn: psycopg.Connection,
    snapshot_id: int,
    rows: list[LineSeqRow],
) -> None:
    """Bulk-insert line coverage sequence rows for one snapshot."""
    if not rows:
        return
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO line_coverage_sequence
                (snapshot_id, source_file_id, start_line, end_line, coverage_status)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (snapshot_id, r.source_file_id, r.start_line, r.end_line, r.coverage_status)
                for r in rows
            ],
        )


def bulk_insert_method_coverage(
    conn: psycopg.Connection,
    snapshot_id: int,
    rows: list[tuple[int, list[Counter]]],
) -> None:
    """Insert method_coverage rows.

    Args:
        rows: list of (method_id, counters) pairs
    """
    if not rows:
        return
    params = []
    for method_id, counters in rows:
        c = _counter_map(counters)
        instr = c.get("INSTRUCTION", (0, 0))
        branch = c.get("BRANCH", (0, 0))
        line = c.get("LINE", (0, 0))
        complexity = c.get("COMPLEXITY", (0, 0))
        params.append((
            snapshot_id, method_id,
            instr[0], instr[1],
            branch[0], branch[1],
            line[0], line[1],
            complexity[0], complexity[1],
        ))
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO method_coverage
                (snapshot_id, method_id,
                 missed_instructions, covered_instructions,
                 missed_branches, covered_branches,
                 missed_lines, covered_lines,
                 missed_complexity, covered_complexity)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_id, method_id) DO NOTHING
            """,
            params,
        )


def bulk_insert_class_coverage(
    conn: psycopg.Connection,
    snapshot_id: int,
    rows: list[tuple[int, list[Counter]]],
) -> None:
    """Insert class_coverage rows.

    Args:
        rows: list of (class_id, counters) pairs
    """
    if not rows:
        return
    params = []
    for class_id, counters in rows:
        c = _counter_map(counters)
        instr = c.get("INSTRUCTION", (0, 0))
        branch = c.get("BRANCH", (0, 0))
        line = c.get("LINE", (0, 0))
        complexity = c.get("COMPLEXITY", (0, 0))
        method = c.get("METHOD", (0, 0))
        params.append((
            snapshot_id, class_id,
            instr[0], instr[1],
            branch[0], branch[1],
            line[0], line[1],
            complexity[0], complexity[1],
            method[0], method[1],
        ))
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO class_coverage
                (snapshot_id, class_id,
                 missed_instructions, covered_instructions,
                 missed_branches, covered_branches,
                 missed_lines, covered_lines,
                 missed_complexity, covered_complexity,
                 missed_methods, covered_methods)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_id, class_id) DO NOTHING
            """,
            params,
        )


def bulk_insert_file_coverage(
    conn: psycopg.Connection,
    snapshot_id: int,
    rows: list[tuple[int, list[Counter]]],
) -> None:
    """Insert file_coverage rows.

    Args:
        rows: list of (source_file_id, counters) pairs
    """
    if not rows:
        return
    params = []
    for sf_id, counters in rows:
        c = _counter_map(counters)
        instr = c.get("INSTRUCTION", (0, 0))
        branch = c.get("BRANCH", (0, 0))
        line = c.get("LINE", (0, 0))
        complexity = c.get("COMPLEXITY", (0, 0))
        method = c.get("METHOD", (0, 0))
        cls = c.get("CLASS", (0, 0))
        params.append((
            snapshot_id, sf_id,
            instr[0], instr[1],
            branch[0], branch[1],
            line[0], line[1],
            complexity[0], complexity[1],
            method[0], method[1],
            cls[0], cls[1],
        ))
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO file_coverage
                (snapshot_id, source_file_id,
                 missed_instructions, covered_instructions,
                 missed_branches, covered_branches,
                 missed_lines, covered_lines,
                 missed_complexity, covered_complexity,
                 missed_methods, covered_methods,
                 missed_classes, covered_classes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_id, source_file_id) DO NOTHING
            """,
            params,
        )


def bulk_insert_package_coverage(
    conn: psycopg.Connection,
    snapshot_id: int,
    rows: list[tuple[int, list[Counter]]],
) -> None:
    """Insert package_coverage rows.

    Args:
        rows: list of (package_id, counters) pairs
    """
    if not rows:
        return
    params = []
    for pkg_id, counters in rows:
        c = _counter_map(counters)
        instr = c.get("INSTRUCTION", (0, 0))
        branch = c.get("BRANCH", (0, 0))
        line = c.get("LINE", (0, 0))
        complexity = c.get("COMPLEXITY", (0, 0))
        method = c.get("METHOD", (0, 0))
        cls = c.get("CLASS", (0, 0))
        params.append((
            snapshot_id, pkg_id,
            instr[0], instr[1],
            branch[0], branch[1],
            line[0], line[1],
            complexity[0], complexity[1],
            method[0], method[1],
            cls[0], cls[1],
        ))
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO package_coverage
                (snapshot_id, package_id,
                 missed_instructions, covered_instructions,
                 missed_branches, covered_branches,
                 missed_lines, covered_lines,
                 missed_complexity, covered_complexity,
                 missed_methods, covered_methods,
                 missed_classes, covered_classes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (snapshot_id, package_id) DO NOTHING
            """,
            params,
        )
