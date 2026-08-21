"""Workflow lifecycle event helpers.

Emits workflow-level SSE events following protocol Ch.5.
"""

from __future__ import annotations

from app.services.sse_bus import sse_bus


async def emit_workflow_started(
    workflow_id: str,
    user_id: str,
    account_id: str,
    topic: str,
) -> None:
    """Emit workflow_started event."""
    await sse_bus.publish(
        workflow_id,
        "workflow_started",
        {
            "user_id": user_id,
            "account_id": account_id,
            "topic": topic,
        },
    )


async def emit_workflow_snapshot(
    workflow_id: str,
    current_node: str,
    node_statuses: dict[str, str],
) -> None:
    """Emit workflow_snapshot event (periodic status update)."""
    await sse_bus.publish(
        workflow_id,
        "workflow_snapshot",
        {
            "current_node": current_node,
            "node_statuses": node_statuses,
        },
    )


async def emit_workflow_completed(
    workflow_id: str,
    final_output: dict,
) -> None:
    """Emit workflow_completed event."""
    await sse_bus.publish(
        workflow_id,
        "workflow_completed",
        {"final_output": final_output},
    )


async def emit_workflow_error(
    workflow_id: str,
    error_code: str,
    error_message: str,
    node_id: str | None = None,
) -> None:
    """Emit workflow_error event."""
    payload = {
        "error_code": error_code,
        "error_message": error_message,
    }
    if node_id:
        payload["node_id"] = node_id
    await sse_bus.publish(workflow_id, "workflow_error", payload)


async def emit_workflow_suspended(
    workflow_id: str,
    reason: str,
    resume_after: str | None = None,
) -> None:
    """Emit workflow_suspended event (D15 suspension)."""
    payload = {"reason": reason}
    if resume_after:
        payload["resume_after"] = resume_after
    await sse_bus.publish(workflow_id, "workflow_suspended", payload)


async def emit_workflow_resumed(workflow_id: str) -> None:
    """Emit workflow_resumed event."""
    await sse_bus.publish(workflow_id, "workflow_resumed", {})


async def emit_workflow_paused(workflow_id: str, paused_at_node: str) -> None:
    """Emit workflow_paused event (D9 soft pause)."""
    await sse_bus.publish(
        workflow_id,
        "workflow_paused",
        {"paused_at_node": paused_at_node},
    )


async def emit_checkpoint_saved(
    workflow_id: str,
    checkpoint_id: str,
    node_id: str,
) -> None:
    """Emit checkpoint_saved event (D6 rollback point)."""
    await sse_bus.publish(
        workflow_id,
        "checkpoint_saved",
        {"checkpoint_id": checkpoint_id, "node_id": node_id},
    )


async def emit_review_required(
    workflow_id: str,
    review_id: str,
    review_type: str,
    node_id: str,
    content: dict,
) -> None:
    """Emit review_required event."""
    await sse_bus.publish(
        workflow_id,
        "review_required",
        {
            "review_id": review_id,
            "review_type": review_type,
            "node_id": node_id,
            "content": content,
        },
    )


async def emit_review_processed(
    workflow_id: str,
    review_id: str,
    action: str,
    node_id: str,
) -> None:
    """Emit review_processed event."""
    await sse_bus.publish(
        workflow_id,
        "review_processed",
        {
            "review_id": review_id,
            "action": action,
            "node_id": node_id,
        },
    )


async def emit_image_generated(
    workflow_id: str,
    node_id: str,
    image_url: str,
    image_index: int,
) -> None:
    """Emit image_generated event (during image_gen node)."""
    await sse_bus.publish(
        workflow_id,
        "image_generated",
        {
            "node_id": node_id,
            "image_url": image_url,
            "image_index": image_index,
        },
    )


async def emit_supervisor_suggestion(
    workflow_id: str,
    suggestion_id: str,
    suggestion_type: str,
    content: str,
) -> None:
    """Emit supervisor_suggestion event (D15)."""
    await sse_bus.publish(
        workflow_id,
        "supervisor_suggestion",
        {
            "suggestion_id": suggestion_id,
            "suggestion_type": suggestion_type,
            "content": content,
        },
    )


async def emit_search_degraded(
    workflow_id: str,
    reason: str,
    fallback_used: str,
) -> None:
    """Emit search_degraded event (D17 system event)."""
    await sse_bus.publish(
        workflow_id,
        "search_degraded",
        {"reason": reason, "fallback_used": fallback_used},
    )
