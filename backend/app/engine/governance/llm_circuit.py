"""全局 LLM 熔断器 — 防止余额不足时继续烧钱。

核心问题：当 LLM API 余额不足（402）或认证失败（401/403）时，
如果不熔断，每个 tool/loop iteration 都会重复调用 LLM，
导致：
  - StreamRetryState 重试 3 次 × LoopExecutor 60 轮 = 180 次失败调用
  - ReAct Loop 里每个 tool 独立调 LLM，失败后继续下一轮
  - 充值后立即被新一轮循环烧光

解决方案：
  - 全局单例 LLMCircuitBreaker，所有 LLM 调用路径共享
  - 连续失败 N 次（默认 3）后熔断，拒绝后续所有 LLM 调用
  - 熔断后自动探针恢复：recovery_timeout 后进入 HALF_OPEN，
    允许试探调用；也可主动调 probe_and_recover() 发起探针
  - 不可恢复错误（402/401/403）立即熔断，不等 N 次
  - 探针成功后自动重置为 CLOSED，无需手动干预
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LLMCircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class LLMCircuitBreaker:
    """全局 LLM 熔断器（单例）。

    与 recovery/circuit_breaker.py 的 CircuitBreaker 区别：
    - CircuitBreaker 是 per-agent 的，用于 RecoveryLoop
    - LLMCircuitBreaker 是全局的，保护所有 LLM 调用路径
    - 不可恢复错误（402/401/403）立即熔断
    - 提供调用计数和花费估算
    - 支持 probe_and_recover()：主动探测 API 可用性，成功则自动重置
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._state = LLMCircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._half_open_inflight = 0
        self._total_calls = 0
        self._total_failures = 0
        self._last_error: str = ""
        self._open_reason: str = ""
        self._last_probe_time: float = 0
        self._probe_cooldown: float = 10.0

    @property
    def state(self) -> LLMCircuitState:
        return self._state

    @property
    def total_calls(self) -> int:
        return self._total_calls

    @property
    def total_failures(self) -> int:
        return self._total_failures

    @property
    def last_error(self) -> str:
        return self._last_error

    @property
    def open_reason(self) -> str:
        return self._open_reason

    def allow_request(self) -> bool:
        """是否允许发起 LLM 请求。"""
        if self._state == LLMCircuitState.CLOSED:
            return True
        if self._state == LLMCircuitState.OPEN:
            if time.time() - self._last_failure_time > self.recovery_timeout:
                self._state = LLMCircuitState.HALF_OPEN
                self._half_open_inflight = 0
                logger.info("[llm-circuit] OPEN -> HALF_OPEN (recovery timeout elapsed)")
                return True
            return False
        if self._state == LLMCircuitState.HALF_OPEN:
            if self._half_open_inflight < 1:
                self._half_open_inflight += 1
                return True
            return False
        return True

    def record_success(self) -> None:
        """记录一次成功的 LLM 调用。"""
        self._total_calls += 1
        self._failure_count = 0
        if self._state == LLMCircuitState.HALF_OPEN:
            self._state = LLMCircuitState.CLOSED
            self._half_open_inflight = 0
            logger.info("[llm-circuit] HALF_OPEN -> CLOSED (probe succeeded)")
        elif self._state == LLMCircuitState.OPEN:
            self._state = LLMCircuitState.CLOSED
            self._open_reason = ""
            logger.info("[llm-circuit] OPEN -> CLOSED (success recorded, auto-recovered)")

    def record_failure(self, error: str = "", is_unrecoverable: bool = False) -> None:
        """记录一次 LLM 调用失败。

        Args:
            error: 错误信息
            is_unrecoverable: 是否为不可恢复错误（402/401/403等），
                             如果是，立即熔断不等阈值
        """
        self._total_calls += 1
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.time()
        self._last_error = error[:500]

        if is_unrecoverable:
            self._state = LLMCircuitState.OPEN
            self._open_reason = f"unrecoverable: {error[:200]}"
            logger.error(
                f"[llm-circuit] -> OPEN immediately (unrecoverable): {error[:200]}"
            )
            return

        if self._state == LLMCircuitState.HALF_OPEN:
            self._state = LLMCircuitState.OPEN
            self._open_reason = f"half_open_probe_failed: {error[:200]}"
            logger.warning("[llm-circuit] HALF_OPEN -> OPEN (probe failed)")
            return

        if self._failure_count >= self.failure_threshold:
            self._state = LLMCircuitState.OPEN
            self._open_reason = f"consecutive_failures={self._failure_count}: {error[:200]}"
            logger.error(
                f"[llm-circuit] CLOSED -> OPEN "
                f"(consecutive failures={self._failure_count})"
            )

    def check_error(self, error: Exception | str) -> bool:
        """检查错误是否为不可恢复，并自动记录失败。

        Returns:
            True if the error is unrecoverable (caller should abort)
        """
        err_str = str(error).lower()
        is_unrecoverable = any(
            kw in err_str
            for kw in [
                "402", "401", "403",
                "payment", "insufficient balance",
                "unauthorized", "forbidden",
                "invalid api key", "authentication",
                "quota exceeded", "billing",
            ]
        )
        self.record_failure(
            error=str(error),
            is_unrecoverable=is_unrecoverable,
        )
        return is_unrecoverable

    async def probe_and_recover(self) -> dict[str, Any]:
        """主动探测 LLM API 可用性。成功则自动重置熔断器。

        探针逻辑：
        1. 如果熔断器 CLOSED，直接返回 ok（无需探针）
        2. 如果距上次探针不足 probe_cooldown(10s)，跳过
        3. 用当前配置的 API key 发一个 max_tokens=1 的极轻量请求
        4. 成功 → reset() → 返回 {recovered: true}
        5. 失败 → 保持 OPEN → 返回 {recovered: false, error: ...}

        Returns:
            dict with keys: ok, recovered, state, detail
        """
        if self._state == LLMCircuitState.CLOSED:
            return {"ok": True, "recovered": False, "state": "closed", "detail": "circuit already closed"}

        now = time.time()
        if now - self._last_probe_time < self._probe_cooldown:
            return {
                "ok": False,
                "recovered": False,
                "state": self._state.value,
                "detail": f"probe cooldown ({self._probe_cooldown}s), last probe {now - self._last_probe_time:.1f}s ago",
            }

        self._last_probe_time = now
        try:
            import os
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv("DEEPSEEK_API_KEY", "")
            api_base = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1").rstrip("/")
            model = os.getenv("DEEPSEEK_MODEL_V3", "deepseek-chat")

            if not api_key:
                return {"ok": False, "recovered": False, "state": self._state.value, "detail": "no API key configured"}

            import json
            import urllib.request
            url = f"{api_base}/chat/completions"
            body = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            }).encode()
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            })
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=15))
            data = json.loads(resp.read())
            if resp.status == 200 and data.get("choices"):
                old_state = self._state.value
                self.reset()
                logger.info(f"[llm-circuit] probe succeeded! {old_state} -> CLOSED (auto-recovered)")
                return {"ok": True, "recovered": True, "state": "closed", "detail": f"API probe succeeded, circuit recovered from {old_state}"}
            else:
                return {"ok": False, "recovered": False, "state": self._state.value, "detail": f"API returned status={resp.status}"}
        except Exception as e:
            err_str = str(e)
            self.check_error(e)
            return {"ok": False, "recovered": False, "state": self._state.value, "detail": f"probe failed: {err_str[:200]}"}

    def reset(self) -> None:
        """手动重置熔断器（用户充值/更换 API Key 后调用）。"""
        self._state = LLMCircuitState.CLOSED
        self._failure_count = 0
        self._half_open_inflight = 0
        self._open_reason = ""
        logger.info("[llm-circuit] manually reset to CLOSED")

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self._state.value,
            "failure_count": self._failure_count,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "last_error": self._last_error,
            "open_reason": self._open_reason,
            "recovery_timeout": self.recovery_timeout,
        }


_global_llm_circuit: LLMCircuitBreaker | None = None


def get_llm_circuit() -> LLMCircuitBreaker:
    """获取全局 LLM 熔断器单例。"""
    global _global_llm_circuit
    if _global_llm_circuit is None:
        _global_llm_circuit = LLMCircuitBreaker()
    return _global_llm_circuit


def reset_llm_circuit() -> None:
    """重置全局 LLM 熔断器（用户充值/更换 API Key 后调用）。"""
    get_llm_circuit().reset()