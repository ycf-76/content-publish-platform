"""熔断器（架构文档 4.4.3）。

三态：CLOSED / OPEN / HALF_OPEN。
- CLOSED：正常放行
- OPEN：熔断，拒绝请求
- HALF_OPEN：recovery_timeout 后试探放行 1 个，成功转 CLOSED，失败转 OPEN

红线：
- failure_threshold 默认 5（红线 4.1）
- recovery_timeout 默认 60s（红线 4.1）
- half_open_max 默认 1
- 不引入外部依赖
"""

from __future__ import annotations

import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断状态。"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """熔断开启时被拒绝。"""

    def __init__(self, agent_id: str, state: CircuitState) -> None:
        self.agent_id = agent_id
        self.state = state
        super().__init__(f"Circuit {state.value} for {agent_id}")


class CircuitBreaker:
    """基于滑动窗口失败次数的熔断器。

    每个 agent_id 独立状态。线程不安全（asyncio 单线程假设）。
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max: int = 1,
    ) -> None:
        if failure_threshold < 1 or recovery_timeout < 0 or half_open_max < 1:
            raise ValueError("invalid circuit breaker params")
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max = half_open_max
        # agent_id → 状态
        self.states: dict[str, CircuitState] = {}
        self.failure_counts: dict[str, int] = {}
        self.last_failure_time: dict[str, float] = {}
        self.half_open_inflight: dict[str, int] = {}

    def allow_request(self, agent_id: str) -> bool:
        """是否放行。同时做 OPEN → HALF_OPEN 的状态转换。"""
        state = self._get_state(agent_id)
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.OPEN:
            # 检查是否到了半开时间
            last = self.last_failure_time.get(agent_id, 0)
            if time.time() - last > self.recovery_timeout:
                self.states[agent_id] = CircuitState.HALF_OPEN
                self.half_open_inflight[agent_id] = 0
                logger.info(
                    f"[circuit] {agent_id} OPEN -> HALF_OPEN after {self.recovery_timeout}s"
                )
                return self._allow_half_open(agent_id)
            return False  # 熔断中，拒绝
        if state == CircuitState.HALF_OPEN:
            return self._allow_half_open(agent_id)
        return True  # 兜底

    def record_success(self, agent_id: str) -> None:
        """记录一次成功：失败计数清零，状态转 CLOSED。"""
        self.failure_counts[agent_id] = 0
        self.states[agent_id] = CircuitState.CLOSED
        self.half_open_inflight[agent_id] = 0

    def record_failure(self, agent_id: str) -> None:
        """记录一次失败：累加失败计数，达阈值转 OPEN。"""
        self.failure_counts[agent_id] = self.failure_counts.get(agent_id, 0) + 1
        self.last_failure_time[agent_id] = time.time()
        # HALF_OPEN 态任一失败立刻回 OPEN
        if self._get_state(agent_id) == CircuitState.HALF_OPEN:
            self.states[agent_id] = CircuitState.OPEN
            self.half_open_inflight[agent_id] = 0
            logger.warning(
                f"[circuit] {agent_id} HALF_OPEN -> OPEN (probe failed)"
            )
            return
        if self.failure_counts[agent_id] >= self.failure_threshold:
            self.states[agent_id] = CircuitState.OPEN
            logger.warning(
                f"[circuit] {agent_id} CLOSED -> OPEN "
                f"(failures={self.failure_counts[agent_id]})"
            )

    def get_state(self, agent_id: str) -> CircuitState:
        """获取当前状态（测试用）。"""
        return self._get_state(agent_id)

    def reset(self, agent_id: str | None = None) -> None:
        """重置状态（测试用）。"""
        if agent_id is None:
            self.states.clear()
            self.failure_counts.clear()
            self.last_failure_time.clear()
            self.half_open_inflight.clear()
        else:
            self.states.pop(agent_id, None)
            self.failure_counts.pop(agent_id, None)
            self.last_failure_time.pop(agent_id, None)
            self.half_open_inflight.pop(agent_id, None)

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _get_state(self, agent_id: str) -> CircuitState:
        return self.states.get(agent_id, CircuitState.CLOSED)

    def _allow_half_open(self, agent_id: str) -> bool:
        inflight = self.half_open_inflight.get(agent_id, 0)
        if inflight < self.half_open_max:
            self.half_open_inflight[agent_id] = inflight + 1
            return True
        return False
