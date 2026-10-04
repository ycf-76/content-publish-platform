"""Hooks: lifecycle callbacks for tool calls and LLM interactions.

Ref: Codex hooks.rs — hooks are called at defined lifecycle points:
  - Before a tool executes (pre-tool)
  - After a tool executes (post-tool)
  - Before an LLM call (pre-llm)
  - After an LLM call (post-llm)
  - On error (on-error)

Hooks can:
  - Modify arguments before execution
  - Transform results after execution
  - Inject context or metadata
  - Log/audit/telemetry
  - Short-circuit execution (return a result without calling the tool)

Our adaptation:
  - Hook is a simple async callable with a well-defined signature
  - Hooks are registered per-event-type, executed in order
  - A hook can return a modified payload or None (pass-through)
  - If a hook raises, it's logged but doesn't crash the pipeline

Usage:
    hooks = HookRegistry()
    hooks.register("pre_tool", my_logging_hook)
    hooks.register("post_tool", my_audit_hook)

    # In executor:
    modified_args = await hooks.fire("pre_tool", tool_name="search", arguments={...})
    result = await skill.execute(modified_args)
    final_result = await hooks.fire("post_tool", tool_name="search", result=result)
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any, Callable, Coroutine

from pydantic import BaseModel

logger = logging.getLogger(__name__)

HookEvent = str
HookFn = Callable[..., Coroutine[Any, Any, dict[str, Any] | None]]


class HookResult(BaseModel):
    event: str
    hook_name: str
    modified: bool = False
    duration_ms: float = 0


class HookRegistry:
    """Registry and executor for lifecycle hooks.

    Ref: Codex hooks.rs — hooks are stored in a Vec and called in order.
    Each hook receives the current payload and can return a modified version.

    Our adaptation:
      - defaultdict of lists for O(1) append
      - fire() executes hooks sequentially, each receiving the latest payload
      - Errors are caught and logged, never crash the pipeline
      - Built-in timing/metrics for each hook execution
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[HookFn]] = defaultdict(list)
        self._stats: dict[str, int] = defaultdict(int)
        self._error_count = 0

    def register(self, event: str, hook: HookFn) -> None:
        name = getattr(hook, "__name__", repr(hook))
        self._hooks[event].append(hook)
        logger.debug(f"[hooks] registered '{name}' for event '{event}'")

    def unregister(self, event: str, hook: HookFn) -> None:
        if event in self._hooks:
            try:
                self._hooks[event].remove(hook)
            except ValueError:
                pass

    async def fire(
        self,
        event: str,
        **payload: Any,
    ) -> dict[str, Any]:
        """Fire all hooks for an event, returning the (possibly modified) payload."""
        hooks = self._hooks.get(event, [])
        if not hooks:
            return payload

        current = dict(payload)
        for hook in hooks:
            hook_name = getattr(hook, "__name__", repr(hook))
            t0 = time.monotonic()
            try:
                result = await hook(**current)
                if result is not None and isinstance(result, dict):
                    current.update(result)
                self._stats[f"{event}:{hook_name}"] += 1
            except Exception as e:
                self._error_count += 1
                logger.warning(
                    f"[hooks] error in '{hook_name}' for event '{event}': {e}"
                )
            finally:
                elapsed = (time.monotonic() - t0) * 1000
                logger.debug(
                    f"[hooks] {event}:{hook_name} completed in {elapsed:.1f}ms"
                )

        return current

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "events_registered": list(self._hooks.keys()),
            "hooks_per_event": {k: len(v) for k, v in self._hooks.items()},
            "total_firings": sum(self._stats.values()),
            "errors": self._error_count,
        }


# ---- Built-in hooks ----

async def hook_log_tool_call(
    tool_name: str | None = None,
    arguments: dict[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any] | None:
    if tool_name:
        args_summary = str(arguments)[:100] if arguments else "{}"
        logger.info(f"[hook:log] pre_tool: {tool_name} args={args_summary}")
    return None


async def hook_log_tool_result(
    tool_name: str | None = None,
    result: dict[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any] | None:
    if tool_name:
        result_summary = str(result)[:100] if result else "{}"
        logger.info(f"[hook:log] post_tool: {tool_name} result={result_summary}")
    return None


async def hook_measure_llm_latency(
    **payload: Any,
) -> dict[str, Any] | None:
    payload["_hook_timestamp"] = time.monotonic()
    return payload


def create_default_hooks() -> HookRegistry:
    registry = HookRegistry()
    registry.register("pre_tool", hook_log_tool_call)
    registry.register("post_tool", hook_log_tool_result)
    registry.register("pre_llm", hook_measure_llm_latency)
    return registry


# ---- SSE Governance Event hooks ----
# Ref: Codex session.rs — governance events are published to the event bus
# so the frontend can display budget warnings, compaction events, etc.

EVENT_GOVERNANCE_BUDGET_WARNING = "governance_budget_warning"
EVENT_GOVERNANCE_COMPACTION = "governance_compaction"
EVENT_GOVERNANCE_GUARDIAN_DECISION = "governance_guardian_decision"
EVENT_GOVERNANCE_RETRY = "governance_retry"
EVENT_GOVERNANCE_CONTEXT_WINDOW = "governance_context_window"


async def hook_publish_governance_event(
    event_type: str | None = None,
    **payload: Any,
) -> dict[str, Any] | None:
    """Publish governance events to SSE bus for frontend consumption.

    This hook is designed to be called from governance modules,
    not from the standard hook pipeline. It provides a bridge
    between governance events and the SSE event bus.
    """
    if not event_type:
        return None

    try:
        from app.services.sse_bus import sse_bus

        workflow_id = payload.get("context", {})
        if hasattr(workflow_id, "workflow_id"):
            workflow_id = workflow_id.workflow_id
        elif isinstance(workflow_id, dict):
            workflow_id = workflow_id.get("workflow_id", "")
        else:
            workflow_id = str(workflow_id) if workflow_id else ""

        if not workflow_id:
            return None

        clean_payload = {k: v for k, v in payload.items() if k != "context"}
        await sse_bus.publish(workflow_id, event_type, clean_payload)
    except Exception as e:
        logger.debug(f"[hooks] failed to publish governance event: {e}")

    return None