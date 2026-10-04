"""Harness runtime entry point (Layer B).

Corresponds to architecture doc Ch.4.
Red line: harness must NOT import langgraph or fastapi.

Governance integration (ref: Codex core/session architecture):
  Codex separates "execution layer" (LLM + Tools + Loop) from "governance layer"
  (Queue + Budget + Compact). We follow the same pattern:
  - AgentHarness owns the governance instances
  - Executors check budget before/after each LLM call
  - LLM calls go through the request queue
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ValidationError

from app.engine.governance.context_compact import CompactConfig, ContextCompactor
from app.engine.governance.context_window import CompactScope, ContextWindowTracker
from app.engine.governance.guardian import Guardian
from app.engine.governance.hooks import HookRegistry, create_default_hooks
from app.engine.governance.request_queue import LLMRequestQueue, get_llm_queue
from app.engine.governance.stream_retry import StreamRetryState, RetryAction
from app.engine.governance.thread_store import ThreadStore, ThreadEventType
from app.engine.governance.time_reminder import TimeReminder
from app.engine.governance.token_budget import BudgetAction, TokenBudget, TokenBudgetConfig
from app.engine.collab.agent_manager import AgentManager, AgentHandle, AgentStatus, CollabMode
from app.engine.collab.message_bus import InterAgentBus
from app.engine.collab.concurrency_pool import ConcurrencyPool
from app.engine.collab.tools import CollaborationTools
from app.engine.harness.executor.base import ExecutorBase
from app.engine.harness.executor.loop import LoopExecutor
from app.engine.harness.executor.single_shot import SingleShotExecutor
from app.engine.harness.memory.memory import AgentMemory
from app.engine.harness.observer.observer import Observer
from app.engine.schemas import (
    AgentOutput,
    HardRule,
    LLMProtocol,
    NodeExecutionError,
    WorkflowContext,
)

if TYPE_CHECKING:
    from app.tools.base import Skill

logger = logging.getLogger(__name__)


class AgentHarness:
    """Agent runtime container.

    Each Agent = one AgentHarness instance + config.
    Orchestrates: pre-rules -> executor -> post-rules -> AgentOutput.

    Governance layer (ref: Codex Session):
      - token_budget: tracks token usage, triggers warnings/compaction
      - compactor: compresses conversation history when budget is exhausted
      - context_window: precise tracking of context window token status
      - llm_queue: rate-limited queue for LLM API calls
      - guardian: tool-call safety gate (policy -> confirm -> validate)
      - hooks: lifecycle callbacks for tool/LLM events
      - thread_store: event log with checkpoint/rollback support
      - time_reminder: periodic time-awareness injection into LLM context
      - stream_retry: intelligent retry for LLM stream calls
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
        token_budget_config: TokenBudgetConfig | None = None,
        compact_config: CompactConfig | None = None,
        llm_queue: LLMRequestQueue | None = None,
        guardian: Guardian | None = None,
        hooks: HookRegistry | None = None,
        thread_store: ThreadStore | None = None,
        context_window: ContextWindowTracker | None = None,
        time_reminder: TimeReminder | None = None,
        agent_manager: AgentManager | None = None,
        message_bus: InterAgentBus | None = None,
        concurrency_pool: ConcurrencyPool | None = None,
        collaboration_tools: CollaborationTools | None = None,
        max_concurrent_agents: int = 3,
        collab_mode: CollabMode = CollabMode.PROACTIVE,
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

        # Governance layer (ref: Codex Session's budget/compact/queue)
        self.token_budget = TokenBudget(token_budget_config)
        self.compactor = ContextCompactor(compact_config, self.token_budget)
        self.llm_queue = llm_queue or get_llm_queue()
        self.guardian = guardian or Guardian()
        self.hooks = hooks or create_default_hooks()
        self.thread_store = thread_store or ThreadStore()
        self.context_window = context_window or ContextWindowTracker(
            full_context_window=getattr(llm, "context_window", None) or 64000,
            scope=CompactScope.BODY_AFTER_PREFIX,
        )
        self.time_reminder = time_reminder or TimeReminder(interval_seconds=300)

        # Collaboration layer (ref: Codex multi_agents_v2)
        self.agent_manager = agent_manager or AgentManager(
            max_concurrent=max_concurrent_agents,
        )
        self.message_bus = message_bus or InterAgentBus()
        self.concurrency_pool = concurrency_pool or ConcurrencyPool(
            max_slots=max_concurrent_agents,
        )
        self.collaboration_tools = collaboration_tools or CollaborationTools(
            agent_manager=self.agent_manager,
            message_bus=self.message_bus,
            concurrency_pool=self.concurrency_pool,
        )

        # Register root agent
        self.agent_manager.register_root(agent_id, role=role)
        self.message_bus.register(agent_id)

        # Collaboration mode determines tool registration
        self.collab_mode = collab_mode
        if collab_mode != CollabMode.DISABLED:
            collab_names = {t.name for t in self.collaboration_tools.tools}
            existing_names = {s.name for s in self.skills}
            _added = []
            for tool in self.collaboration_tools.tools:
                if tool.name not in existing_names:
                    self.skills.append(tool)
                    _added.append(tool.name)
            logger.info(
                f"[harness] collab_mode={collab_mode.value}, "
                f"collab_tools_available={collab_names}, "
                f"already_in_skills={collab_names & existing_names}, "
                f"newly_added={_added}, "
                f"total_skills_after={len(self.skills)}"
            )
        else:
            logger.info(f"[harness] collab_mode=DISABLED, no collab tools registered")

        # Set sub-agent executor: uses this harness's LLM to run tasks
        self.agent_manager.set_executor(self._execute_sub_agent)

    _COLLAB_TOOL_NAMES = frozenset({
        "spawn_agent", "send_message", "wait_agent",
        "interrupt_agent", "list_agents",
    })

    def _build_sub_harness(
        self,
        agent_id: str,
        task_description: str,
        registered_agent_def: Any | None = None,
        model_override: str | None = None,
    ) -> AgentHarness:
        """构建子Agent的 AgentHarness，复用 LoopExecutor / SingleShotExecutor。

        核心原则：
        - 子Agent复用正式的 Executor（LoopExecutor 或 SingleShotExecutor），
          不再手搓 ReAct 循环
        - 子Agent不能递归 spawn（无协作工具）
        - 子Agent继承父Agent的非协作工具，若 AgentDef 指定了 skills 则以 AgentDef 为准
        - 支持模型覆盖（model_override 优先于 AgentDef.llm_model）
        - 共享父Agent的治理基础设施（llm_queue、guardian）
        """
        from app.agents.registry import AgentRegistry, _build_skills

        handle = self.agent_manager.get(agent_id)
        role_desc = handle.role if handle else "assistant"

        if registered_agent_def is not None:
            agent_def = registered_agent_def
            if model_override and agent_def.llm_model != model_override:
                agent_def = agent_def.model_copy(update={"llm_model": model_override})
        else:
            from app.agents.registry import AgentDef
            agent_def = AgentDef(
                agent_id=agent_id,
                role=role_desc or "sub-agent",
                llm_model=model_override,
                executor="loop",
                max_iterations=10,
                prompt_template="",
            )

        sub_llm = None
        if agent_def.llm_model:
            try:
                from app.engine.factory import get_deepseek_llm
                sub_llm = get_deepseek_llm(model=agent_def.llm_model)
            except Exception as e:
                logger.warning(f"[sub-harness] model init failed for {agent_def.llm_model}: {e}, using parent LLM")
                sub_llm = self.llm
        if sub_llm is None:
            sub_llm = self.llm

        executor = (
            LoopExecutor(max_iterations=agent_def.max_iterations)
            if agent_def.executor == "loop"
            else SingleShotExecutor()
        )

        if agent_def.skills is not None:
            sub_skills = _build_skills(agent_def.skills)
        else:
            sub_skills = [
                s for s in self.skills
                if s.name not in self._COLLAB_TOOL_NAMES
            ]

        system_prefix = ""
        if agent_def.prompt_template:
            system_prefix = agent_def.prompt_template
        elif registered_agent_def is not None and agent_def.description:
            system_prefix = (
                f"你是{agent_def.role}。\n"
                f"{agent_def.description}\n"
                f"请完成以下任务，直接输出结果。"
            )
        else:
            system_prefix = (
                f"You are a sub-agent (role: {role_desc or 'generalist'}). "
                f"You have the SAME tools and autonomy as your parent agent. "
                f"Read the tool descriptions carefully and decide which tools to use to complete your task. "
                f"You are not limited to a specific tool set — use ANY available tool that helps. "
                f"Think step by step, call tools as needed, and produce a clear result."
            )

        sub_observer = Observer()
        if self.observer and getattr(self.observer, "_emit_callback", None) is not None:
            sub_observer = Observer(emit_callback=self.observer._emit_callback)

        sub_harness = AgentHarness(
            agent_id=agent_id,
            role=agent_def.role or role_desc,
            llm=sub_llm,
            skills=sub_skills,
            memory=AgentMemory(),
            prompt_template=system_prefix,
            hard_rules=[],
            observer=sub_observer,
            executor=executor,
            collab_mode=CollabMode.DISABLED,
            llm_queue=self.llm_queue,
            guardian=self.guardian,
            max_concurrent_agents=0,
        )

        return sub_harness

    async def _execute_sub_agent(
        self, agent_id: str, task_description: str
    ) -> Any:
        """Execute a sub-agent task via _build_sub_harness + harness.run().

        子Agent复用正式的 LoopExecutor / SingleShotExecutor，
        不再手搓 ReAct 循环。子Agent不能递归 spawn（collab_mode=DISABLED）。

        Fork mode (ref: Claude Code):
          - fork: 子Agent继承父Agent的对话历史，适合需要上下文的任务
            （如审核已有文案、基于搜索结果写文案）
          - clean: 子Agent从干净状态开始，适合需要独立视角的任务
            （如并行搜索、独立审核）
        """
        if self.llm is None:
            return task_description

        handle = self.agent_manager.get(agent_id)
        registered_agent_def = getattr(handle, "_registered_agent_def", None) if handle else None
        model_override = handle.model_override if handle else None
        fork_mode = getattr(handle, "_fork_mode", "clean") if handle else "clean"

        sub_harness = self._build_sub_harness(
            agent_id=agent_id,
            task_description=task_description,
            registered_agent_def=registered_agent_def,
            model_override=model_override,
        )

        try:
            from app.engine.schemas import WorkflowContext
            ctx = WorkflowContext(
                workflow_id="",
                node_id=f"sub:{agent_id}",
                user_id="",
                account_id="",
            )

            input_data = {"topic": task_description}

            if fork_mode == "fork":
                parent_messages = self.thread_store.messages
                if parent_messages:
                    recent = parent_messages[-10:]
                    history_lines = []
                    for msg in recent:
                        role = msg.get("role", "")
                        content = msg.get("content", "")
                        if role in ("user", "assistant") and content:
                            label = "用户" if role == "user" else "助手"
                            history_lines.append(f"{label}：{content[:500]}")
                    if history_lines:
                        input_data["fork_context"] = (
                            "[父Agent对话历史 — 供你理解任务背景]\n"
                            + "\n".join(history_lines)
                        )

            output = await sub_harness.run(input_data, ctx)
            result = output.output if output else {}
            return result
        except Exception as e:
            logger.error(f"[sub-agent] harness.run failed for {agent_id}: {e}")
            return {"error": str(e)[:500], "agent_id": agent_id}
        finally:
            try:
                await sub_harness.shutdown()
            except Exception:
                pass

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

    async def shutdown(self) -> None:
        """Shutdown the harness: cancel sub-agents, release all resources.

        Called when the session ends. After shutdown, the harness
        should not be reused.
        """
        await self.agent_manager.shutdown()
        self.message_bus.shutdown()
        logger.info(
            f"[harness] shutdown complete for agent {self.agent_id}"
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
        from app.engine.schemas import PermissionDeniedError
        from app.tools.permissions import permission_gate

        for skill in self.skills:
            await self.observer.emit_tool_call_start(
                context.node_id, skill.name, llm_output
            )
            try:
                # 权限门控：被拒即记失败并抛出，由上层 NodeExecutionError 接管
                await permission_gate.require(skill.required_permissions, context)
                result = await skill.execute(llm_output)
                await self.observer.emit_tool_call_end(
                    context.node_id, skill.name, True, self._summarize(result),
                    result_data=self._safe_result_data(result),
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

    @staticmethod
    def _safe_result_data(result: Any, max_depth: int = 3) -> Any:
        """Extract JSON-safe result data for frontend structured rendering.

        Only passes through dicts/lists/primitives that are JSON-serializable.
        Skips non-serializable objects (LLM clients, DB sessions, etc.)
        to keep the SSE payload small and safe.
        """
        if result is None:
            return None
        if isinstance(result, (bool, int, float, str)):
            return result
        if isinstance(result, (list, tuple)):
            if len(result) > 50:
                return result[:50]
            return list(result)
        if isinstance(result, dict):
            try:
                import json
                json.dumps(result, default=str, ensure_ascii=False)
                return result
            except (TypeError, ValueError, OverflowError):
                return None
        return None

    def governance_stats(self) -> dict[str, Any]:
        """Collect governance layer stats for monitoring.

        Ref: Codex session.rs::status() — exposes session state
        for monitoring and debugging. We follow the same pattern:
        aggregate governance module stats into one snapshot.
        """
        return {
            "agent_id": self.agent_id,
            "role": self.role,
            "token_budget": {
                "total_tokens": self.token_budget.total_tokens,
                "remaining": self.token_budget.remaining_in_window(),
                "context_window": self.token_budget.config.context_window_tokens,
                "window_number": self.token_budget.window_number,
            },
            "context_window": self.context_window.to_dict(),
            "llm_queue": self.llm_queue.stats,
            "guardian": self.guardian.stats if hasattr(self.guardian, "stats") else {},
            "hooks": self.hooks.stats,
            "thread_store": {
                "thread_id": self.thread_store.thread_id,
                "event_count": len(self.thread_store._events),
                "checkpoint_count": len(self.thread_store._checkpoints),
            },
            "time_reminder": self.time_reminder.stats,
            "collaboration": {
                "agent_manager": self.agent_manager.stats,
                "message_bus": self.message_bus.stats,
                "concurrency_pool": self.concurrency_pool.stats,
                "collab_mode": self.collab_mode.value,
            },
        }