"""Harness runtime entry point (Layer B).

Corresponds to architecture doc Ch.4.
Red line: harness must NOT import langgraph or fastapi.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from app.agents.core.harness.executor.base import ExecutorBase
from app.agents.core.harness.executor.single_shot import SingleShotExecutor
from app.agents.core.harness.memory.memory import AgentMemory
from app.agents.core.harness.observer.observer import Observer
from app.agents.core.schemas import (
    AgentOutput,
    HardRule,
    LLMProtocol,
    NodeExecutionError,
    WorkflowContext,
)

if TYPE_CHECKING:
    from app.agents.skills.base import Skill

logger = logging.getLogger(__name__)


class AgentHarness:
    """Agent runtime container.

    Each Agent = one AgentHarness instance + config.
    Orchestrates: pre-rules -> executor -> post-rules -> AgentOutput.
    """

    def __init__(
        self,
        agent_id: str,
        role: str,
        llm: LLMProtocol | None = None,
        skills: list[Skill] | None = None,
        memory: AgentMemory | None = None,
        prompt_template: str = "",
        output_schema: type[BaseModel] | None = None,
        hard_rules: list[HardRule] | None = None,
        observer: Observer | None = None,
        executor: ExecutorBase | None = None,
        recovery_loop: Any | None = None,
        soft_semantic: Any | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.role = role
        self.llm = llm
        self.skills = skills or []
        self.memory = memory or AgentMemory()
        self.prompt_template = prompt_template
        self.output_schema = output_schema
        self.hard_rules = hard_rules or []
        self.observer = observer or Observer()
        self.executor = executor or SingleShotExecutor()
        self.recovery_loop = recovery_loop
        self.soft_semantic = soft_semantic

    async def run(
        self, input: dict[str, Any], context: WorkflowContext
    ) -> AgentOutput:
        """Standard execution flow:
        1. Pre hard-rule guards
        2. Delegate to executor (recovery_loop wraps if available, Phase 6)
        3. Post hard-rule guards (schema validation)
        4. Return AgentOutput
        """
        for rule in self.hard_rules:
            passed = await rule.check_pre(input, context)
            if not passed:
                raise NodeExecutionError(
                    context.node_id,
                    "pre_check_failed",
                    f"Pre-check failed: {rule.name}",
                )

        start = time.monotonic()
        try:
            if self.recovery_loop is not None:
                raw_output = await self.recovery_loop.execute_with_recovery(
                    agent=self,
                    input=input,
                    context=context,
                    execute_fn=lambda inp, ctx: self.executor.execute(self, inp, ctx),
                )
            else:
                raw_output = await self.executor.execute(self, input, context)
        except NodeExecutionError:
            raise
        except Exception as e:
            raise NodeExecutionError(
                context.node_id, "execution_error", str(e)
            ) from e

        duration_ms = int((time.monotonic() - start) * 1000)

        if self.output_schema is not None:
            try:
                validated = self.output_schema.model_validate(raw_output)
            except ValidationError as e:
                raise NodeExecutionError(
                    context.node_id, "schema_validation_failed", str(e)
                ) from e
            output_data = validated.model_dump()
        else:
            output_data = raw_output

        for rule in self.hard_rules:
            passed = await rule.check_post(output_data, context)
            if not passed:
                raise NodeExecutionError(
                    context.node_id,
                    "post_check_failed",
                    f"Post-check failed: {rule.name}",
                )

        token_usage = raw_output.get("_token_usage", 0)
        model_used = self.llm.model_name if self.llm else None

        return AgentOutput(
            output=output_data,
            quality_report=None,
            token_usage=token_usage,
            duration_ms=duration_ms,
            model_used=model_used,
        )

    async def _execute_with_skills(
        self, llm_output: dict[str, Any], context: WorkflowContext
    ) -> dict[str, Any]:
        """Call registered skills and merge results into output.

        Called by SingleShotExecutor after LLM produces output.
        Emits tool_call_start/end events via observer.
        每次调用前必须经过 permission_gate（与 LoopExecutor 行为一致）。
        """
        # 局部导入避免循环依赖：harness 不能在模块顶层依赖 skills
        from app.agents.core.schemas import PermissionDeniedError
        from app.agents.skills.permissions import permission_gate

        for skill in self.skills:
            await self.observer.emit_tool_call_start(
                context.node_id, skill.name, llm_output
            )
            try:
                # 权限门控：被拒即记失败并抛出，由上层 NodeExecutionError 接管
                await permission_gate.require(skill.required_permissions, context)
                result = await skill.execute(llm_output)
                await self.observer.emit_tool_call_end(
                    context.node_id, skill.name, True, self._summarize(result)
                )
                llm_output[skill.name] = result
            except PermissionDeniedError as e:
                await self.observer.emit_tool_call_end(
                    context.node_id, skill.name, False, f"permission denied: {e.permission.value}"
                )
                raise NodeExecutionError(
                    context.node_id,
                    "permission_denied",
                    f"Skill {skill.name} requires {e.permission.value}",
                ) from e
            except NodeExecutionError:
                raise
            except Exception as e:
                await self.observer.emit_tool_call_end(
                    context.node_id, skill.name, False, str(e)
                )
                raise
        return llm_output

    @staticmethod
    def _summarize(result: Any, max_len: int = 200) -> str:
        """Short summary of skill result for trace events."""
        text = str(result)
        return text[:max_len] if len(text) > max_len else text