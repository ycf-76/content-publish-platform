"""Collaboration Tools: LLM-callable tools for multi-agent coordination.

Ref: Codex multi_agents_v2 tool surface:
  - spawn_agent: create a new sub-agent with a task
  - send_message: send a message to another agent
  - wait_agent: wait for an agent to complete
  - interrupt_agent: stop a running agent
  - list_agents: list all active agents
  - followup_task: send a follow-up task to a completed agent

Our adaptation:
  - Tools are registered as Skills in the existing tool registry
  - Each tool delegates to AgentManager / InterAgentBus
  - Tool results are JSON-serializable for LLM consumption
  - Concurrency limits enforced at tool level
"""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.engine.collab.agent_manager import AgentManager, AgentHandle, AgentStatus
from app.engine.collab.message_bus import InterAgentBus, AgentMessage, MessageType
from app.engine.collab.concurrency_pool import ConcurrencyPool
from app.tools.base import Skill

logger = logging.getLogger(__name__)


class SpawnAgentInput(BaseModel):
    task_name: str = Field(description="Short name for the sub-agent task, e.g. 'research_ai_trends'")
    task_description: str = Field(description="Detailed description of what the sub-agent should do. Be specific about the goal, expected output format, and any constraints. The sub-agent will autonomously decide which tools to use.")
    role: str | None = Field(default=None, description="Optional role description for the sub-agent (e.g. 'researcher', 'auditor', 'writer'). This sets the sub-agent's system prompt persona but does NOT limit its tools — it inherits ALL parent tools and decides which to use autonomously.")
    agent_id: str | None = Field(default=None, description="OPTIONAL: reference a pre-registered specialist (e.g. 'search', 'audit') for a pre-configured skill set and prompt. When omitted, the sub-agent is a generalist that inherits ALL parent tools — this is the DEFAULT and preferred mode (ref: Codex/Claude Code). Use agent_id only when you want a specialist with a curated skill set instead of the full toolkit.")
    model: str | None = Field(default=None, description="Optional LLM model override (e.g. 'deepseek-r1' for reasoning, 'deepseek-v3' for speed). When omitted, inherits parent model.")
    fork_mode: str = Field(
        default="clean",
        description=(
            "Context strategy for the sub-agent. "
            "'fork' = inherit parent conversation history (use when sub-agent needs context "
            "about what was discussed/done before, e.g. reviewing work-in-progress). "
            "'clean' = start from scratch (use when sub-agent needs independent/fresh perspective, "
            "e.g. parallel search, audit, or creative tasks). "
            "Default: 'clean'."
        ),
    )


class SendMessageInput(BaseModel):
    target_agent_id: str = Field(description="ID of the agent to send the message to")
    content: str = Field(description="Message content to send")


class WaitAgentInput(BaseModel):
    agent_id: str = Field(description="ID of the agent to wait for")
    timeout_seconds: float = Field(default=30.0, description="Maximum time to wait in seconds")


class InterruptAgentInput(BaseModel):
    agent_id: str = Field(description="ID of the agent to interrupt")


class ListAgentsInput(BaseModel):
    pass


def _build_spawn_description() -> str:
    """生成 spawn_agent 的 description。

    核心哲学 (ref: Codex / Claude Code):
      - 子 Agent 是"另一个自己"，不是"某个专家"
      - 默认模式：不传 agent_id → 子 Agent 继承全量工具，自主决策
      - 专家模式：传 agent_id → 用预配置的 skill 子集 + prompt（快捷方式，非唯一路径）
      - LLM 决定"做什么任务"，子 Agent 自己决定"用什么工具"
      - 三个 spawn 信号：Context Gathering / Multiple Independent Tasks / Fresh Perspective
    """
    try:
        from app.agents.registry import BUILTIN_AGENTS
        skip_ids = {"chat_agent"}
        agent_lines = []
        for aid, adef in BUILTIN_AGENTS.items():
            if aid in skip_ids:
                continue
            desc = adef.description or adef.role or ""
            agent_lines.append(f"  - {aid}: {desc}")
        agents_block = "\n".join(agent_lines)
    except Exception:
        agents_block = "  (agent registry unavailable)"
    return (
        "Spawn a sub-agent to handle a sub-task independently.\n\n"
        "CORE MODEL (ref: Codex / Claude Code):\n"
        "The sub-agent is ANOTHER INSTANCE OF YOU — it has the same tools and autonomy.\n"
        "You define WHAT to do (task_description), the sub-agent decides HOW to do it (which tools to use).\n"
        "This is the default mode: omit agent_id, and the sub-agent inherits ALL your tools.\n\n"
        "WHEN to spawn (3 signals):\n"
        "1. Context Gathering: You need information before you can proceed.\n"
        "   Example: User asks to write copy about a topic you haven't researched → "
        "spawn_agent(task_description='Search 小红书 for AI穿搭 trends and summarize top 5 posts')\n"
        "2. Multiple Independent Tasks: The request contains 2+ steps that don't depend on each other.\n"
        "   Example: 'Search trends AND write copy' → spawn both in parallel, wait_agent each.\n"
        "3. Fresh Perspective: You need a different viewpoint to review/improve your work.\n"
        "   Example: After writing copy → spawn_agent(role='auditor', fork_mode='fork', "
        "task_description='Review this copy for compliance and quality')\n\n"
        "WHEN NOT to spawn:\n"
        "- Single-step task you can handle directly with a tool (e.g. just 'search AI trends' → use trending_search directly).\n"
        "- Sequential dependency where sub-task B needs sub-task A's output (do A first, then B yourself).\n\n"
        "TASK DESCRIPTION BEST PRACTICES:\n"
        "- Be specific: 'Search 小红书 for 穿搭 trends, find top 5 posts, extract their titles and engagement metrics'\n"
        "  NOT: 'search trends'\n"
        "- Specify output format: '...return results as a JSON array with fields: title, likes, comments'\n"
        "- Include constraints: '...focus on posts from the last 7 days, skip sponsored content'\n\n"
        "FORK MODE (context strategy for sub-agent):\n"
        "- clean (default): Sub-agent starts from scratch. Use for independent tasks (parallel search, fresh audit).\n"
        "- fork: Sub-agent inherits parent conversation history. Use when it needs context about prior work "
        "(e.g. reviewing work-in-progress, building on search results you already have).\n\n"
        "SPECIALIST SHORTCUTS (optional agent_id):\n"
        "When you pass agent_id, the sub-agent uses a pre-configured skill subset and prompt instead of the full toolkit.\n"
        "This is a convenience — you can always achieve the same result without agent_id by describing the task clearly.\n"
        f"Available specialists:\n{agents_block}\n\n"
        "Usage pattern: spawn_agent → wait_agent to collect result. "
        "For parallel tasks, spawn all first, then wait each.\n"
        "model param overrides LLM (e.g. deepseek-r1 for reasoning-heavy tasks, deepseek-v3 for speed)."
    )


class SpawnAgentSkill(Skill):
    """Spawn a new sub-agent to work on a task in parallel.

    Ref: Codex spawn_agent tool — creates a child thread with:
      - A task description (message)
      - Optional role override
      - Fork mode (full history vs clean slate)
      - Model/reasoning overrides

    Our adaptation:
      - Spawns a new AgentHandle via AgentManager
      - Acquires a concurrency slot
      - Returns the agent_id for future reference
      - description dynamically lists available agents for LLM routing
    """

    name = "spawn_agent"
    description = _build_spawn_description()
    input_schema = SpawnAgentInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        manager: AgentManager | None = params.get("_agent_manager")
        pool: ConcurrencyPool | None = params.get("_concurrency_pool")
        bus: InterAgentBus | None = params.get("_message_bus")
        parent_id: str | None = params.get("_caller_agent_id")
        observer: Any | None = params.get("_observer")
        ctx = params.get("_context")
        node_id: str = ""
        if ctx:
            node_id = getattr(ctx, "node_id", "") if not isinstance(ctx, dict) else ctx.get("node_id", "")

        if not all([manager, pool, bus, parent_id]):
            return {"error": "collaboration infrastructure not available"}

        task_name = params.get("task_name", "unnamed_task")
        task_description = params.get("task_description", "")
        role = params.get("role")
        ref_agent_id = params.get("agent_id")
        model_override = params.get("model")
        fork_mode = params.get("fork_mode", "clean")

        try:
            handle = await manager.spawn(
                name=task_name,
                parent_id=parent_id,
                role=role,
                task_description=task_description,
            )
        except ValueError as e:
            return {"error": str(e)}

        acquired = await pool.acquire(handle.agent_id, timeout=5.0)
        if not acquired:
            manager.interrupt(handle.agent_id)
            return {"error": "concurrency pool full, try again later"}

        bus.register(handle.agent_id)

        if task_description:
            await bus.send(AgentMessage(
                message_type=MessageType.TASK,
                sender_id=parent_id,
                recipient_id=handle.agent_id,
                content=task_description,
                trigger_turn=True,
            ))

        use_registered = False
        registered_agent_def = None
        if ref_agent_id:
            try:
                from app.agents.registry import AgentRegistry
                registry = AgentRegistry()
                registered_agent_def = registry.get(ref_agent_id)
                if registered_agent_def is not None:
                    use_registered = True
                    if not role:
                        handle.role = registered_agent_def.role
                    logger.info(
                        f"[spawn_agent] using registered agent def: "
                        f"{ref_agent_id} (skills={registered_agent_def.skills}, "
                        f"model={registered_agent_def.llm_model})"
                    )
                else:
                    logger.warning(f"[spawn_agent] agent_id '{ref_agent_id}' not found in registry, using default")
            except Exception as e:
                logger.warning(f"[spawn_agent] failed to lookup agent '{ref_agent_id}': {e}")

        manager.start_sub_agent(
            agent_id=handle.agent_id,
            task_description=task_description,
            bus=bus,
            observer=observer,
            node_id=node_id,
            concurrency_pool=pool,
            registered_agent_def=registered_agent_def if use_registered else None,
            model_override=model_override,
            fork_mode=fork_mode,
        )

        result = {
            "success": True,
            "agent_id": handle.agent_id,
            "name": handle.name,
            "path": str(handle.agent_path),
            "parent_id": parent_id or "",
            "depth": (handle.depth if hasattr(handle, 'depth') else 1),
            "role": role or handle.role or None,
            "status": handle.status.value,
            "message": f"Sub-agent '{task_name}' spawned with id {handle.agent_id}",
        }
        if use_registered:
            result["registered_as"] = ref_agent_id
            result["skills"] = registered_agent_def.skills if registered_agent_def else []
        if model_override:
            result["model"] = model_override
        if fork_mode and fork_mode != "clean":
            result["fork_mode"] = fork_mode
        return result


class SendMessageSkill(Skill):
    """Send a message to another agent.

    Ref: Codex send_message tool — enqueues a message to the
    target agent's inbox. The message can optionally trigger
    a new turn in the recipient.
    """

    name = "send_message"
    description = "Send a message to another agent by agent_id."
    input_schema = SendMessageInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        bus: InterAgentBus | None = params.get("_message_bus")
        sender_id: str | None = params.get("_caller_agent_id")

        if not bus or not sender_id:
            return {"error": "message bus not available"}

        target_id = params.get("target_agent_id", "")
        message = params.get("content", "")
        trigger_turn = params.get("trigger_turn", False)

        if not target_id or not message:
            return {"error": "target_agent_id and content are required"}

        await bus.send(AgentMessage(
            message_type=MessageType.MESSAGE,
            sender_id=sender_id,
            recipient_id=target_id,
            content=message,
            trigger_turn=trigger_turn,
        ))

        return {
            "success": True,
            "delivered": True,
            "target": target_id,
            "pending_in_target": bus.pending_count(target_id),
        }


class WaitAgentSkill(Skill):
    """Wait for an agent to complete, with optional timeout.

    Ref: Claude Code wait_agent tool — blocks until the target agent
    finishes or the timeout expires. Returns the agent's final status
    and structured result (not truncated string).

    Default timeout: 30s. Min: 5s. Max: 300s.
    """

    name = "wait_agent"
    description = (
        "Wait for a sub-agent to complete and return its result. "
        "Use after spawn_agent to collect the sub-agent's output. "
        "For parallel tasks: spawn all first, then wait each one. "
        "Returns structured result (dict) when available, not just a string."
    )
    input_schema = WaitAgentInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        manager: AgentManager | None = params.get("_agent_manager")
        bus: InterAgentBus | None = params.get("_message_bus")

        if not manager:
            return {"error": "agent manager not available"}

        target_id = params.get("agent_id", "")
        timeout_seconds = params.get("timeout_seconds", 30.0)
        timeout_s = max(5.0, min(300.0, float(timeout_seconds)))

        handle = manager.get(target_id)
        if not handle:
            return {"error": f"agent {target_id} not found"}

        final_status = await handle.wait(timeout=timeout_s)

        result: dict[str, Any] = {
            "success": True,
            "agent_id": target_id,
            "status": final_status.value,
        }
        if handle.result is not None:
            if isinstance(handle.result, dict):
                result["result"] = handle.result
            else:
                result["result"] = str(handle.result)[:4000]
        if handle.error:
            result["error"] = handle.error

        return result


class InterruptAgentSkill(Skill):
    """Interrupt a running agent.

    Ref: Codex interrupt_agent tool — signals the target agent
    to stop execution. The agent's status becomes 'interrupted'.
    """

    name = "interrupt_agent"
    description = "Interrupt a running agent by agent_id."
    input_schema = InterruptAgentInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        manager: AgentManager | None = params.get("_agent_manager")
        pool: ConcurrencyPool | None = params.get("_concurrency_pool")

        if not manager:
            return {"error": "agent manager not available"}

        target_id = params.get("agent_id", "")

        interrupted = manager.interrupt(target_id)
        if interrupted and pool:
            pool.release(target_id)

        return {
            "success": interrupted,
            "agent_id": target_id,
            "interrupted": interrupted,
        }


class ListAgentsSkill(Skill):
    """List all active agents in the session.

    Ref: Codex list_agents tool — returns all agents visible
    to the caller, with their status and path information.
    """

    name = "list_agents"
    description = "List all agents in the current session."
    input_schema = ListAgentsInput

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        manager: AgentManager | None = params.get("_agent_manager")

        if not manager:
            return {"error": "agent manager not available"}

        path_prefix = params.get("path_prefix")
        agents = manager.list_agents(path_prefix=path_prefix)

        return {
            "success": True,
            "agents": [a.to_dict() for a in agents],
            "total": len(agents),
            "active": sum(
                1 for a in agents
                if a.status in (AgentStatus.RUNNING, AgentStatus.PENDING)
            ),
        }


class CollaborationTools:
    """Registry of all collaboration tools.

    Ref: Codex's tool registry — the collaboration tools are
    registered as a namespace (multi_agent_v1 / multi_agent_v2)
    and made available to the LLM based on the session config.

    Our adaptation:
      - CollaborationTools holds references to AgentManager,
        InterAgentBus, and ConcurrencyPool
      - Provides a list of Skill instances for tool registration
      - Injects infrastructure references into tool params
    """

    def __init__(
        self,
        agent_manager: AgentManager,
        message_bus: InterAgentBus,
        concurrency_pool: ConcurrencyPool,
    ) -> None:
        self.agent_manager = agent_manager
        self.message_bus = message_bus
        self.concurrency_pool = concurrency_pool
        self._tools: list[Skill] = [
            SpawnAgentSkill(),
            SendMessageSkill(),
            WaitAgentSkill(),
            InterruptAgentSkill(),
            ListAgentsSkill(),
        ]

    @property
    def tools(self) -> list[Skill]:
        return self._tools

    def inject_params(self, params: dict[str, Any], caller_agent_id: str) -> dict[str, Any]:
        """Inject collaboration infrastructure references into tool params."""
        params["_agent_manager"] = self.agent_manager
        params["_message_bus"] = self.message_bus
        params["_concurrency_pool"] = self.concurrency_pool
        params["_caller_agent_id"] = caller_agent_id
        return params

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "agent_manager": self.agent_manager.stats,
            "message_bus": self.message_bus.stats,
            "concurrency_pool": self.concurrency_pool.stats,
        }