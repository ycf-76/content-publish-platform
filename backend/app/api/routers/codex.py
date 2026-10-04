"""Codex mode API endpoint.

Provides two endpoints:
1. POST /api/v1/codex/run — Synchronous run (returns JSON with full steps)
2. POST /api/v1/codex/stream — SSE stream (real-time thought/tool/observation events)
3. GET  /api/v1/codex/info — List primitives and permissions

The SSE stream endpoint is the primary one for frontend use.
The synchronous endpoint is kept for simple scripts and testing.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.engine.schemas import Permission
from app.api.deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/codex", tags=["codex"])


class CodexRunRequest(BaseModel):
    intent: str = Field(..., min_length=1, max_length=10000, description="User intent")
    permissions: list[str] = Field(
        default_factory=list,
        description="Granted permissions (e.g. ['file:read', 'file:write', 'bash:exec', 'xhs:search'])",
    )
    max_iterations: int = Field(default=12, ge=1, le=30, description="Max ReAct loop iterations")
    context: dict[str, Any] | None = Field(default=None, description="Extra context")
    session_id: str | None = Field(default=None, description="Optional session ID for SSE events")


class CodexRunResponse(BaseModel):
    ok: bool
    output: dict[str, Any]
    iterations: int
    token_usage: int
    last_thought: str
    steps: list[dict[str, Any]]
    duration_ms: int


class CodexInfoResponse(BaseModel):
    primitives: list[dict[str, Any]]
    permissions_available: list[str]


def _parse_permissions(perm_strs: list[str]) -> set[Permission]:
    result: set[Permission] = set()
    for s in perm_strs:
        try:
            result.add(Permission(s))
        except ValueError:
            logger.warning(f"[codex] unknown permission ignored: {s}")
    return result


@router.post("/run", response_model=CodexRunResponse)
async def codex_run(
    request: CodexRunRequest,
    user_id: str = Depends(get_current_user),
) -> CodexRunResponse:
    """Run a task in Codex mode (synchronous, returns full result with steps)."""
    from app.engine.codex.session import build_codex_session

    permissions = _parse_permissions(request.permissions)
    context = request.context or {}
    context.setdefault("user_id", user_id)

    session = build_codex_session(
        workflow_id=request.session_id or "",
        allowed_permissions=permissions,
        max_iterations=request.max_iterations,
    )

    start = time.monotonic()
    try:
        result = await session.run(request.intent, context=context)
    except Exception as e:
        logger.exception("[codex] session.run failed")
        raise HTTPException(status_code=500, detail=str(e))
    duration_ms = int((time.monotonic() - start) * 1000)

    return CodexRunResponse(
        ok=True,
        output={k: v for k, v in result.items() if not k.startswith("_")},
        iterations=result.get("_iterations", 0),
        token_usage=result.get("_token_usage", 0),
        last_thought=result.get("_last_thought", ""),
        steps=result.get("_steps", []),
        duration_ms=duration_ms,
    )


@router.post("/stream")
async def codex_stream(
    request: CodexRunRequest,
    user_id: str = Depends(get_current_user),
) -> StreamingResponse:
    """Run a task in Codex mode with SSE streaming.

    Returns a real-time event stream with:
    - workflow_started: session begins
    - agent_thinking: LLM reasoning (chain-of-thought)
    - decision_made: LLM's thought/plan for this iteration
    - tool_call_start: tool about to be called (with inputs)
    - tool_call_end: tool finished (with summary + duration)
    - progress_update: iteration progress
    - node_completed: final output
    - workflow_completed: session ends

    Frontend consumes via fetch + ReadableStream (same as /api/sse/workflow/{id}).
    """
    from app.engine.codex.session import CodexSession
    from app.engine.factory import get_deepseek_llm

    permissions = _parse_permissions(request.permissions)
    context = request.context or {}
    context.setdefault("user_id", user_id)

    llm = get_deepseek_llm()
    event_queue: asyncio.Queue = asyncio.Queue()

    session = CodexSession(
        llm=llm,
        allowed_permissions=permissions,
        max_iterations=request.max_iterations,
    )

    original_emit_sse = session._emit_sse

    async def _queue_emit(event_type: str, payload: dict[str, Any]) -> None:
        await original_emit_sse(event_type, payload)
        await event_queue.put({"event_type": event_type, "payload": payload})

    session._emit_sse = _queue_emit

    async def _run_and_signal_done():
        try:
            await session.run(request.intent, context=context)
        except Exception as e:
            logger.exception("[codex/stream] session.run failed")
            await event_queue.put({
                "event_type": "workflow_error",
                "payload": {"error": str(e)},
            })
        finally:
            await event_queue.put(None)

    task = asyncio.create_task(_run_and_signal_done())

    async def event_stream():
        try:
            while True:
                item = await event_queue.get()
                if item is None:
                    break
                event_type = item["event_type"]
                payload = item["payload"]
                data = json.dumps(payload, ensure_ascii=False, default=str)
                yield f"event: {event_type}\ndata: {data}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/info", response_model=CodexInfoResponse)
async def codex_info() -> CodexInfoResponse:
    """List available primitives and permissions."""
    from app.engine.codex.primitives import ALL_PRIMITIVES

    primitives = [p.info() for p in ALL_PRIMITIVES]
    permissions = [p.value for p in Permission]

    return CodexInfoResponse(
        primitives=primitives,
        permissions_available=permissions,
    )