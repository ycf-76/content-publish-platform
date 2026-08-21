"""SSE integration helpers.

Provides factory functions to create Observer with SSE callback.
Architecture: Layer A (LangGraph) imports this, injects into Layer B (Harness).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.agents.core.harness.observer.observer import Observer
from app.services.sse_bus import sse_bus

if TYPE_CHECKING:
    pass


def create_observer_with_sse(workflow_id: str) -> Observer:
    """Create Observer with SSE callback injected.

    Args:
        workflow_id: Workflow ID for SSE event routing

    Returns:
        Observer instance with SSE publish callback
    """

    async def emit_callback(
        node_id: str, event_type: str, payload: dict
    ) -> None:
        """Callback that publishes events to SSE bus."""
        await sse_bus.publish(
            workflow_id=workflow_id,
            event_type=event_type,
            payload={"node_id": node_id, **payload},
        )

    return Observer(emit_callback=emit_callback)
