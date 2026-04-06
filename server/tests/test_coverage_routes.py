"""Integration tests for the coverage REST endpoints."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
async def client(app):
    """HTTPX async client wired to the test FastAPI app."""
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c


# ---------------------------------------------------------------------------
# GET /codebases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_codebases(client):
    resp = await client.get("/codebases")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert any(r["git_origin"] == "https://github.com/example/repo.git" for r in data)


# ---------------------------------------------------------------------------
# GET /codebases/{id}/snapshots
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_snapshots(client, seeded_db):
    _, ids = seeded_db
    resp = await client.get(f"/codebases/{ids['codebase_id']}/snapshots")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_snapshots_limit(client, seeded_db):
    _, ids = seeded_db
    resp = await client.get(f"/codebases/{ids['codebase_id']}/snapshots?limit=1")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# GET /snapshots/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_snapshot_ok(client, seeded_db):
    _, ids = seeded_db
    resp = await client.get(f"/snapshots/{ids['snap1_id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == ids["snap1_id"]
    assert data["git_commit_hash"] == "a" * 40


@pytest.mark.asyncio
async def test_get_snapshot_not_found(client):
    resp = await client.get("/snapshots/999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /compare
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_file_level(client, seeded_db):
    _, ids = seeded_db
    resp = await client.get(
        f"/compare?before={ids['snap1_id']}&after={ids['snap2_id']}&level=file"
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["delta_covered_lines"] == 3


@pytest.mark.asyncio
async def test_compare_class_level(client, seeded_db):
    _, ids = seeded_db
    resp = await client.get(
        f"/compare?before={ids['snap1_id']}&after={ids['snap2_id']}&level=class"
    )
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["entity_name"] == "com/example/Calculator"


@pytest.mark.asyncio
async def test_compare_method_level_excludes_missing(client, seeded_db):
    """Entities only in one snapshot must be excluded (INNER JOIN)."""
    _, ids = seeded_db
    resp = await client.get(
        f"/compare?before={ids['snap1_id']}&after={ids['snap2_id']}&level=method"
    )
    assert resp.status_code == 200
    rows = resp.json()
    # 'subtract' only exists in snap2 → excluded; only 'add' returned
    assert len(rows) == 1
    assert "add" in rows[0]["entity_name"]


@pytest.mark.asyncio
async def test_compare_with_filter(client, seeded_db):
    _, ids = seeded_db
    resp = await client.get(
        f"/compare?before={ids['snap1_id']}&after={ids['snap2_id']}"
        f"&level=file&filter=com/example"
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_compare_with_nonmatching_filter(client, seeded_db):
    _, ids = seeded_db
    resp = await client.get(
        f"/compare?before={ids['snap1_id']}&after={ids['snap2_id']}"
        f"&level=file&filter=xyz_nonexistent"
    )
    assert resp.status_code == 200
    assert resp.json() == []
