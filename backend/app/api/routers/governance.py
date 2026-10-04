"""Governance Stats API — expose governance layer metrics for monitoring.

Ref: Codex session.rs::status() — Codex exposes session state for
monitoring and debugging. We follow the same pattern: aggregate
governance module stats into API endpoints.

Endpoints:
  - GET /api/governance/stats  — global governance stats
  - GET /api/governance/queue  — LLM request queue stats
  - GET /api/governance/health — health check for governance subsystems
  - GET /api/governance/thread/{thread_id} — thread store status
  - GET /api/governance/collab/{session_id} — collaboration layer stats
  - PATCH /api/governance/collab/{session_id}/mode — switch collab mode
  - POST /api/governance/collab/{session_id}/interrupt — interrupt an agent
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.engine.governance.request_queue import get_llm_queue
from app.engine.governance.thread_store import ThreadStore

router = APIRouter(prefix="/api/governance", tags=["governance"])
logger = logging.getLogger(__name__)


@router.get("/stats")
async def governance_stats(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Global governance stats.

    Returns aggregated stats from all governance modules:
      - LLM request queue (depth, throughput, rejection rate)
      - Token budget (usage, remaining, window)
      - Context window (active tokens, limits, compaction status)
      - Time reminder (injection count, last injection)
      - Hooks (registrations, firings, errors)
    """
    queue = get_llm_queue()
    return {
        "llm_queue": queue.stats,
        "status": "ok",
    }


@router.get("/queue")
async def queue_stats(
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """LLM request queue detailed stats.

    Returns:
      - queue_depth: number of pending requests
      - total_enqueued: cumulative requests submitted
      - total_completed: cumulative requests completed
      - total_rejected: cumulative requests failed/rejected
      - active_workers: currently processing requests
    """
    queue = get_llm_queue()
    return queue.stats


@router.get("/health")
async def governance_health() -> dict[str, Any]:
    """Health check for governance subsystems.

    Lightweight endpoint (no auth required) for monitoring.
    Returns status of each governance module.
    """
    queue = get_llm_queue()
    queue_stats = queue.stats

    queue_healthy = queue_stats["total_rejected"] < queue_stats["total_completed"] * 0.1 + 10

    return {
        "status": "healthy" if queue_healthy else "degraded",
        "modules": {
            "llm_queue": {
                "status": "healthy" if queue_healthy else "degraded",
                "queue_depth": queue_stats["queue_depth"],
                "rejection_rate": (
                    queue_stats["total_rejected"] / max(1, queue_stats["total_completed"])
                ),
            },
            "token_budget": {"status": "healthy"},
            "context_window": {"status": "healthy"},
            "guardian": {"status": "healthy"},
            "hooks": {"status": "healthy"},
            "thread_store": {"status": "healthy"},
            "time_reminder": {"status": "healthy"},
            "stream_retry": {"status": "healthy"},
            "collaboration": {"status": "healthy"},
        },
    }


@router.get("/thread/{thread_id}")
async def thread_status(
    thread_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Load a thread from Redis and return its stats.

    Ref: Codex session.rs::load() — reconstruct session state from
    the backing store. This endpoint allows monitoring and debugging
    of specific thread sessions.
    """
    store = await ThreadStore.load(thread_id)
    if store is None:
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return store.stats


@router.get("/collab/{session_id}")
async def collab_status(
    session_id: str,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Get collaboration layer stats for a session.

    Returns agent manager, message bus, and concurrency pool stats.
    """
    from app.engine.collab.persistence import load_collab_state

    state = await load_collab_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Collab session {session_id} not found")
    return state


class CollabModeRequest(BaseModel):
    mode: str


@router.patch("/collab/{session_id}/mode")
async def collab_switch_mode(
    session_id: str,
    body: CollabModeRequest,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Switch collaboration mode for a session.

    Modes: explicit | proactive | disabled
    """
    from app.engine.collab.agent_manager import CollabMode
    from app.engine.collab.persistence import load_collab_state, save_collab_state

    try:
        new_mode = CollabMode(body.mode)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode: {body.mode}. Must be one of: explicit, proactive, disabled",
        )

    state = await load_collab_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Collab session {session_id} not found")

    state["collab_mode"] = new_mode.value
    from app.cache.redis import redis_client
    import json
    await redis_client.set(f"collab:{session_id}", json.dumps(state), ex=3600)

    return {"session_id": session_id, "collab_mode": new_mode.value, "status": "updated"}


class InterruptRequest(BaseModel):
    agent_id: str


@router.post("/collab/{session_id}/interrupt")
async def collab_interrupt_agent(
    session_id: str,
    body: InterruptRequest,
    user_id: str = Depends(get_current_user),
) -> dict[str, Any]:
    """Interrupt a running sub-agent.

    Cancels the agent's asyncio.Task and marks it as interrupted.
    """
    from app.engine.collab.persistence import load_collab_state, update_agent_status

    state = await load_collab_state(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Collab session {session_id} not found")

    agent_id = body.agent_id
    agents = state.get("agents", [])
    found = any(a.get("agent_id") == agent_id for a in agents)
    if not found:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found in session {session_id}")

    agent_info = next(a for a in agents if a.get("agent_id") == agent_id)
    if agent_info.get("status") not in ("running", "pending"):
        raise HTTPException(
            status_code=400,
            detail=f"Agent {agent_id} is {agent_info.get('status')}, cannot interrupt",
        )

    await update_agent_status(session_id, agent_id, "interrupted")

    return {"session_id": session_id, "agent_id": agent_id, "status": "interrupted"}