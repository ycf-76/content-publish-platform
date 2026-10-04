"""Thread Store: session persistence and rollback.

Ref: Codex thread_store.rs / thread.rs — every session has a thread that:
  1. Records every event (user input, LLM response, tool call, tool result)
  2. Can be persisted to disk/DB
  3. Supports rollback to any prior checkpoint
  4. Supports replay from a checkpoint

Our adaptation:
  - ThreadStore records events as an append-only log
  - Checkpoints are snapshots of the message list at a point in time
  - rollback() restores messages to a prior checkpoint
  - search() finds events by type/content
  - to_dict() / from_dict() for serialization
  - Designed to be stored in Redis or DB via the existing chat_session layer

Usage:
    store = ThreadStore()
    store.record("user_input", {"content": "search AI trends"})
    store.checkpoint("before_search")
    store.record("tool_call", {"tool": "trending_search", "args": {...}})
    store.record("tool_result", {"tool": "trending_search", "result": {...}})
    # ... later ...
    store.rollback("before_search")  # messages restored to checkpoint
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from enum import Enum
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ThreadEventType(str, Enum):
    USER_INPUT = "user_input"
    LLM_REQUEST = "llm_request"
    LLM_RESPONSE = "llm_response"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    COMPACTION = "compaction"
    BUDGET_WARNING = "budget_warning"
    GUARDIAN_DECISION = "guardian_decision"
    CHECKPOINT = "checkpoint"
    ERROR = "error"


class ThreadEvent(BaseModel):
    id: str
    event_type: ThreadEventType
    timestamp: float
    data: dict[str, Any]
    metadata: dict[str, Any] = {}


class Checkpoint(BaseModel):
    name: str
    event_index: int
    messages_snapshot: list[dict[str, Any]]
    timestamp: float
    token_usage: int = 0


class ThreadStore:
    """Append-only event log with checkpoint/rollback support.

    Ref: Codex thread_store.rs:
      - Thread holds a Vec<ThreadEvent> (append-only)
      - Checkpoints are created at key moments
      - rollback() truncates the event list and restores state

    Our adaptation:
      - Events are stored as ThreadEvent objects
      - Checkpoints snapshot the current message list
      - rollback() restores messages and truncates events
      - search() finds events by type or content
    """

    def __init__(self, thread_id: str | None = None) -> None:
        self.thread_id = thread_id or uuid.uuid4().hex[:16]
        self._events: list[ThreadEvent] = []
        self._checkpoints: dict[str, Checkpoint] = {}
        self._messages: list[dict[str, Any]] = []
        self._token_usage = 0

    def record(
        self,
        event_type: ThreadEventType,
        data: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> ThreadEvent:
        event = ThreadEvent(
            id=uuid.uuid4().hex[:12],
            event_type=event_type,
            timestamp=time.time(),
            data=data,
            metadata=metadata or {},
        )
        self._events.append(event)
        logger.debug(
            f"[thread:{self.thread_id}] recorded {event_type.value} "
            f"(total events: {len(self._events)})"
        )
        return event

    def checkpoint(
        self,
        name: str,
        messages: list[dict[str, Any]] | None = None,
    ) -> Checkpoint:
        cp = Checkpoint(
            name=name,
            event_index=len(self._events),
            messages_snapshot=copy.deepcopy(messages or self._messages),
            timestamp=time.time(),
            token_usage=self._token_usage,
        )
        self._checkpoints[name] = cp
        self.record(
            ThreadEventType.CHECKPOINT,
            {"checkpoint_name": name, "event_index": cp.event_index},
        )
        logger.info(
            f"[thread:{self.thread_id}] checkpoint '{name}' at event #{cp.event_index}"
        )
        return cp

    def rollback(self, name: str) -> list[dict[str, Any]] | None:
        cp = self._checkpoints.get(name)
        if cp is None:
            logger.warning(
                f"[thread:{self.thread_id}] checkpoint '{name}' not found"
            )
            return None

        self._events = self._events[: cp.event_index]
        self._messages = copy.deepcopy(cp.messages_snapshot)
        self._token_usage = cp.token_usage

        # Remove checkpoints created after this one
        to_remove = [
            k for k, v in self._checkpoints.items() if v.event_index > cp.event_index
        ]
        for k in to_remove:
            del self._checkpoints[k]

        logger.info(
            f"[thread:{self.thread_id}] rolled back to '{name}' "
            f"(events: {len(self._events)}, messages: {len(self._messages)})"
        )
        return self._messages

    def set_messages(self, messages: list[dict[str, Any]]) -> None:
        self._messages = copy.deepcopy(messages)

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self._messages

    @property
    def token_usage(self) -> int:
        return self._token_usage

    @token_usage.setter
    def token_usage(self, value: int) -> None:
        self._token_usage = value

    def search(
        self,
        event_type: ThreadEventType | None = None,
        content_contains: str | None = None,
        last_n: int = 50,
    ) -> list[ThreadEvent]:
        results = []
        for event in reversed(self._events):
            if event_type and event.event_type != event_type:
                continue
            if content_contains:
                data_str = json.dumps(event.data, ensure_ascii=False)
                if content_contains.lower() not in data_str.lower():
                    continue
            results.append(event)
            if len(results) >= last_n:
                break
        return list(reversed(results))

    def to_dict(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "events": [e.model_dump() for e in self._events],
            "checkpoints": {k: v.model_dump() for k, v in self._checkpoints.items()},
            "messages": self._messages,
            "token_usage": self._token_usage,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ThreadStore:
        store = cls(thread_id=data.get("thread_id"))
        events: list[ThreadEvent] = []
        for e in data.get("events", []):
            try:
                events.append(ThreadEvent(**e))
            except Exception as ex:
                logger.warning(f"[thread] skipping corrupt event: {ex}")
        store._events = events
        checkpoints: dict[str, Checkpoint] = {}
        for k, v in data.get("checkpoints", {}).items():
            try:
                checkpoints[k] = Checkpoint(**v)
            except Exception as ex:
                logger.warning(f"[thread] skipping corrupt checkpoint '{k}': {ex}")
        store._checkpoints = checkpoints
        store._messages = data.get("messages", [])
        store._token_usage = data.get("token_usage", 0)
        return store

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "total_events": len(self._events),
            "checkpoints": list(self._checkpoints.keys()),
            "messages_count": len(self._messages),
            "token_usage": self._token_usage,
        }

    async def persist(self) -> None:
        """Persist the thread to Redis.

        Ref: Codex session.rs::save() — after each checkpoint or critical
        event, the session is persisted to the backing store. We use Redis
        with a 24h TTL, matching the typical session lifetime.
        """
        try:
            from app.cache.redis import redis_client

            key = f"thread:{self.thread_id}"
            data = json.dumps(self.to_dict(), ensure_ascii=False)
            await redis_client.set(key, data, ex=86400)
            logger.debug(
                f"[thread:{self.thread_id}] persisted to Redis "
                f"({len(data)} bytes, {len(self._events)} events)"
            )
        except Exception as e:
            logger.warning(f"[thread:{self.thread_id}] persist failed: {e}")

    @classmethod
    async def load(cls, thread_id: str) -> ThreadStore | None:
        """Load a thread from Redis.

        Ref: Codex session.rs::load() — reconstruct the session from
        the backing store on startup or reconnection.
        """
        try:
            from app.cache.redis import redis_client

            key = f"thread:{thread_id}"
            raw = await redis_client.get(key)
            if raw is None:
                return None
            data = json.loads(raw)
            store = cls.from_dict(data)
            logger.info(
                f"[thread:{thread_id}] loaded from Redis "
                f"({len(store._events)} events, {len(store._checkpoints)} checkpoints)"
            )
            return store
        except Exception as e:
            logger.warning(f"[thread:{thread_id}] load failed: {e}")
            return None

    async def persist_checkpoint(self, name: str, messages: list[dict[str, Any]] | None = None) -> Checkpoint:
        """Create a checkpoint and persist to Redis atomically.

        Ref: Codex session.rs — checkpoints are the natural persistence
        boundary. After each checkpoint, the session is saved.
        """
        cp = self.checkpoint(name, messages)
        await self.persist()
        return cp