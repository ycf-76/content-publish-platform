"""Collaboration layer Redis persistence.

Persists AgentManager state to Redis so that:
  - Agent status survives across HTTP requests
  - Frontend can poll collab state via governance API
  - Session recovery after backend restart (best-effort)

Key schema:
  collab:{session_id} -> JSON {
    agents: [{agent_id, name, path, parent_id, depth, role, status, error}],
    max_concurrent: int,
    max_depth: int,
    collab_mode: str,
    updated_at: float,
  }

TTL: 1 hour (auto-cleanup for stale sessions)
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

_COLLAB_KEY_PREFIX = "collab:"
_COLLAB_TTL_SECONDS = 3600


def _make_key(session_id: str) -> str:
    return f"{_COLLAB_KEY_PREFIX}{session_id}"


async def save_collab_state(
    session_id: str,
    agent_manager: Any,
    collab_mode: str = "explicit",
) -> None:
    """Persist current collaboration state to Redis."""
    try:
        from app.cache.redis import redis_client

        agents = agent_manager.list_agents()
        state = {
            "agents": [a.to_dict() for a in agents],
            "max_concurrent": agent_manager.max_concurrent,
            "max_depth": agent_manager._max_depth,
            "collab_mode": collab_mode,
            "updated_at": time.time(),
        }
        await redis_client.set_json(
            _make_key(session_id), state, ex=_COLLAB_TTL_SECONDS
        )
    except Exception as e:
        logger.warning(f"[collab-persist] save failed for {session_id}: {e}")


async def load_collab_state(session_id: str) -> dict[str, Any] | None:
    """Load collaboration state from Redis."""
    try:
        from app.cache.redis import redis_client

        return await redis_client.get_json(_make_key(session_id))
    except Exception as e:
        logger.warning(f"[collab-persist] load failed for {session_id}: {e}")
        return None


async def delete_collab_state(session_id: str) -> None:
    """Delete collaboration state from Redis."""
    try:
        from app.cache.redis import redis_client

        await redis_client.delete(_make_key(session_id))
    except Exception as e:
        logger.warning(f"[collab-persist] delete failed for {session_id}: {e}")


async def update_agent_status(
    session_id: str,
    agent_id: str,
    status: str,
    error: str | None = None,
    result: Any = None,
) -> None:
    """Update a single agent's status in the persisted state.

    More efficient than full save_collab_state for status changes.
    """
    try:
        state = await load_collab_state(session_id)
        if state is None:
            return

        agents = state.get("agents", [])
        for agent in agents:
            if agent.get("agent_id") == agent_id:
                agent["status"] = status
                if error is not None:
                    agent["error"] = error
                break

        state["updated_at"] = time.time()
        from app.cache.redis import redis_client

        await redis_client.set_json(
            _make_key(session_id), state, ex=_COLLAB_TTL_SECONDS
        )
    except Exception as e:
        logger.warning(
            f"[collab-persist] update_agent_status failed for "
            f"{session_id}/{agent_id}: {e}"
        )