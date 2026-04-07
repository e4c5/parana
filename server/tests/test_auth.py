"""Tests for authentication and route protection."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_register_and_login(client):
    """Test user registration and subsequent login to get a token."""
    # 1. Register
    reg_resp = await client.post(
        "/auth/register",
        json={"username": "testuser", "password": "testpassword"},
    )
    assert reg_resp.status_code == 201
    assert reg_resp.json()["username"] == "testuser"

    # 2. Login
    login_resp = await client.post(
        "/auth/token",
        data={"username": "testuser", "password": "testpassword"},
    )
    assert login_resp.status_code == 200
    token_data = login_resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_protected_routes_unauthorized(client):
    """Test that coverage routes return 401 when no token is provided."""
    routes = [
        "/codebases",
        "/codebases/1/snapshots",
        "/snapshots/1",
        "/compare?before=1&after=2",
    ]
    for route in routes:
        resp = await client.get(route)
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_authorized(client):
    """Test that a protected route works with a valid token."""
    # Register and login to get a token
    await client.post("/auth/register", json={"username": "authuser", "password": "password123"})
    login_resp = await client.post("/auth/token", data={"username": "authuser", "password": "password123"})
    token = login_resp.json()["access_token"]

    # Call a protected route
    resp = await client.get(
        "/codebases",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
