"""Shared pytest fixtures for the Parana server test suite.

The ``db`` session-scoped fixture spins up a Postgres container via
testcontainers, applies the schema, and seeds a minimal dataset:

  codebase: id=1, git_origin='https://github.com/example/repo.git'
  snapshots: ids 1 (before) and 2 (after)
  One package / source file / class / two methods
  file_coverage, class_coverage, method_coverage rows for both snapshots
"""

from __future__ import annotations

import os
import pathlib
from datetime import datetime, timezone

import psycopg
import pytest


# Set TESTCONTAINERS_RYUK_DISABLED if it's not already set.
# This improves compatibility with Podman-based environments where the Ryuk reaper
# container may fail to start or connect.
if "TESTCONTAINERS_RYUK_DISABLED" not in os.environ:
    os.environ["TESTCONTAINERS_RYUK_DISABLED"] = "true"

_DESIGN_DIR = pathlib.Path(__file__).parent.parent.parent / "design"
_SCHEMA_PATH = _DESIGN_DIR / "schema.sql"


def _apply_schema(conn: psycopg.Connection) -> None:
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()


def _seed(conn: psycopg.Connection) -> dict:
    """Insert minimal fixture data and return a dict of inserted IDs."""
    ids: dict = {}
    with conn.cursor() as cur:
        # codebase
        cur.execute(
            "INSERT INTO codebase (git_origin) VALUES (%s) RETURNING id",
            ("https://github.com/example/repo.git",),
        )
        ids["codebase_id"] = cur.fetchone()[0]

        # package
        cur.execute(
            "INSERT INTO package (codebase_id, name) VALUES (%s, %s) RETURNING id",
            (ids["codebase_id"], "com/example"),
        )
        ids["package_id"] = cur.fetchone()[0]

        # source_file
        cur.execute(
            "INSERT INTO source_file (package_id, name) VALUES (%s, %s) RETURNING id",
            (ids["package_id"], "Calculator.java"),
        )
        ids["source_file_id"] = cur.fetchone()[0]

        # java_class
        cur.execute(
            "INSERT INTO java_class (source_file_id, name) VALUES (%s, %s) RETURNING id",
            (ids["source_file_id"], "com/example/Calculator"),
        )
        ids["class_id"] = cur.fetchone()[0]

        # methods
        cur.execute(
            "INSERT INTO method (class_id, name, descriptor, start_line) VALUES (%s, %s, %s, %s) RETURNING id",
            (ids["class_id"], "add", "(II)I", 5),
        )
        ids["method_add_id"] = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO method (class_id, name, descriptor, start_line) VALUES (%s, %s, %s, %s) RETURNING id",
            (ids["class_id"], "subtract", "(II)I", 10),
        )
        ids["method_sub_id"] = cur.fetchone()[0]

        # snapshots: before (snap1) and after (snap2)
        cur.execute(
            """
            INSERT INTO coverage_snapshot
                (codebase_id, git_branch, git_commit_hash, uncommitted_files_hash, captured_at)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (
                ids["codebase_id"],
                "main",
                "a" * 40,
                "CLEAN",
                datetime(2024, 1, 1, tzinfo=timezone.utc),
            ),
        )
        ids["snap1_id"] = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO coverage_snapshot
                (codebase_id, git_branch, git_commit_hash, uncommitted_files_hash, captured_at)
            VALUES (%s, %s, %s, %s, %s) RETURNING id
            """,
            (
                ids["codebase_id"],
                "main",
                "b" * 40,
                "CLEAN",
                datetime(2024, 1, 2, tzinfo=timezone.utc),
            ),
        )
        ids["snap2_id"] = cur.fetchone()[0]

        # file_coverage rows
        for snap_id, cl, ml in [
            (ids["snap1_id"], 5, 5),   # before: 50 % coverage
            (ids["snap2_id"], 8, 2),   # after:  80 %
        ]:
            cur.execute(
                """
                INSERT INTO file_coverage
                    (snapshot_id, source_file_id,
                     covered_lines, missed_lines,
                     covered_branches, missed_branches,
                     covered_instructions, missed_instructions,
                     covered_complexity, missed_complexity,
                     covered_methods, missed_methods,
                     covered_classes, missed_classes)
                VALUES (%s, %s, %s, %s, 2, 2, 10, 10, 1, 1, 1, 1, 1, 0)
                """,
                (snap_id, ids["source_file_id"], cl, ml),
            )

        # class_coverage rows
        for snap_id, cl, ml in [
            (ids["snap1_id"], 5, 5),
            (ids["snap2_id"], 8, 2),
        ]:
            cur.execute(
                """
                INSERT INTO class_coverage
                    (snapshot_id, class_id,
                     covered_lines, missed_lines,
                     covered_branches, missed_branches,
                     covered_instructions, missed_instructions,
                     covered_complexity, missed_complexity,
                     covered_methods, missed_methods)
                VALUES (%s, %s, %s, %s, 2, 2, 10, 10, 1, 1, 1, 1)
                """,
                (snap_id, ids["class_id"], cl, ml),
            )

        # method_coverage for 'add' — present in both snapshots
        for snap_id, cl, ml in [
            (ids["snap1_id"], 2, 0),
            (ids["snap2_id"], 2, 0),
        ]:
            cur.execute(
                """
                INSERT INTO method_coverage
                    (snapshot_id, method_id,
                     covered_lines, missed_lines,
                     covered_branches, missed_branches,
                     covered_instructions, missed_instructions,
                     covered_complexity, missed_complexity)
                VALUES (%s, %s, %s, %s, 0, 0, 4, 0, 1, 0)
                """,
                (snap_id, ids["method_add_id"], cl, ml),
            )

        # method_coverage for 'subtract' — only in snap2 (simulates added method)
        cur.execute(
            """
            INSERT INTO method_coverage
                (snapshot_id, method_id,
                 covered_lines, missed_lines,
                 covered_branches, missed_branches,
                 covered_instructions, missed_instructions,
                 covered_complexity, missed_complexity)
            VALUES (%s, %s, 0, 2, 0, 0, 0, 4, 0, 1)
            """,
            (ids["snap2_id"], ids["method_sub_id"]),
        )

    conn.commit()
    return ids


@pytest.fixture(scope="session")
def db_dsn():
    """Start a Postgres container and return its DSN."""
    try:
        from testcontainers.postgres import PostgresContainer
    except ImportError:
        pytest.skip("testcontainers[postgres] not installed")

    with PostgresContainer("postgres:16") as pg:
        url = pg.get_connection_url()
        dsn = url.replace("postgresql+psycopg2://", "postgresql://").replace(
            "postgresql+psycopg://", "postgresql://"
        )
        yield dsn


@pytest.fixture(scope="session")
def seeded_db(db_dsn):
    """Apply schema + seed data; return the IDs dict."""
    with psycopg.connect(db_dsn) as conn:
        _apply_schema(conn)
        ids = _seed(conn)
    return db_dsn, ids


@pytest.fixture()
def app(seeded_db):
    """Return a configured FastAPI app wired to the test database."""
    from parana_server.main import create_app

    db_dsn, _ids = seeded_db
    return create_app(dsn=db_dsn)
