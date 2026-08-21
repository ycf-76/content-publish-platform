"""RecoveryLoop（架构文档 4.4.1 + 手册 Phase 6 Part C）。

主流程：
1. 熔断器拦截：最近失败率过高直接拒绝（抛 CircuitOpenError）
2. 按策略列表顺序逐个尝试：adjust → execute → 成功即返回
3. 失败：熔断器记录 + 退避 sleep + 试下一个策略
4. 全部失败：抛 RecoveryExhaustedError → 上层 RecoveryService 触发 supervisor 介入

红线：
- max_attempts=3 上限（红线 4.1）
- 智能退避 + 抖动（红线 4.1）
- 熔断器三态（红线 4.1）
- 重试策略硬编码（不让 LLM 决策，红线 4.1）
- 不直接调 LLM/MCP，execute_fn 由调用方注入
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from app.engine.harness.recovery.backoff import BackoffPolicy
from app.engine.harness.recovery.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
)
from app.engine.harness.recovery.strategies import RecoveryStrategy
from app.engine.schemas import RecoveryExhaustedError, WorkflowContext

if TYPE_CHECKING:
    from app.engine.harness.observer.observer import Observer
    from app.engine.harness.runtime import AgentHarness

logger = logging.getLogger(__name__)


# execute_fn: 接收调整后的 (input, context)，返回 dict
ExecuteFn = Callable[
    [dict[str, Any], WorkflowContext],
    Awaitable[dict[str, Any]],
]


class RecoveryLoop:
    """每个 Agent 内部的恢复循环。

    通过 AgentHarness.recovery_loop 字段注入（runtime.py L52 已留位）。
    AgentHarness.run() 会判断：有 recovery_loop → 走 execute_with_recovery；
    否则直接走 executor.execute。
    """

    def __init__(
        self,
        max_attempts: int = 3,
        strategies: list[RecoveryStrategy] | None = None,
        backoff: BackoffPolicy | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        observer: Observer | None = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.max_attempts = max_attempts
        # 默认策略：原样重试（与架构文档 4.4.4 对齐）
        if not strategies:
            from app.engine.harness.recovery.strategies import RetryStrategy
            strategies = [RetryStrategy()]
        self.strategies = list(strategies)
        self.backoff = backoff or BackoffPolicy()
        self.circuit_breaker = circuit_breaker or CircuitBreaker()
        self.observer = observer

    async def execute_with_recovery(
        self,
        agent: AgentHarness,
        input: dict[str, Any],
        context: WorkflowContext,
        execute_fn: ExecuteFn,
    ) -> dict[str, Any]:
        """恢复循环主流程。"""
        agent_id = agent.agent_id

        # 1. 熔断器拦截
        if not self.circuit_breaker.allow_request(agent_id):
            await self._emit("circuit_open", agent_id, context, {"state": "open"})
            logger.warning(f"[recovery] {agent_id} circuit open, reject")
            raise CircuitOpenError(agent_id, self.circuit_breaker.get_state(agent_id))

        last_error: Exception | None = None
        # 策略数 vs max_attempts：取较小值（架构文档 4.4.1 同款语义）
        attempts_to_run = min(self.max_attempts, len(self.strategies))
        if attempts_to_run == 0:
            # 兜底（理论上 __init__ 已保证 strategies 非空）
            attempts_to_run = 1

        for attempt in range(attempts_to_run):
            strategy = self.strategies[attempt]
            try:
                # 2. 策略调整输入/上下文
                adjusted_input, adjusted_ctx = strategy.adjust(
                    input, context, last_error
                )

                await self._emit(
                    "recovery_attempt",
                    agent_id,
                    context,
                    {
                        "attempt": attempt,
                        "strategy": strategy.name,
                        "description": strategy.describe(),
                    },
                )
                logger.info(
                    f"[recovery] {agent_id} attempt {attempt} strategy={strategy.name}"
                )

                # 3. 执行
                result = await execute_fn(adjusted_input, adjusted_ctx)

                # 4. 成功
                self.circuit_breaker.record_success(agent_id)
                await self._emit(
                    "recovery_success",
                    agent_id,
                    context,
                    {"attempt": attempt, "strategy": strategy.name},
                )
                return result

            except Exception as e:
                last_error = e
                self.circuit_breaker.record_failure(agent_id)
                await self._emit(
                    "recovery_attempt_failed",
                    agent_id,
                    context,
                    {
                        "attempt": attempt,
                        "strategy": strategy.name,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                )
                logger.warning(
                    f"[recovery] {agent_id} attempt {attempt} "
                    f"strategy={strategy.name} failed: {e}"
                )

                # 5. 退避（最后一次不退避）
                if attempt < attempts_to_run - 1:
                    delay = self.backoff.next_delay(attempt)
                    logger.info(f"[recovery] {agent_id} backoff {delay:.2f}s")
                    await asyncio.sleep(delay)
                continue

        # 6. 全部失败
        err_msg = str(last_error) if last_error else "no attempts made"
        logger.error(
            f"[recovery] {agent_id} exhausted after {attempts_to_run} attempts: {err_msg}"
        )
        await self._emit(
            "recovery_exhausted",
            agent_id,
            context,
            {"attempts": attempts_to_run, "last_error": err_msg},
        )
        raise RecoveryExhaustedError(
            node_id=context.node_id,
            attempts=attempts_to_run,
            last_error=err_msg,
        )

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    async def _emit(
        self,
        event_type: str,
        agent_id: str,
        context: WorkflowContext,
        payload: dict[str, Any],
    ) -> None:
        """推送 trace 事件。observer 缺省时静默。

        优先使用 Observer 的专用方法（项目书 4.8 要求），
        专用方法有明确的字段约定和语义，便于前端解析和统计。
        """
        if self.observer is None:
            return
        try:
            if event_type == "recovery_attempt":
                await self.observer.log_attempt(
                    context.node_id,
                    attempt=payload.get("attempt", 0),
                    strategy=payload.get("strategy", "unknown"),
                    adjusted=payload.get("description"),
                )
            elif event_type == "recovery_attempt_failed":
                await self.observer.log_attempt_failed(
                    context.node_id,
                    attempt=payload.get("attempt", 0),
                    strategy=payload.get("strategy", "unknown"),
                    error=payload.get("error", ""),
                    error_type=payload.get("error_type", ""),
                )
            elif event_type == "recovery_success":
                await self.observer.log_recovery_success(
                    context.node_id,
                    attempt=payload.get("attempt", 0),
                    strategy=payload.get("strategy", "unknown"),
                )
            elif event_type == "recovery_exhausted":
                await self.observer.log_recovery_exhausted(
                    context.node_id,
                    attempts=payload.get("attempts", 0),
                    last_error=payload.get("last_error", ""),
                )
            elif event_type == "circuit_open":
                await self.observer.log_circuit_open(
                    context.node_id,
                    state=payload.get("state", "open"),
                )
            else:
                # 未知事件类型兜底用通用 emit_trace
                full_payload = {"agent_id": agent_id, "node_id": context.node_id, **payload}
                await self.observer.emit_trace(context.node_id, event_type, full_payload)
        except Exception as e:
            # observer 失败不能影响 recovery 主流程
            logger.debug(f"[recovery] observer emit failed: {e}")
