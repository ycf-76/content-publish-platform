"""智能退避策略（架构文档 4.4.2）。

指数退避 + 抖动，避免雪崩式重试打爆下游服务。
红线：
- max_delay 上限 30s（D15 + 红线 4.1）
- jitter 必须开启（避免多 Agent 同步重试）
- 不引入外部依赖
"""

from __future__ import annotations

import random


class BackoffPolicy:
    """指数退避 + 抖动。

    delay = min(base_delay * 2^attempt, max_delay) + jitter(0~10%)
    attempt 从 0 开始。
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: bool = True,
    ) -> None:
        if base_delay < 0 or max_delay < 0:
            raise ValueError("delays must be non-negative")
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def next_delay(self, attempt: int) -> float:
        """计算第 attempt 次重试的延迟秒数（attempt 从 0 开始）。"""
        if attempt < 0:
            attempt = 0
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        if self.jitter:
            # 0~10% 抖动（与架构文档 4.4.2 一致）
            delay += random.uniform(0, delay * 0.1)
        return delay

    # 兼容手册 Phase 6 里的方法名（compute_delay / next_delay 同义）
    compute_delay = next_delay
