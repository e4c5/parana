"""Unit tests for the chat endpoint.

The LLM client is always mocked so these tests do not require an API key.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture()
async def client(app):
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c


def _make_llm_responses(*texts: str):
    """Build a side_effect list for the mocked ``_llm_chat`` async function."""
    responses = list(texts)
    idx = 0

    async def _mock(*args, **kwargs):
        nonlocal idx
        text = responses[idx % len(responses)]
        idx += 1
        return text

    return _mock


async def _collect_sse(response) -> list[dict]:
    """Parse all SSE events from an httpx streaming response body."""
    events = []
    body = response.content.decode()
    for line in body.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ---------------------------------------------------------------------------
# Missing API key → error event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_no_api_key(auth_client):
    with patch("parana_server.routers.chat._get_llm_client", return_value=None):
        resp = await auth_client.post("/chat", json={"session_id": "s1", "message": "hello"})
    assert resp.status_code == 200
    events = await _collect_sse(resp)
    types = [e["type"] for e in events]
    assert "error" in types
    assert "done" in types


# ---------------------------------------------------------------------------
# Normal text answer flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_text_answer(auth_client, seeded_db):
    _, ids = seeded_db
    intent_json = json.dumps({"action": "list_codebases", "params": {}})
    render_json = json.dumps({"result_type": "text", "answer": "There is 1 codebase."})

    mock_llm = (AsyncMock(), "gpt-4o-mini")

    with (
        patch("parana_server.routers.chat._get_llm_client", return_value=mock_llm),
        patch(
            "parana_server.routers.chat._llm_chat",
            _make_llm_responses(intent_json, render_json),
        ),
    ):
        resp = await auth_client.post(
            "/chat", json={"session_id": "s2", "message": "How many codebases?"}
        )

    assert resp.status_code == 200
    events = await _collect_sse(resp)
    types = [e["type"] for e in events]
    assert "text_delta" in types
    assert "done" in types
    # No "result" event for text answers
    assert "result" not in types

    text_events = [e for e in events if e["type"] == "text_delta"]
    assert any("1 codebase" in (e.get("data") or "") for e in text_events)


# ---------------------------------------------------------------------------
# Table answer flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_table_answer(auth_client, seeded_db):
    _, ids = seeded_db
    intent_json = json.dumps({
        "action": "compare",
        "params": {
            "before_id": ids["snap1_id"],
            "after_id": ids["snap2_id"],
            "level": "file",
        },
    })
    render_json = json.dumps({"result_type": "table", "summary": "Coverage improved."})

    mock_llm = (AsyncMock(), "gpt-4o-mini")

    with (
        patch("parana_server.routers.chat._get_llm_client", return_value=mock_llm),
        patch(
            "parana_server.routers.chat._llm_chat",
            _make_llm_responses(intent_json, render_json),
        ),
    ):
        resp = await auth_client.post(
            "/chat",
            json={"session_id": "s3", "message": "Compare snap1 and snap2"},
        )

    assert resp.status_code == 200
    events = await _collect_sse(resp)
    types = [e["type"] for e in events]
    assert "result" in types
    assert "done" in types

    result_events = [e for e in events if e["type"] == "result"]
    assert len(result_events) == 1
    payload = result_events[0]["data"]
    assert payload["result_type"] == "table"
    assert "columns" in payload
    assert "rows" in payload


# ---------------------------------------------------------------------------
# SSE event order guarantee
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_event_order(auth_client):
    intent_json = json.dumps({"action": "no_data", "params": {}})
    render_json = json.dumps({"result_type": "text", "answer": "No data available."})

    mock_llm = (AsyncMock(), "gpt-4o-mini")

    with (
        patch("parana_server.routers.chat._get_llm_client", return_value=mock_llm),
        patch(
            "parana_server.routers.chat._llm_chat",
            _make_llm_responses(intent_json, render_json),
        ),
    ):
        resp = await auth_client.post(
            "/chat", json={"session_id": "s4", "message": "anything"}
        )

    events = await _collect_sse(resp)
    assert events[-1]["type"] == "done"


# ---------------------------------------------------------------------------
# Session history accumulates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_history_grows(auth_client):
    from parana_server.routers.chat import _session_history

    session_id = "s_history_test"
    _session_history.pop(session_id, None)

    intent_json = json.dumps({"action": "no_data", "params": {}})
    render_json = json.dumps({"result_type": "text", "answer": "ok"})

    mock_llm = (AsyncMock(), "gpt-4o-mini")

    for _ in range(2):
        with (
            patch("parana_server.routers.chat._get_llm_client", return_value=mock_llm),
            patch(
                "parana_server.routers.chat._llm_chat",
                _make_llm_responses(intent_json, render_json),
            ),
        ):
            await auth_client.post(
                "/chat", json={"session_id": session_id, "message": "ping"}
            )

    # 2 turns × 2 messages (user + assistant) = 4 history entries
    assert len(_session_history[session_id]) == 4
