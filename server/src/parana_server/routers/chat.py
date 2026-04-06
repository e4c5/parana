"""Chat endpoint — POST /chat.

Implements the two-LLM-call flow described in §3.2.2 of the software design:

1. **Intent resolution** — the user message + API schema description → LLM
   decides which coverage endpoint to call (or emits a "no_data" response).
2. **Execute** — the importer's psycopg query functions are called directly.
3. **Render decision** — original question + raw result → LLM produces the
   final answer text (and signals "table" or "text" presentation).
4. **SSE stream** — typed events: ``text_delta``, ``result``, ``done``, ``error``.

Per-session conversation history is kept in-memory, keyed on ``session_id``.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import AsyncGenerator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..db import get_conn
from ..models import ChatRequest, ResultPayload, SSEChunk
from .. import queries

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory session history: session_id → list of {"role": ..., "content": ...}
_session_history: dict[str, list[dict]] = defaultdict(list)

# ---------------------------------------------------------------------------
# API schema description supplied to the intent-resolution LLM call
# ---------------------------------------------------------------------------
_API_SCHEMA = """
You are a data assistant for the Parana coverage-tracking system.
Available API calls (return JSON):

1. list_codebases() → list of {id, git_origin}
2. list_snapshots(codebase_id, limit?, offset?) → list of {id, codebase_id, git_branch, git_commit_hash, captured_at}
3. get_snapshot(snapshot_id) → {id, codebase_id, git_branch, git_commit_hash, captured_at}
4. compare(before_id, after_id, level="file"|"class"|"method", filter?) →
   list of {entity_name, covered_lines_before, covered_lines_after, delta_covered_lines,
             covered_branches_before, covered_branches_after, delta_covered_branches,
             coverage_pct_before, coverage_pct_after, delta_coverage_pct}

Respond ONLY with a JSON object (no prose, no markdown fences) with this schema:
{
  "action": "list_codebases" | "list_snapshots" | "get_snapshot" | "compare" | "no_data",
  "params": { ... }   // key-value pairs matching the function signature above
}

If the question cannot be answered with the available API, use action="no_data".
""".strip()

_RENDER_PROMPT = """
You are a helpful assistant. The user asked: {question}

The API returned the following data:
{data}

Decide how to present this answer:
- If the data is a list of rows, respond with JSON: {{"result_type": "table", "summary": "..."}}
- If a simple text answer is better, respond with JSON: {{"result_type": "text", "answer": "..."}}

Respond ONLY with the JSON object above — no prose, no markdown fences.
""".strip()


def _sse_line(chunk: SSEChunk) -> str:
    """Encode a single SSE line."""
    payload = chunk.model_dump_json()
    return f"data: {payload}\n\n"


def _get_llm_client():
    """Lazily import and return an OpenAI client.

    Returns ``None`` when ``OPENAI_API_KEY`` / ``LLM_API_KEY`` is not set
    (useful for tests that mock this layer).
    """
    import os
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    if not api_key:
        return None
    try:
        from openai import AsyncOpenAI
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        return AsyncOpenAI(api_key=api_key), model
    except Exception:
        return None


async def _llm_chat(messages: list[dict], client_info) -> str:
    """Call the LLM and return the response text."""
    client, model = client_info
    response = await client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
    )
    return response.choices[0].message.content or ""


async def _resolve_intent(question: str, history: list[dict], client_info) -> dict:
    """Ask the LLM which API action to take."""
    messages = [
        {"role": "system", "content": _API_SCHEMA},
        *history,
        {"role": "user", "content": question},
    ]
    raw = await _llm_chat(messages, client_info)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"action": "no_data", "params": {}}


async def _execute_action(action: str, params: dict, conn) -> list | dict | None:
    """Execute the resolved API action and return raw data."""
    if action == "list_codebases":
        rows = await queries.list_codebases(conn)
        return [r.model_dump() for r in rows]
    if action == "list_snapshots":
        codebase_id = int(params.get("codebase_id", 0))
        limit = int(params.get("limit", 20))
        offset = int(params.get("offset", 0))
        rows = await queries.list_snapshots(conn, codebase_id, limit=limit, offset=offset)
        return [r.model_dump() for r in rows]
    if action == "get_snapshot":
        snap = await queries.get_snapshot(conn, int(params.get("snapshot_id", 0)))
        return snap.model_dump() if snap else None
    if action == "compare":
        before_id = int(params.get("before_id", 0))
        after_id = int(params.get("after_id", 0))
        level = params.get("level", "file")
        filter_text = params.get("filter")
        if level == "file":
            rows = await queries.compare_snapshots_file(conn, before_id, after_id, filter_text)
        elif level == "class":
            rows = await queries.compare_snapshots_class(conn, before_id, after_id, filter_text)
        else:
            rows = await queries.compare_snapshots_method(conn, before_id, after_id, filter_text)
        return [r.model_dump() for r in rows]
    return None


async def _render_response(
    question: str,
    raw_data,
    client_info,
) -> tuple[str, ResultPayload | None]:
    """Ask the LLM how to render the result; return (text, result_payload)."""
    data_str = json.dumps(raw_data, default=str)
    prompt = _RENDER_PROMPT.format(question=question, data=data_str)
    messages = [{"role": "user", "content": prompt}]
    raw = await _llm_chat(messages, client_info)
    try:
        render = json.loads(raw)
    except json.JSONDecodeError:
        render = {"result_type": "text", "answer": raw}

    result_type = render.get("result_type", "text")
    summary = render.get("summary") or render.get("answer") or ""

    if result_type == "table" and isinstance(raw_data, list) and raw_data:
        columns = list(raw_data[0].keys()) if raw_data else []
        payload = ResultPayload(result_type="table", columns=columns, rows=raw_data)
    else:
        payload = ResultPayload(result_type="text")

    return summary, payload


async def _stream_chat(
    request: ChatRequest,
    conn,
) -> AsyncGenerator[str, None]:
    """Core generator that produces SSE lines for one chat turn."""
    history = _session_history[request.session_id]

    client_info = _get_llm_client()
    if client_info is None:
        yield _sse_line(SSEChunk(type="error", data="LLM not configured (missing API key)"))
        yield _sse_line(SSEChunk(type="done"))
        return

    try:
        # Step 1 — intent resolution
        intent = await _resolve_intent(request.message, history, client_info)
        action = intent.get("action", "no_data")
        params = intent.get("params", {})

        # Step 2 — execute
        raw_data = await _execute_action(action, params, conn)

        # Step 3 — render decision
        answer_text, result_payload = await _render_response(
            request.message, raw_data, client_info
        )

        # Step 4 — stream
        if answer_text:
            yield _sse_line(SSEChunk(type="text_delta", data=answer_text))

        if result_payload.result_type == "table":
            yield _sse_line(SSEChunk(type="result", data=result_payload))

        yield _sse_line(SSEChunk(type="done"))

        # Update session history
        history.append({"role": "user", "content": request.message})
        history.append({"role": "assistant", "content": answer_text})
        # Cap history at 20 turns to avoid unbounded growth
        if len(history) > 40:
            _session_history[request.session_id] = history[-40:]

    except Exception as exc:  # noqa: BLE001
        logger.exception("Chat error for session %s", request.session_id)
        yield _sse_line(SSEChunk(type="error", data=str(exc)))
        yield _sse_line(SSEChunk(type="done"))


@router.post("/chat")
async def chat(request: ChatRequest, conn=Depends(get_conn)):
    """Accept a plain-English question and stream the answer as SSE."""
    return StreamingResponse(
        _stream_chat(request, conn),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
