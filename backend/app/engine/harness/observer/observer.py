"""Observer layer (D16 process transparency).

Codex-style two-phase event model:
  Phase 1 (Delta):  streaming incremental updates (reasoning_summary_text_delta, agent_message_delta)
  Phase 2 (Completed): item finalization (reasoning_completed, agent_message_completed)

Delta events update status bar and stream tail only — they do NOT write to history.
Completed events write the final item to history, replacing the stream tail.

Red line: must NOT import SSE or FastAPI directly.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

EmitCallback = Callable[[str, str, dict[str, Any]], Awaitable[None]]


async def _noop(node_id: str, event_type: str, payload: dict[str, Any]) -> None:
    pass


class Observer:
    """D16 observation layer with Codex-style two-phase events."""

    def __init__(self, emit_callback: EmitCallback | None = None):
        self._emit_callback = emit_callback
        self._emit = emit_callback or _noop

    async def emit(self, node_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await self._emit(node_id, event_type, payload)

    # ------------------------------------------------------------------
    # Phase 1: Delta events (streaming, do NOT write to history)
    # ------------------------------------------------------------------

    async def emit_reasoning_delta(self, node_id: str, delta: str) -> None:
        """Push a reasoning summary text delta.

        Codex: ReasoningSummaryTextDelta → on_agent_reasoning_delta()
        - Frontend accumulates into reasoning_buffer
        - Frontend extracts first **bold** header for status bar (once, then cached)
        - summary_header is pre-extracted here as a hint, frontend may ignore if empty
        """
        import re
        bold_match = re.search(r'\*\*(.+?)\*\*', delta)
        summary_header = bold_match.group(1) if bold_match else ""
        await self._emit(node_id, "reasoning_summary_text_delta", {
            "delta": delta,
            "summary_header": summary_header,
            "item_id": node_id,
        })

    async def emit_agent_message_delta(self, node_id: str, delta: str) -> None:
        """Push an agent message text delta.

        Codex: AgentMessageDelta → on_agent_message_delta()
        - Goes through StreamController for line-by-line commit animation
        - Only the readable reply text, never raw JSON
        """
        import logging as _logging
        _logging.getLogger(__name__).info(f"[Observer] emit_agent_message_delta: node_id={node_id}, delta_len={len(delta)}, preview={delta[:60]!r}")
        await self._emit(node_id, "agent_message_delta", {
            "delta": delta,
            "item_id": node_id,
        })

    # ------------------------------------------------------------------
    # Phase 2: Completed events (finalize item, write to history)
    # ------------------------------------------------------------------

    async def emit_reasoning_completed(self, node_id: str, summary_parts: list[str]) -> None:
        """Push a reasoning item completion.

        Codex: ItemCompleted(ThreadItem::Reasoning) → on_agent_reasoning_final()
        - Takes the accumulated reasoning_buffer parts
        - Frontend creates a ReasoningSummaryCell (dim + italic, collapsible)
        - Adds to history, clears streaming state
        """
        await self._emit(node_id, "reasoning_completed", {
            "summary_parts": summary_parts,
            "item_id": node_id,
        })

    async def emit_agent_message_completed(self, node_id: str, text: str) -> None:
        """Push an agent message item completion.

        Codex: ItemCompleted(ThreadItem::AgentMessage) → on_agent_message_item_completed()
        - Takes the final message text
        - Frontend finalizes StreamController → AgentMarkdownCell
        - Consolidates streaming tail into permanent history
        """
        await self._emit(node_id, "agent_message_completed", {
            "text": text,
            "item_id": node_id,
        })

    # ------------------------------------------------------------------
    # Legacy: emit_llm_stream (kept for backward compat, delegates to new methods)
    # ------------------------------------------------------------------

    async def emit_llm_stream(self, node_id: str, chunk: dict[str, Any]) -> None:
        """Push an LLM streaming chunk (reasoning only, NOT content).

        Content (LLM formal output) contains structured JSON and must be
        parsed by loop.py, not streamed directly.
        """
        reasoning = chunk.get("reasoning_content", "")
        if reasoning:
            await self.emit_reasoning_delta(node_id, reasoning)

    # ------------------------------------------------------------------
    # Tool call events
    # ------------------------------------------------------------------

    async def emit_tool_call_start(
        self, node_id: str, tool_name: str, inputs: dict[str, Any]
    ) -> None:
        payload: dict[str, Any] = {"tool_name": tool_name, "inputs": inputs}
        if node_id.startswith("sub:"):
            payload["sub_agent_id"] = node_id[4:]
        import logging as _log
        _log.getLogger(__name__).info(
            f"[Observer] emit_tool_call_start: node={node_id}, tool={tool_name}, "
            f"sub_agent_id={payload.get('sub_agent_id', '')}, "
            f"has_callback={self._emit_callback is not None}"
        )
        await self._emit(
            node_id, "tool_call_start", payload
        )

    async def emit_tool_call_end(
        self, node_id: str, tool_name: str, success: bool, summary: str = "",
        result_data: Any = None,
    ) -> None:
        payload: dict[str, Any] = {
            "tool_name": tool_name,
            "success": success,
            "summary": summary,
        }
        if result_data is not None:
            payload["result_data"] = result_data
        if node_id.startswith("sub:"):
            payload["sub_agent_id"] = node_id[4:]
        import logging as _log
        _log.getLogger(__name__).info(
            f"[Observer] emit_tool_call_end: node={node_id}, tool={tool_name}, "
            f"success={success}, sub_agent_id={payload.get('sub_agent_id', '')}"
        )
        await self._emit(node_id, "tool_call_end", payload)

    # ------------------------------------------------------------------
    # Other trace events
    # ------------------------------------------------------------------

    async def emit_trace(self, node_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await self._emit(node_id, event_type, payload)

    async def emit_progress(
        self, node_id: str, current: int, total: int, label: str = ""
    ) -> None:
        await self._emit(
            node_id, "progress_update",
            {"current": current, "total": total, "label": label},
        )

    async def emit_model_switched(
        self, node_id: str, from_model: str, to_model: str
    ) -> None:
        await self._emit(
            node_id, "model_switched", {"from": from_model, "to": to_model}
        )

    async def emit_decision(self, node_id: str, decision_text: str) -> None:
        await self._emit(node_id, "decision_made", {"decision": decision_text})

    # ------------------------------------------------------------------
    # Recovery observation
    # ------------------------------------------------------------------

    async def log_attempt(
        self,
        node_id: str,
        attempt: int,
        strategy: str,
        adjusted: dict[str, Any] | None = None,
    ) -> None:
        await self._emit(
            node_id,
            "recovery_attempt",
            {
                "attempt": attempt,
                "strategy": strategy,
                "adjusted": adjusted or {},
            },
        )

    async def log_attempt_failed(
        self,
        node_id: str,
        attempt: int,
        strategy: str,
        error: str,
        error_type: str = "",
    ) -> None:
        await self._emit(
            node_id,
            "recovery_attempt_failed",
            {
                "attempt": attempt,
                "strategy": strategy,
                "error": error,
                "error_type": error_type,
            },
        )

    async def log_recovery_success(
        self,
        node_id: str,
        attempt: int,
        strategy: str,
    ) -> None:
        await self._emit(
            node_id,
            "recovery_success",
            {
                "attempt": attempt,
                "strategy": strategy,
            },
        )

    async def log_recovery_exhausted(
        self,
        node_id: str,
        attempts: int,
        last_error: str,
    ) -> None:
        await self._emit(
            node_id,
            "recovery_exhausted",
            {
                "attempts": attempts,
                "last_error": last_error,
            },
        )

    async def log_circuit_open(
        self,
        node_id: str,
        state: str,
    ) -> None:
        await self._emit(
            node_id,
            "circuit_open",
            {"state": state},
        )