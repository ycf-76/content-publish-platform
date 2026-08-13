"""SSE event bus for real-time event streaming.

Implements:
- Single instance per workflow
- Event publishing with ULID event_id
- Last-Event-ID continuation
- 15s heartbeat
- DB persistence for replay
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SSEEvent(BaseModel):
    """SSE event structure."""

    event_id: str
    event_type: str
    payload: dict[str, Any]
    timestamp: str


class SSEEventBus:
    """SSE event bus for workflow event streaming.

    Singleton pattern: one instance per workflow_id.
    """

    _instance: SSEEventBus | None = None

    def __new__(cls) -> SSEEventBus:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers = defaultdict(set)
            cls._instance._event_history = defaultdict(list)
        return cls._instance

    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._event_history: dict[str, list[SSEEvent]] = defaultdict(list)

    async def publish(
        self,
        workflow_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        """Publish event to all subscribers of a workflow.

        Args:
            workflow_id: Workflow ID
            event_type: Event type (27 types defined in protocol)
            payload: Event payload

        Returns:
            event_id: Generated event ID (evt_ + ULID)
        """
        import ulid

        event_id = f"evt_{ulid.new()}"
        event = SSEEvent(
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            timestamp=datetime.now(UTC).isoformat(),
        )

        # Persist to history (for Last-Event-ID continuation)
        self._event_history[workflow_id].append(event)

        # Push to all subscriber queues
        queues = self._subscribers.get(workflow_id, set())
        for queue in queues:
            await queue.put(event)

        logger.debug(f"[{workflow_id}] Published {event_type}: {event_id}")
        return event_id

    async def subscribe(
        self,
        workflow_id: str,
        last_event_id: str | None = None,
    ) -> AsyncIterator[str]:
        """Subscribe to workflow events.

        Args:
            workflow_id: Workflow ID
            last_event_id: Last received event ID (for continuation)

        Yields:
            SSE formatted strings: "id: {event_id}\\nevent: {type}\\ndata: {json}\\n\\n"
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers[workflow_id].add(queue)

        # 终态事件类型：收到后主动结束订阅，让前端流自然 done，避免前端 abort 触发 ERR_ABORTED
        terminal_types = {'workflow_completed', 'workflow_error', 'workflow_terminated'}

        try:
            # Replay missed events.
            # - 带 last_event_id：从该 id 之后 replay（断线重连场景）
            # - 不带 last_event_id：replay 全部历史（首次订阅场景）。
            #   原因：后端 start_workflow 用 asyncio.create_task 启动 graph，
            #   graph 执行可能极快（search 调 API + 其他节点 stub），
            #   事件在前端 SSE 连接建立前就发完了。首次订阅 replay 全部历史，
            #   保证前端不丢事件。若 history 中已有 terminal 事件，replay 后直接结束。
            history = self._event_history.get(workflow_id, [])
            if last_event_id:
                replay_list = self._replay_events(workflow_id, last_event_id)
            else:
                replay_list = list(history)
            for event in replay_list:
                yield self._format_sse(event)
                if event.event_type in terminal_types:
                    logger.debug(
                        f"[{workflow_id}] Stream ended after replaying terminal event {event.event_type}"
                    )
                    return

            # Real-time subscription
            heartbeat_counter = 0
            while True:
                try:
                    # Wait for event with timeout for heartbeat
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    heartbeat_counter = 0
                    yield self._format_sse(event)
                    # 终态事件：结束订阅，关闭 SSE 流
                    if event.event_type in terminal_types:
                        logger.debug(f"[{workflow_id}] Stream ended after terminal event {event.event_type}")
                        return
                except TimeoutError:
                    # Send heartbeat every 15 seconds
                    heartbeat_counter += 1
                    yield ": heartbeat\n\n"
                    if heartbeat_counter > 4:
                        # 60 seconds without events, check connection
                        logger.debug(f"[{workflow_id}] Heartbeat check")
        finally:
            self._subscribers[workflow_id].discard(queue)

    def _replay_events(
        self, workflow_id: str, last_event_id: str
    ) -> list[SSEEvent]:
        """Replay events after last_event_id."""
        events = self._event_history.get(workflow_id, [])
        found = False
        replay = []
        for event in events:
            if found:
                replay.append(event)
            if event.event_id == last_event_id:
                found = True
        return replay

    def _format_sse(self, event: SSEEvent) -> str:
        """Format event as SSE string."""
        data = json.dumps(
            {
                "event_id": event.event_id,
                "type": event.event_type,
                "payload": event.payload,
                "timestamp": event.timestamp,
            }
        )
        return f"id: {event.event_id}\nevent: {event.event_type}\ndata: {data}\n\n"


# Singleton instance
sse_bus = SSEEventBus()
