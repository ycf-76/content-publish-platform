"""Observer layer (D16 process transparency).

Pushes trace events via dependency-injected callbacks.
Red line: must NOT import SSE or FastAPI directly.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

EmitCallback = Callable[[str, str, dict[str, Any]], Awaitable[None]]


async def _noop(node_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Default no-op callback when none is injected."""
    pass


class Observer:
    """D16 observation layer.

    Emits 7 trace event types via a dependency-injected callback.
    The SSE layer (Phase 5) injects a real callback; defaults to no-op.
    """

    def __init__(self, emit_callback: EmitCallback | None = None):
        self._emit = emit_callback or _noop

    async def emit_trace(self, node_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Push a generic trace event."""
        await self._emit(node_id, event_type, payload)

    async def emit_llm_stream(self, node_id: str, chunk: dict[str, Any]) -> None:
        """Push an LLM streaming chunk (reasoning_content -> agent_thinking)."""
        await self._emit(node_id, "agent_thinking", {"chunk": chunk})

    async def emit_tool_call_start(
        self, node_id: str, tool_name: str, inputs: dict[str, Any]
    ) -> None:
        """Push a tool_call_start event."""
        await self._emit(
            node_id, "tool_call_start", {"tool_name": tool_name, "inputs": inputs}
        )

    async def emit_tool_call_end(
        self, node_id: str, tool_name: str, success: bool, summary: str = ""
    ) -> None:
        """Push a tool_call_end event."""
        await self._emit(
            node_id,
            "tool_call_end",
            {"tool_name": tool_name, "success": success, "summary": summary},
        )

    async def emit_progress(
        self, node_id: str, current: int, total: int, label: str = ""
    ) -> None:
        """Push a progress_update event."""
        await self._emit(
            node_id, "progress_update",
            {"current": current, "total": total, "label": label},
        )

    async def emit_model_switched(
        self, node_id: str, from_model: str, to_model: str
    ) -> None:
        """Push a model_switched event."""
        await self._emit(
            node_id, "model_switched", {"from": from_model, "to": to_model}
        )

    async def emit_decision(self, node_id: str, decision_text: str) -> None:
        """Push a decision_made event."""
        await self._emit(node_id, "decision_made", {"decision": decision_text})

    # ------------------------------------------------------------------
    # Recovery 观测（项目书 4.8 要求的 log_attempt / log_attempt_failed）
    # RecoveryLoop 通过这两个方法记录每次 attempt 的策略、调整和结果
    # 与通用的 emit_trace 相比，这两个方法有明确的语义和字段约定
    # ------------------------------------------------------------------

    async def log_attempt(
        self,
        node_id: str,
        attempt: int,
        strategy: str,
        adjusted: dict[str, Any] | None = None,
    ) -> None:
        """记录一次 recovery attempt 开始。

        参数:
            node_id: 节点 ID
            attempt: 第几次尝试（从 0 开始）
            strategy: 策略名（retry / broaden_keyword / switch_model 等）
            adjusted: 调整后的输入摘要（用于追踪策略如何修改了输入）
        """
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
        """记录一次 recovery attempt 失败。

        参数:
            node_id: 节点 ID
            attempt: 第几次尝试（从 0 开始）
            strategy: 策略名
            error: 错误消息
            error_type: 错误类型名（如 NodeExecutionError / TimeoutError）
        """
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
        """记录 recovery 最终成功（在第 N 次尝试后成功）。"""
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
        """记录 recovery 所有策略耗尽，最终失败。"""
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
        """记录熔断器开启，请求被拒绝。"""
        await self._emit(
            node_id,
            "circuit_open",
            {"state": state},
        )
