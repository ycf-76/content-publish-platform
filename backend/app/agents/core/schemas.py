"""Core schema definitions shared across Harness and LangGraph layers.

Red line: Harness layer only reads input, writes output.
It must NOT manipulate LangGraph state directly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field


@runtime_checkable
class LLMProtocol(Protocol):
    """Interface that model adapters must satisfy.

    Phase 3 implements DeepSeekAdapter, QwenVLAdapter, etc.
    The Harness/Executor depends only on this protocol, never on concrete adapters.
    """

    model_name: str

    async def chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat.

        Returns: {"content": str, "reasoning_content": str | None, "token_usage": int}
        """
        ...

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming chat.

        Yields: {"content": str | None, "reasoning_content": str | None,
                "is_final": bool, "token_usage": int | None}
        """
        ...


class WorkflowContext(BaseModel):
    """Context passed to every Agent harness execution.

    D7: only task-internal context, no cross-task memory.
    """

    workflow_id: str
    node_id: str
    user_id: str
    account_id: str
    topic: str = ""
    upstream_outputs: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    """Standardized output from AgentHarness.run()."""

    output: dict[str, Any]
    quality_report: dict[str, Any] | None = None
    token_usage: int = 0
    duration_ms: int = 0
    model_used: str | None = None


class HardRule(ABC):
    """Abstract hard rule (guard).

    Pre-check runs before executor; post-check runs after schema validation.
    Both must pass for the node to succeed.
    """

    name: str = ""

    @abstractmethod
    async def check_pre(self, input: dict[str, Any], context: WorkflowContext) -> bool:
        """Validate input before execution. Return False to block."""
        ...

    @abstractmethod
    async def check_post(self, output: dict[str, Any], context: WorkflowContext) -> bool:
        """Validate output after execution. Return False to block."""
        ...


class NodeExecutionError(Exception):
    """Raised when a node fails execution."""

    def __init__(self, node_id: str, crash_reason: str, message: str = ""):
        self.node_id = node_id
        self.crash_reason = crash_reason
        self.message = message
        super().__init__(f"[{node_id}] {crash_reason}: {message}")


class RecoveryExhaustedError(Exception):
    """Raised when all recovery strategies are exhausted (Phase 6)."""

    def __init__(self, node_id: str, attempts: int, last_error: str = ""):
        self.node_id = node_id
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"[{node_id}] recovery exhausted after {attempts} attempts: {last_error}"
        )
