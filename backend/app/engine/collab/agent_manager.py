"""Agent Manager: central registry for spawned sub-agents.

Ref: Codex session/multi_agents.rs — the session holds a thread manager
that tracks all spawned child threads. Each child has:
  - A unique thread_id
  - A parent_thread_id
  - A depth (how many levels deep in the spawn tree)
  - An agent_path (hierarchical name like /root/research/writer)
  - A status (running/completed/error/interrupted)

Our adaptation:
  - AgentManager is a singleton per workflow session
  - AgentHandle is a lightweight reference (not the full AgentHarness)
  - Status tracking via asyncio.Event for completion signaling
  - Agent path tree for hierarchical naming
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ERROR = "error"
    INTERRUPTED = "interrupted"


class CollabMode(str, Enum):
    """Multi-agent collaboration mode.

    Ref: Claude Code design philosophy:
      - The LLM decides when to spawn sub-agents in the ReAct loop.
      - Code provides tools + guardrails, NOT decisions.
      - Three spawn signals the model recognizes:
        1. Context Gathering — need info before proceeding
        2. Multiple Independent Tasks — parallel sub-tasks
        3. Fresh Perspective — different viewpoint for review

    Modes:
      - proactive (default): spawn_agent tool is available, model decides
        when to use it based on task complexity and tool descriptions.
        This is the Claude Code way — trust the model.
      - explicit: spawn_agent tool is available but prompt says
        "only use when user explicitly asks for parallel work".
        Use this for conservative deployments.
      - disabled: spawn_agent tool is hidden from skill_map entirely.
    """
    EXPLICIT = "explicit"
    PROACTIVE = "proactive"
    DISABLED = "disabled"


@dataclass
class AgentPath:
    """Hierarchical agent path, ref: Codex AgentPath.

    Represents the spawn tree: /root/research/writer
    """
    segments: list[str] = field(default_factory=lambda: ["root"])

    def join(self, child_name: str) -> AgentPath:
        return AgentPath(segments=self.segments + [child_name])

    def __str__(self) -> str:
        return "/".join(self.segments)

    @classmethod
    def root(cls) -> AgentPath:
        return cls(segments=["root"])

    @property
    def depth(self) -> int:
        return len(self.segments) - 1


@dataclass
class AgentHandle:
    """Lightweight reference to a spawned sub-agent.

    Ref: Codex ThreadId + agent control — the parent doesn't hold
    the full agent state, just a handle to query status and
    send messages.
    """
    agent_id: str
    name: str
    agent_path: AgentPath
    parent_id: str | None
    depth: int
    role: str | None = None
    model_override: str | None = None
    status: AgentStatus = AgentStatus.PENDING
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    result: Any = None
    error: str | None = None
    _completion_event: asyncio.Event = field(
        default_factory=asyncio.Event, repr=False
    )

    def mark_running(self) -> None:
        self.status = AgentStatus.RUNNING

    def mark_completed(self, result: Any = None) -> None:
        self.status = AgentStatus.COMPLETED
        self.result = result
        self.completed_at = time.time()
        self._completion_event.set()

    def mark_error(self, error: str) -> None:
        self.status = AgentStatus.ERROR
        self.error = error
        self.completed_at = time.time()
        self._completion_event.set()

    def mark_interrupted(self) -> None:
        self.status = AgentStatus.INTERRUPTED
        self.completed_at = time.time()
        self._completion_event.set()

    async def wait(self, timeout: float | None = None) -> AgentStatus:
        """Wait for the agent to complete.

        Ref: Codex wait_agent tool — blocks until the target agent
        finishes or times out.
        """
        try:
            await asyncio.wait_for(self._completion_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            pass
        return self.status

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "path": str(self.agent_path),
            "parent_id": self.parent_id,
            "depth": self.depth,
            "role": self.role,
            "status": self.status.value,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error": self.error,
        }


class AgentManager:
    """Central registry for spawned sub-agents.

    Ref: Codex's thread manager + agent_control:
      - Tracks all spawned agents in a session
      - Enforces max concurrency limits
      - Provides agent lookup by id or path prefix
      - Supports interrupt/kill operations

    Our adaptation:
      - Singleton per workflow session
      - asyncio-based concurrency control
      - Agent path tree for hierarchical naming
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        max_depth: int = 3,
    ) -> None:
        self._agents: dict[str, AgentHandle] = {}
        self._max_concurrent = max_concurrent
        self._max_depth = max_depth
        self._root_id: str | None = None
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._agent_executor: Any = None

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    def register_root(self, agent_id: str, role: str | None = None) -> AgentHandle:
        """Register the root agent (the main session agent)."""
        handle = AgentHandle(
            agent_id=agent_id,
            name="root",
            agent_path=AgentPath.root(),
            parent_id=None,
            depth=0,
            role=role,
        )
        handle.mark_running()
        self._agents[agent_id] = handle
        self._root_id = agent_id
        logger.info(f"[agent-manager] root agent registered: {agent_id}")
        return handle

    async def spawn(
        self,
        name: str,
        parent_id: str,
        role: str | None = None,
        task_description: str | None = None,
    ) -> AgentHandle:
        """Spawn a new sub-agent.

        Ref: Codex spawn_agent tool — creates a new thread with:
          - A unique thread_id
          - Parent reference
          - Depth tracking
          - Agent path derived from parent path + task name

        Returns:
            AgentHandle for the new sub-agent.
        Raises:
            ValueError if max concurrency or depth exceeded.
        """
        parent = self._agents.get(parent_id)
        if parent is None:
            raise ValueError(f"Parent agent {parent_id} not found")

        if parent.depth >= self._max_depth:
            raise ValueError(
                f"Max spawn depth ({self._max_depth}) exceeded. "
                f"Cannot spawn at depth {parent.depth + 1}."
            )

        active_count = sum(
            1 for h in self._agents.values()
            if h.status in (AgentStatus.RUNNING, AgentStatus.PENDING)
        )
        if active_count >= self._max_concurrent:
            raise ValueError(
                f"Max concurrent agents ({self._max_concurrent}) reached. "
                f"Wait for an agent to complete before spawning."
            )

        agent_id = uuid.uuid4().hex[:12]
        child_path = parent.agent_path.join(name)
        handle = AgentHandle(
            agent_id=agent_id,
            name=name,
            agent_path=child_path,
            parent_id=parent_id,
            depth=parent.depth + 1,
            role=role,
        )

        self._agents[agent_id] = handle
        logger.info(
            f"[agent-manager] spawned: {agent_id} name={name} "
            f"path={child_path} parent={parent_id} depth={handle.depth}"
        )
        return handle

    def get(self, agent_id: str) -> AgentHandle | None:
        return self._agents.get(agent_id)

    def list_agents(
        self,
        path_prefix: str | None = None,
    ) -> list[AgentHandle]:
        """List all agents, optionally filtered by path prefix.

        Ref: Codex list_agents tool — returns all agents visible
        to the caller, filtered by path prefix.
        """
        agents = list(self._agents.values())
        if path_prefix:
            agents = [
                a for a in agents
                if str(a.agent_path).startswith(path_prefix)
            ]
        return agents

    def interrupt(self, agent_id: str) -> bool:
        """Interrupt a running agent.

        Ref: Codex interrupt_agent tool — signals the target agent
        to stop. Returns True if the agent was interrupted.
        """
        handle = self._agents.get(agent_id)
        if handle is None:
            return False
        if handle.status in (AgentStatus.RUNNING, AgentStatus.PENDING):
            handle.mark_interrupted()
            logger.info(f"[agent-manager] interrupted: {agent_id}")
            return True
        return False

    @property
    def stats(self) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        for h in self._agents.values():
            key = h.status.value
            status_counts[key] = status_counts.get(key, 0) + 1
        return {
            "total_agents": len(self._agents),
            "max_concurrent": self._max_concurrent,
            "max_depth": self._max_depth,
            "status_counts": status_counts,
            "active_count": sum(
                1 for h in self._agents.values()
                if h.status in (AgentStatus.RUNNING, AgentStatus.PENDING)
            ),
        }

    def set_executor(self, executor: Any) -> None:
        """Set the agent executor callable.

        The executor is a callable(agent_id, task_description) -> Any
        used to run sub-agents in background tasks.
        """
        self._agent_executor = executor

    async def shutdown(self) -> None:
        """Shutdown the agent manager: cancel running tasks, clear all handles.

        Called when the session ends to release all resources.
        After shutdown, the manager should not be reused.
        """
        # Cancel all running sub-agent tasks
        for agent_id, task in list(self._running_tasks.items()):
            if not task.done():
                task.cancel()
                logger.info(f"[agent-manager] cancelled running task: {agent_id}")
        # Wait for cancellations to propagate
        if self._running_tasks:
            await asyncio.gather(
                *self._running_tasks.values(), return_exceptions=True
            )
        self._running_tasks.clear()

        # Clear all agent handles
        count = len(self._agents)
        self._agents.clear()
        self._root_id = None
        logger.info(f"[agent-manager] shutdown complete, cleared {count} agent handles")

    def start_sub_agent(
        self,
        agent_id: str,
        task_description: str,
        bus: InterAgentBus | None = None,
        observer: Any = None,
        node_id: str = "",
        session_id: str = "",
        concurrency_pool: Any | None = None,
        registered_agent_def: Any | None = None,
        model_override: str | None = None,
        fork_mode: str = "clean",
    ) -> asyncio.Task | None:
        """Launch a sub-agent in a background asyncio.Task.

        The sub-agent will:
        1. Mark itself as RUNNING
        2. Execute via self._agent_executor (if set)
        3. Mark COMPLETED/ERROR based on result
        4. Release concurrency pool slot
        5. Send a result message back to parent via bus (if provided)
        6. Emit collab_agent_completed via observer (if provided)

        Returns the asyncio.Task for the caller to track.
        """
        handle = self._agents.get(agent_id)
        if handle is None:
            return None

        _pool = concurrency_pool
        _model_override = model_override

        if _model_override and handle:
            handle.model_override = _model_override
        if registered_agent_def is not None and handle:
            handle._registered_agent_def = registered_agent_def
        if fork_mode and handle:
            handle._fork_mode = fork_mode

        async def _run():
            handle.mark_running()
            try:
                if self._agent_executor is not None:
                    result = await self._agent_executor(
                        agent_id, task_description
                    )
                    handle.mark_completed(result=result)
                else:
                    handle.mark_completed(result=task_description)
            except asyncio.CancelledError:
                handle.mark_interrupted()
            except Exception as e:
                handle.mark_error(error=str(e))
                logger.error(f"[agent-manager] sub-agent {agent_id} failed: {e}")
            finally:
                self._running_tasks.pop(agent_id, None)
                if _pool is not None:
                    try:
                        _pool.release(agent_id)
                    except Exception:
                        pass
                if bus and handle.parent_id:
                    from app.engine.collab.message_bus import AgentMessage, MessageType
                    try:
                        await asyncio.wait_for(
                            bus.send(AgentMessage(
                                message_type=MessageType.RESULT,
                                sender_id=agent_id,
                                recipient_id=handle.parent_id,
                                content=str(handle.result)[:500] if handle.result else "",
                            )),
                            timeout=5.0,
                        )
                    except asyncio.TimeoutError:
                        logger.warning(f"[agent-manager] bus.send timed out for {agent_id}, skipping")
                    except Exception:
                        pass
                if observer is not None:
                    try:
                        await observer.emit_trace(
                            node_id or "collab",
                            "collab_agent_completed",
                            {
                                "agent_id": agent_id,
                                "status": handle.status.value,
                                "error": handle.error,
                                "name": handle.role or "",
                                "task_description": task_description,
                                "result_preview": str(handle.result)[:200] if handle.result else "",
                            },
                        )
                    except Exception:
                        pass
                if session_id:
                    try:
                        from app.engine.collab.persistence import update_agent_status
                        await update_agent_status(
                            session_id, agent_id,
                            handle.status.value,
                            error=handle.error,
                        )
                    except Exception:
                        pass

        task = asyncio.create_task(_run())
        self._running_tasks[agent_id] = task
        return task