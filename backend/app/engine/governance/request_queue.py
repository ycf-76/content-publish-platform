"""LLM Request Queue — rate-limited async queue for LLM API calls.

Codex core insight (ref: codex-rs/core/src/session/input_queue.rs):
  - InputQueue manages pending user inputs and inter-agent mail
  - It decouples "request arrival" from "request processing"
  - The session consumes from the queue at its own pace
  - This is THE fundamental pattern that prevents 429: the queue owns the rate

Our adaptation:
  - Instead of Codex's per-session input queue (which manages user inputs),
    we build a global LLM call queue that manages API call rate
  - Codex's insight: "never let the caller hit the API directly, always go through a queue"
  - We apply this to LLM calls: all LLM calls go through this queue,
    which enforces a token-bucket rate limit
  - Workers consume from the queue at a controlled rate,
    so the API never sees burst traffic

Key design decisions from Codex:
  1. Queue is async, callers await results (like Codex's turn suspension)
  2. Queue has a concurrency limit (like Codex's single-turn-at-a-time model)
  3. Rate is controlled by token bucket (like Codex's rollout_budget)
  4. Callers get a Future they can await (like Codex's turn_input/turn_suspension)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class _PendingRequest:
    """A pending LLM request waiting in the queue.

    Ref: Codex's TurnInput — the queue stores inputs and the caller
    awaits the result via a Future.
    """

    call_id: int
    fn: Callable[[], Awaitable[Any]]
    future: asyncio.Future
    enqueued_at: float = field(default_factory=time.monotonic)
    token_estimate: int = 0


class TokenBucketRateLimiter:
    """Token bucket rate limiter.

    Ref: Codex's rollout_budget.rs — tracks token usage and enforces
    a budget per time window. When budget is exceeded, requests must wait.

    Key insight from Codex: the rate limiter doesn't reject requests,
    it DELAYS them. This is the fundamental difference from our old approach
    (which let requests hit the API and then retry on 429).
    """

    def __init__(
        self,
        max_requests_per_minute: int = 200,
        max_concurrent: int = 10,
    ) -> None:
        self._max_rpm = max_requests_per_minute
        self._max_concurrent = max_concurrent
        self._tokens = float(max_requests_per_minute)
        self._last_refill = time.monotonic()
        self._refill_rate = max_requests_per_minute / 60.0
        self._active_count = 0
        self._lock = asyncio.Lock()
        self._wake = asyncio.Event()

    async def acquire(self) -> None:
        """Wait until a token is available, then consume it.

        This is the key: instead of sending a request and getting a 429,
        we wait here until we know the request will succeed.
        """
        while True:
            async with self._lock:
                self._refill()
                if self._tokens >= 1.0 and self._active_count < self._max_concurrent:
                    self._tokens -= 1.0
                    self._active_count += 1
                    return
            self._wake.clear()
            await asyncio.wait_for(self._wake.wait(), timeout=0.05)

    async def release(self) -> None:
        """Release a concurrency slot after request completes."""
        async with self._lock:
            self._active_count = max(0, self._active_count - 1)
        self._wake.set()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            float(self._max_rpm),
            self._tokens + elapsed * self._refill_rate,
        )
        self._last_refill = now


class LLMRequestQueue:
    """Global LLM request queue with rate limiting.

    Ref: Codex's InputQueue + Session architecture:
      - InputQueue stores pending inputs
      - Session processes them one at a time
      - Rate is controlled by the session, not the caller

    Our adaptation:
      - All LLM calls go through this queue (no direct API calls)
      - Queue enforces token-bucket rate limit
      - Callers submit a coroutine factory and await the result
      - Workers consume at controlled rate

    Usage:
        queue = LLMRequestQueue(max_rpm=50, max_concurrent=5)
        result = await queue.submit(lambda: llm.chat(messages))
    """

    def __init__(
        self,
        max_rpm: int = 200,
        max_concurrent: int = 10,
    ) -> None:
        self._limiter = TokenBucketRateLimiter(
            max_requests_per_minute=max_rpm,
            max_concurrent=max_concurrent,
        )
        self._queue: deque[_PendingRequest] = deque()
        self._call_counter = 0
        self._counter_lock = asyncio.Lock()
        self._started = False
        self._worker_task: asyncio.Task | None = None
        self._total_enqueued = 0
        self._total_completed = 0
        self._total_rejected = 0
        self._queue_event = asyncio.Event()

    def start(self, num_workers: int = 3) -> None:
        """Start worker tasks.

        Ref: Codex's session spawns a turn for each input.
        We spawn N workers that consume from the queue.
        """
        if self._started:
            return
        self._started = True
        self._worker_tasks: list[asyncio.Task] = []
        for i in range(num_workers):
            task = asyncio.create_task(self._worker(i))
            task.add_done_callback(lambda t: logger.debug(f"[llm-queue] worker done"))
            self._worker_tasks.append(task)
        logger.info(
            f"[llm-queue] started {num_workers} workers, "
            f"max_rpm={self._limiter._max_rpm}, "
            f"max_concurrent={self._limiter._max_concurrent}"
        )

    async def submit(
        self,
        fn: Callable[[], Awaitable[Any]],
        token_estimate: int = 0,
        priority: int = 0,
    ) -> Any:
        """Submit an LLM call to the queue and await the result.

        Ref: Codex's InputQueue.enqueue() + TurnSuspension pattern:
          - Caller enqueues input
          - Caller awaits a Future
          - When the turn completes, the Future is resolved

        This is the key API: callers never hit the API directly.
        They submit through the queue and wait for the result.
        """
        if not self._started:
            self.start()

        async with self._counter_lock:
            self._call_counter += 1
            call_id = self._call_counter

        loop = asyncio.get_running_loop()
        future = loop.create_future()

        req = _PendingRequest(
            call_id=call_id,
            fn=fn,
            future=future,
            token_estimate=token_estimate,
        )

        if priority > 0:
            self._queue.appendleft(req)
        else:
            self._queue.append(req)

        self._total_enqueued += 1
        self._queue_event.set()
        logger.debug(
            f"[llm-queue] enqueued call #{call_id} "
            f"(queue={len(self._queue)}, total={self._total_enqueued})"
        )

        return await future

    async def _worker(self, worker_id: int) -> None:
        """Worker that consumes requests from the queue.

        Ref: Codex's session.run_turn() — processes one turn at a time,
        rate-limited by the session's own pacing.
        """
        while True:
            try:
                if not self._queue:
                    self._queue_event.clear()
                    await asyncio.wait_for(self._queue_event.wait(), timeout=1.0)
                    continue

                req = self._queue.popleft()

                await self._limiter.acquire()

                try:
                    result = await req.fn()
                    if not req.future.done():
                        req.future.set_result(result)
                    self._total_completed += 1
                except Exception as e:
                    if not req.future.done():
                        req.future.set_exception(e)
                    self._total_rejected += 1
                    logger.warning(
                        f"[llm-queue] worker-{worker_id} call #{req.call_id} failed: {e}"
                    )
                finally:
                    await self._limiter.release()

            except asyncio.CancelledError:
                logger.info(f"[llm-queue] worker-{worker_id} cancelled")
                break
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"[llm-queue] worker-{worker_id} error: {e}")
                await asyncio.sleep(1)

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "queue_depth": len(self._queue),
            "total_enqueued": self._total_enqueued,
            "total_completed": self._total_completed,
            "total_rejected": self._total_rejected,
            "active_workers": self._limiter._active_count,
        }

    async def shutdown(self) -> None:
        """Cancel all worker tasks and stop the queue."""
        for task in getattr(self, '_worker_tasks', []):
            if not task.done():
                task.cancel()
        if getattr(self, '_worker_tasks', None):
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._started = False
        logger.info("[llm-queue] shutdown complete")


_global_queue: LLMRequestQueue | None = None


def get_llm_queue() -> LLMRequestQueue:
    """Get or create the global LLM request queue.

    The queue is created lazily. Workers are started on first submit()
    call (which always happens inside an async context), not at creation
    time, so this function is safe to call outside an event loop.
    """
    global _global_queue
    if _global_queue is None:
        _global_queue = LLMRequestQueue()
    return _global_queue