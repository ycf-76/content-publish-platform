"""Recovery 子系统（架构文档 4.4 + PRD D15 + 红线 4）。

红线：
- max_attempts=3 + 智能退避 + 熔断
- 技术性恢复自动执行，结构性恢复用户拍板
- 30 分钟超时挂起
- 重试策略硬编码（不让 LLM 决策）
- Recovery 策略配置化（YAML）
"""

from app.engine.harness.recovery.backoff import BackoffPolicy
from app.engine.harness.recovery.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)
from app.engine.harness.recovery.loop import RecoveryLoop
from app.engine.harness.recovery.strategies import (
    BroadenKeywordStrategy,
    ReduceInputStrategy,
    RefreshTokenStrategy,
    RecoveryStrategy,
    RetryStrategy,
    SimplifyPromptStrategy,
    SwitchModelStrategy,
    from_config,
    from_config_list,
)
from app.engine.harness.recovery.supervisor import (
    RecoveryAction,
    RecoveryActionType,
    SupervisorRecovery,
)

__all__ = [
    # 退避
    "BackoffPolicy",
    # 熔断
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    # 策略
    "RecoveryStrategy",
    "RetryStrategy",
    "BroadenKeywordStrategy",
    "ReduceInputStrategy",
    "SimplifyPromptStrategy",
    "SwitchModelStrategy",
    "RefreshTokenStrategy",
    "from_config",
    "from_config_list",
    # 主循环
    "RecoveryLoop",
    # 监督决策
    "SupervisorRecovery",
    "RecoveryAction",
    "RecoveryActionType",
]
