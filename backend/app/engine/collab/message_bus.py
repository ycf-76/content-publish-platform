"""Inter-Agent Message Bus: async message passing between agents.

Ref: Codex InterAgentCommunication + send_message tool:
  - Agents communicate via message passing, not shared memory
  - Messages are queued per-agent (each agent has an inbox)
  - Messages can trigger a new turn in the receiving agent
  - Two delivery modes: queue_only (no turn trigger) and trigger_turn

Our adaptation:
  - InterAgentBus is a singleton per workflow session
  - Each agent gets an asyncio.Queue as inbox
  - Messages carry type (task/message/result) and content
  - wait_agent polls the bus for activity
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


class MessageType(str, Enum):
    TASK = "task"
    MESSAGE = "message"
    RESULT = "result"
    INTERRUPT = "interrupt"


@dataclass
class AgentMessage:
    """A message between agents.

    Ref: Codex InterAgentMessage — carries:
      - message_type (NewTask / Message)
      - recipient (AgentPath)
      - author (AgentPath)
      - content (the actual message text)
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    message_type: MessageType = MessageType.MESSAGE
    sender_id: str = ""
    recipient_id: str = ""
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    trigger_turn: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.message_type.value,
            "sender": self.sender_id,
            "recipient": self.recipient_id,
            "content": self.content[:500],
            "trigger_turn": self.trigger_turn,
            "timestamp": self.timestamp,
        }


class InterAgentBus:
    """Async message bus for inter-agent communication.

    Ref: Codex's input_queue + InterAgentCommunication:
      - Each agent has an inbox (asyncio.Queue)
      - send_message enqueues to the recipient's inbox
      - wait_agent subscribes to activity events
      - Messages can optionally trigger a new turn

    Our adaptation:
      - Singleton per workflow session
      - asyncio.Queue per agent for message inbox
      - Activity events for wait_agent polling
      - Message history for debugging/auditing
    """

    def __init__(self, max_inbox_size: int = 100) -> None:
        self._inboxes: dict[str, asyncio.Queue[AgentMessage]] = {}
        self._max_inbox_size = max_inbox_size
        self._history: list[AgentMessage] = []
        self._activity_events: dict[str, asyncio.Event] = {}

    def register(self, agent_id: str) -> None:
        """Register an agent's inbox on the bus."""
        if agent_id not in self._inboxes:
            self._inboxes[agent_id] = asyncio.Queue(maxsize=self._max_inbox_size)
            self._activity_events[agent_id] = asyncio.Event()
            logger.debug(f"[message-bus] registered inbox for {agent_id}")

    async def send(self, message: AgentMessage) -> None:
        """Send a message to an agent's inbox.

        Ref: Codex send_message tool — enqueues the message
        and optionally triggers a new turn in the recipient.
        """
        inbox = self._inboxes.get(message.recipient_id)
        if inbox is None:
            logger.warning(
                f"[message-bus] recipient {message.recipient_id} not registered, "
                f"dropping message from {message.sender_id}"
            )
            return

        try:
            inbox.put_nowait(message)
        except asyncio.QueueFull:
            logger.warning(
                f"[message-bus] inbox full for {message.recipient_id}, "
                f"dropping message from {message.sender_id}"
            )
            return
        self._history.append(message)

        activity = self._activity_events.get(message.recipient_id)
        if activity:
            activity.set()

        logger.debug(
            f"[message-bus] {message.sender_id} -> {message.recipient_id} "
            f"type={message.message_type.value} trigger_turn={message.trigger_turn}"
        )

    async def receive(
        self,
        agent_id: str,
        timeout: float | None = None,
    ) -> AgentMessage | None:
        """Receive the next message from an agent's inbox.

        Returns None if the inbox is empty and timeout expires.
        """
        inbox = self._inboxes.get(agent_id)
        if inbox is None:
            return None

        try:
            if timeout is not None:
                return await asyncio.wait_for(inbox.get(), timeout=timeout)
            return await inbox.get()
        except asyncio.TimeoutError:
            return None

    def pending_count(self, agent_id: str) -> int:
        """Return the number of pending messages for an agent."""
        inbox = self._inboxes.get(agent_id)
        if inbox is None:
            return 0
        return inbox.qsize()

    async def drain(
        self,
        agent_id: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Drain all pending messages from an agent's inbox.

        Returns a list of message dicts (not AgentMessage objects)
        for easy consumption by the LoopExecutor.

        Used by the main loop to inject sub-agent results into
        the LLM conversation context.
        """
        inbox = self._inboxes.get(agent_id)
        if inbox is None:
            return []

        messages: list[dict[str, Any]] = []
        for _ in range(min(limit, inbox.qsize())):
            try:
                msg = inbox.get_nowait()
                messages.append({
                    "id": msg.id,
                    "message_type": msg.message_type.value,
                    "sender_id": msg.sender_id,
                    "recipient_id": msg.recipient_id,
                    "content": msg.content,
                    "trigger_turn": msg.trigger_turn,
                    "timestamp": msg.timestamp,
                })
            except asyncio.QueueEmpty:
                break

        return messages

    async def wait_for_activity(
        self,
        agent_id: str,
        timeout: float = 30.0,
    ) -> bool:
        """Wait for any activity (new message) for an agent.

        Ref: Codex wait_agent tool — blocks until the target agent
        has activity or the timeout expires.

        Returns True if activity was detected, False on timeout.
        """
        event = self._activity_events.get(agent_id)
        if event is None:
            return False

        event.clear()
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "registered_agents": len(self._inboxes),
            "total_messages_sent": len(self._history),
            "pending_per_agent": {
                aid: inbox.qsize()
                for aid, inbox in self._inboxes.items()
            },
        }

    def shutdown(self) -> None:
        """Shutdown the message bus: clear all inboxes and history.

        Called when the session ends to release all resources.
        """
        agent_count = len(self._inboxes)
        msg_count = len(self._history)
        self._inboxes.clear()
        self._activity_events.clear()
        self._history.clear()
        logger.info(
            f"[message-bus] shutdown complete, "
            f"cleared {agent_count} inboxes, {msg_count} history messages"
        )