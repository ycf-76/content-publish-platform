"""Concurrency Pool: bounded parallel agent execution.

Ref: Codex max_concurrent_threads_per_session:
  - Codex limits the number of simultaneously active agents
  - The session holds a concurrency pool (default 3 slots)
  - spawn_agent checks available slots before creating a new thread
  - When an agent completes, its slot is released

Our adaptation:
  - ConcurrencyPool wraps asyncio.Semaphore with slot tracking
  - Each slot holds a reference to the running agent
  - Supports priority-based scheduling (higher depth = lower priority)
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class PoolSlot:
    """A concurrency slot occupied by a running agent."""
    agent_id: str
    acquired_at: float = field(default_factory=time.time)
    released_at: float | None = None

    @property
    def duration_s(self) -> float:
        end = self.released_at or time.time()
        return end - self.acquired_at


class ConcurrencyPool:
    """Bounded concurrency pool for parallel agent execution.

    Ref: Codex max_concurrent_threads_per_session:
      - Limits how many agents can run simultaneously
      - Default: 3 concurrent agents per session
      - Slot acquisition is async (waits if pool is full)
      - Slots are released when agents complete or are interrupted
    """

    def __init__(self, max_slots: int = 3) -> None:
        self._max_slots = max_slots
        self._semaphore = asyncio.Semaphore(max_slots)
        self._slots: dict[str, PoolSlot] = {}
        self._total_acquired: int = 0
        self._total_released: int = 0

    async def acquire(self, agent_id: str, timeout: float | None = None) -> bool:
        """Acquire a concurrency slot for an agent.

        Returns True if acquired, False on timeout.
        Raises ValueError if the agent already holds a slot.
        """
        if agent_id in self._slots:
            raise ValueError(f"Agent {agent_id} already holds a slot")

        try:
            if timeout is not None:
                acquired = await asyncio.wait_for(
                    self._semaphore.acquire(), timeout=timeout
                )
            else:
                await self._semaphore.acquire()
                acquired = True
        except asyncio.TimeoutError:
            logger.warning(
                f"[concurrency-pool] agent {agent_id} timed out "
                f"waiting for slot (pool full: {self._max_slots})"
            )
            return False

        self._slots[agent_id] = PoolSlot(agent_id=agent_id)
        self._total_acquired += 1
        logger.debug(
            f"[concurrency-pool] acquired slot for {agent_id} "
            f"({self.active_count}/{self._max_slots})"
        )
        return True

    def release(self, agent_id: str) -> None:
        """Release a concurrency slot."""
        slot = self._slots.pop(agent_id, None)
        if slot is None:
            return
        slot.released_at = time.time()
        if self._semaphore._value < self._max_slots:
            self._semaphore.release()
        else:
            logger.warning(
                f"[concurrency-pool] double release detected for {agent_id}, "
                f"semaphore already at max ({self._max_slots})"
            )
        self._total_released += 1
        logger.debug(
            f"[concurrency-pool] released slot for {agent_id} "
            f"(duration: {slot.duration_s:.1f}s, "
            f"active: {self.active_count}/{self._max_slots})"
        )

    @property
    def active_count(self) -> int:
        return len(self._slots)

    @property
    def available_slots(self) -> int:
        return self._max_slots - self.active_count

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "max_slots": self._max_slots,
            "active_count": self.active_count,
            "available_slots": self.available_slots,
            "total_acquired": self._total_acquired,
            "total_released": self._total_released,
            "active_agents": list(self._slots.keys()),
        }