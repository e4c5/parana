"""Unit tests for the database query layer (queries.py)."""

from __future__ import annotations

import psycopg
import pytest


# All tests in this module require a running Postgres container.
pytestmark = pytest.mark.usefixtures("seeded_db")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _get_async_conn(dsn: str):
    return await psycopg.AsyncConnection.connect(dsn)


# ---------------------------------------------------------------------------
# list_codebases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_codebases(seeded_db):
    from parana_server.queries import list_codebases

    dsn, ids = seeded_db
    conn = await _get_async_conn(dsn)
    try:
        result = await list_codebases(conn)
    finally:
        await conn.close()

    assert len(result) >= 1
    origins = [r.git_origin for r in result]
    assert "https://github.com/example/repo.git" in origins


# ---------------------------------------------------------------------------
# list_snapshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_snapshots(seeded_db):
    from parana_server.queries import list_snapshots

    dsn, ids = seeded_db
    conn = await _get_async_conn(dsn)
    try:
        result = await list_snapshots(conn, ids["codebase_id"])
    finally:
        await conn.close()

    assert len(result) == 2
    # Newest first
    assert result[0].captured_at >= result[1].captured_at


@pytest.mark.asyncio
async def test_list_snapshots_pagination(seeded_db):
    from parana_server.queries import list_snapshots

    dsn, ids = seeded_db
    conn = await _get_async_conn(dsn)
    try:
        page1 = await list_snapshots(conn, ids["codebase_id"], limit=1, offset=0)
        page2 = await list_snapshots(conn, ids["codebase_id"], limit=1, offset=1)
    finally:
        await conn.close()

    assert len(page1) == 1
    assert len(page2) == 1
    assert page1[0].id != page2[0].id


# ---------------------------------------------------------------------------
# get_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_snapshot_found(seeded_db):
    from parana_server.queries import get_snapshot

    dsn, ids = seeded_db
    conn = await _get_async_conn(dsn)
    try:
        result = await get_snapshot(conn, ids["snap1_id"])
    finally:
        await conn.close()

    assert result is not None
    assert result.id == ids["snap1_id"]
    assert result.git_commit_hash == "a" * 40


@pytest.mark.asyncio
async def test_get_snapshot_not_found(seeded_db):
    from parana_server.queries import get_snapshot

    dsn, ids = seeded_db
    conn = await _get_async_conn(dsn)
    try:
        result = await get_snapshot(conn, 999999)
    finally:
        await conn.close()

    assert result is None


# ---------------------------------------------------------------------------
# compare_snapshots_file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_file(seeded_db):
    from parana_server.queries import compare_snapshots_file

    dsn, ids = seeded_db
    conn = await _get_async_conn(dsn)
    try:
        rows = await compare_snapshots_file(conn, ids["snap1_id"], ids["snap2_id"])
    finally:
        await conn.close()

    assert len(rows) == 1
    row = rows[0]
    assert row.covered_lines_before == 5
    assert row.covered_lines_after == 8
    assert row.delta_covered_lines == 3
    assert row.coverage_pct_before == pytest.approx(0.5)
    assert row.coverage_pct_after == pytest.approx(0.8)
    assert row.delta_coverage_pct == pytest.approx(0.3, abs=1e-5)


@pytest.mark.asyncio
async def test_compare_file_filter(seeded_db):
    from parana_server.queries import compare_snapshots_file

    dsn, ids = seeded_db
    conn = await _get_async_conn(dsn)
    try:
        rows_match = await compare_snapshots_file(
            conn, ids["snap1_id"], ids["snap2_id"], filter_text="com/example"
        )
        rows_no_match = await compare_snapshots_file(
            conn, ids["snap1_id"], ids["snap2_id"], filter_text="nonexistent"
        )
    finally:
        await conn.close()

    assert len(rows_match) == 1
    assert len(rows_no_match) == 0


# ---------------------------------------------------------------------------
# compare_snapshots_class
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_class(seeded_db):
    from parana_server.queries import compare_snapshots_class

    dsn, ids = seeded_db
    conn = await _get_async_conn(dsn)
    try:
        rows = await compare_snapshots_class(conn, ids["snap1_id"], ids["snap2_id"])
    finally:
        await conn.close()

    assert len(rows) == 1
    assert rows[0].entity_name == "com/example/Calculator"
    assert rows[0].delta_covered_lines == 3


# ---------------------------------------------------------------------------
# compare_snapshots_method — only 'add' is in both snapshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_method_excludes_new_method(seeded_db):
    from parana_server.queries import compare_snapshots_method

    dsn, ids = seeded_db
    conn = await _get_async_conn(dsn)
    try:
        rows = await compare_snapshots_method(conn, ids["snap1_id"], ids["snap2_id"])
    finally:
        await conn.close()

    # 'subtract' only exists in snap2 → excluded by INNER JOIN
    assert len(rows) == 1
    assert "add" in rows[0].entity_name
