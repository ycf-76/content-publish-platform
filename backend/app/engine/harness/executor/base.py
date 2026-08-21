"""Executor abstract base class.

Corresponds to architecture doc 4.3. Phase 2 implements SingleShotExecutor.
Red line: currently only single_shot, no ReAct.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.engine.harness.runtime import AgentHarness
    from app.engine.schemas import WorkflowContext


class ExecutorBase(ABC):
    """Executor interface: defines how an Agent runs (single-shot / ReAct / ...)."""

    @abstractmethod
    async def execute(
        self,
        harness: AgentHarness,
        input: dict[str, Any],
        context: WorkflowContext,
    ) -> dict[str, Any]:
        """Execute the agent's single run, return raw output dict."""
        raise NotImplementedError
