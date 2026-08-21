"""全局通知总线 — 跨模块实时推送。

与 sse_bus 不同，这里不绑定 workflow_id，而是全局广播。
用于选题池监控完成、系统事件等非工作流场景的实时通知。

前端通过 GET /api/sse/notifications 订阅，收到事件后显示弹窗。
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class NotificationEvent(BaseModel):
    event_type: str
    payload: dict[str, Any]
    timestamp: str


class NotificationBus:
    """全局通知总线（单例）。

    所有已登录用户共享同一个通知频道。
    后端各模块调用 publish() 推送事件，前端通过 SSE 订阅接收。
    """

    _instance: NotificationBus | None = None

    def __new__(cls) -> NotificationBus:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._subscribers: list[asyncio.Queue] = []
            cls._instance._recent: list[NotificationEvent] = []
        return cls._instance

    def __init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._recent: list[NotificationEvent] = []

    async def publish(
        self,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """广播通知事件到所有订阅者。"""
        event = NotificationEvent(
            event_type=event_type,
            payload=payload,
            timestamp=datetime.now(UTC).isoformat(),
        )

        self._recent.append(event)
        if len(self._recent) > 100:
            self._recent = self._recent[-100:]

        dead_queues: list[asyncio.Queue] = []
        for queue in self._subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                dead_queues.append(queue)

        for q in dead_queues:
            self._subscribers.remove(q)

        logger.info(f"[NotificationBus] published {event_type}: {json.dumps(payload, ensure_ascii=False)[:120]}")

    async def subscribe(self) -> AsyncIterator[str]:
        """SSE 订阅流，前端通过此方法接收实时通知。"""
        queue: asyncio.Queue = asyncio.Queue(maxsize=50)
        self._subscribers.append(queue)

        try:
            for event in self._recent[-20:]:
                yield self._format_sse(event)

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield self._format_sse(event)
                except TimeoutError:
                    yield ": heartbeat\n\n"
        finally:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    def _format_sse(self, event: NotificationEvent) -> str:
        data = json.dumps(
            {
                "type": event.event_type,
                "payload": event.payload,
                "timestamp": event.timestamp,
            },
            ensure_ascii=False,
        )
        return f"event: {event.event_type}\ndata: {data}\n\n"


notification_bus = NotificationBus()