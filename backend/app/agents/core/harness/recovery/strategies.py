"""Recovery 策略库（架构文档 4.4.4 + 手册 Phase 6 Part B）。

6 种策略：
1. RetryStrategy             — 原样重试（瞬时错误）
2. BroadenKeywordStrategy    — 拓宽搜索关键词（结果为空）
3. ReduceInputStrategy       — 减少输入数据量（输入过长）
4. SimplifyPromptStrategy    — 简化 prompt（R1 因复杂要求崩溃）
5. SwitchModelStrategy       — 切备用模型（模型过载/不可用）
6. RefreshTokenStrategy      — 刷新小红书 Token（发布时 token 过期）

红线：
- 策略只调整输入/上下文，不直接调 LLM / MCP
- 每个策略可独立测试
- 工厂 from_config() 从 YAML 读取策略配置（红线 4.2 配置化）
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agents.core.schemas import WorkflowContext

logger = logging.getLogger(__name__)


class RecoveryStrategy(ABC):
    """恢复策略接口：调整输入/参数后重试。"""

    name: str = "abstract"

    @abstractmethod
    def adjust(
        self,
        input: dict[str, Any],
        context: WorkflowContext,
        last_error: Exception | None = None,
    ) -> tuple[dict[str, Any], WorkflowContext]:
        """返回调整后的 (input, context)。

        不修改原对象（不可变约定）。
        """
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        """返回该策略的可读描述（用于 trace 事件）。"""
        return {"name": self.name}


# ----------------------------------------------------------------------
# 策略 1: 原样重试
# ----------------------------------------------------------------------


class RetryStrategy(RecoveryStrategy):
    """策略1：原样重试（应对网络抖动等瞬时错误）。"""

    name = "retry"

    def adjust(
        self,
        input: dict[str, Any],
        context: WorkflowContext,
        last_error: Exception | None = None,
    ) -> tuple[dict[str, Any], WorkflowContext]:
        return input, context


# ----------------------------------------------------------------------
# 策略 2: 拓宽搜索关键词
# ----------------------------------------------------------------------


class BroadenKeywordStrategy(RecoveryStrategy):
    """策略2：拓宽搜索关键词（应对搜索结果为空）。

    规则（硬编码，不让 LLM 决策）：
    - 去掉 keyword 中的限定词（如 "科技类" -> "科技"）
    - 去掉引号、特殊符号
    - 兜底返回原词
    """

    name = "broaden_keyword"

    def adjust(
        self,
        input: dict[str, Any],
        context: WorkflowContext,
        last_error: Exception | None = None,
    ) -> tuple[dict[str, Any], WorkflowContext]:
        keyword = str(input.get("keyword") or input.get("topic") or "")
        new_keyword = self._broaden(keyword)
        if new_keyword and new_keyword != keyword:
            logger.info(f"[broaden_keyword] {keyword!r} -> {new_keyword!r}")
            return {**input, "keyword": new_keyword}, context
        return input, context

    @staticmethod
    def _broaden(keyword: str) -> str:
        """简化关键词。"""
        if not keyword:
            return keyword
        # 去掉常见后缀"类 / 主题 / 内容"
        for suffix in ("类", "主题", "内容", "方向"):
            if keyword.endswith(suffix) and len(keyword) > len(suffix):
                return keyword[: -len(suffix)]
        # 去掉引号
        return keyword.strip("\"'""''")


# ----------------------------------------------------------------------
# 策略 3: 减少输入数据量
# ----------------------------------------------------------------------


class ReduceInputStrategy(RecoveryStrategy):
    """策略2'：减少输入量（应对输入过长导致 LLM 崩溃）。

    按字段名 notes / results / items / images 截断。
    """

    name = "reduce_input"

    def __init__(self, max_items: int = 5) -> None:
        if max_items < 1:
            raise ValueError("max_items must be >= 1")
        self.max_items = max_items

    def adjust(
        self,
        input: dict[str, Any],
        context: WorkflowContext,
        last_error: Exception | None = None,
    ) -> tuple[dict[str, Any], WorkflowContext]:
        for key in ("notes", "results", "items", "images", "images_base64"):
            v = input.get(key)
            if isinstance(v, list) and len(v) > self.max_items:
                logger.info(
                    f"[reduce_input] {key}: {len(v)} -> {self.max_items}"
                )
                input = {**input, key: v[: self.max_items]}
        return input, context

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "max_items": self.max_items}


# ----------------------------------------------------------------------
# 策略 4: 简化 prompt
# ----------------------------------------------------------------------


class SimplifyPromptStrategy(RecoveryStrategy):
    """策略2''：简化 prompt（应对 R1 因复杂要求崩溃）。

    通过 context.extra.use_simplified_prompt 标记，由 Executor 决定是否使用简化版。
    """

    name = "simplify_prompt"

    def adjust(
        self,
        input: dict[str, Any],
        context: WorkflowContext,
        last_error: Exception | None = None,
    ) -> tuple[dict[str, Any], WorkflowContext]:
        new_extra = {**context.extra, "use_simplified_prompt": True}
        new_ctx = context.model_copy(update={"extra": new_extra})
        logger.info(f"[simplify_prompt] flagged for {context.node_id}")
        return input, new_ctx


# ----------------------------------------------------------------------
# 策略 5: 切换备用模型
# ----------------------------------------------------------------------


class SwitchModelStrategy(RecoveryStrategy):
    """策略3：切备用模型（应对模型过载/不可用）。

    通过 context.extra.force_model 标记，由 Executor 决定用哪个模型。
    """

    name = "switch_model"

    def __init__(self, fallback: str = "deepseek-v3") -> None:
        if not fallback:
            raise ValueError("fallback model must be specified")
        self.fallback = fallback

    def adjust(
        self,
        input: dict[str, Any],
        context: WorkflowContext,
        last_error: Exception | None = None,
    ) -> tuple[dict[str, Any], WorkflowContext]:
        new_extra = {**context.extra, "force_model": self.fallback}
        new_ctx = context.model_copy(update={"extra": new_extra})
        logger.info(f"[switch_model] force_model={self.fallback} for {context.node_id}")
        return input, new_ctx

    def describe(self) -> dict[str, Any]:
        return {"name": self.name, "fallback": self.fallback}


# ----------------------------------------------------------------------
# 策略 6: 刷新小红书 Token
# ----------------------------------------------------------------------


class RefreshTokenStrategy(RecoveryStrategy):
    """策略4：刷新小红书 Token（应对 publish 时 token 过期）。

    通过 context.extra.refresh_token_first 标记，由 XhsPublishSkill 在 execute
    前主动刷新。仅对 publish 节点生效，其他节点原样返回。
    """

    name = "refresh_token"

    def adjust(
        self,
        input: dict[str, Any],
        context: WorkflowContext,
        last_error: Exception | None = None,
    ) -> tuple[dict[str, Any], WorkflowContext]:
        if context.node_id != "publish":
            return input, context
        new_extra = {**context.extra, "refresh_token_first": True}
        new_ctx = context.model_copy(update={"extra": new_extra})
        logger.info(f"[refresh_token] flagged for publish node")
        return input, new_ctx


# ----------------------------------------------------------------------
# 工厂：从 YAML 配置构建策略
# ----------------------------------------------------------------------


_STRATEGY_REGISTRY: dict[str, type[RecoveryStrategy]] = {
    "retry": RetryStrategy,
    "broaden_keyword": BroadenKeywordStrategy,
    "reduce_input": ReduceInputStrategy,
    "simplify_prompt": SimplifyPromptStrategy,
    "switch_model": SwitchModelStrategy,
    "refresh_token": RefreshTokenStrategy,
}


def from_config(strategy_config: dict[str, Any]) -> RecoveryStrategy:
    """从 YAML 配置 dict 构建单个策略。

    配置示例（与红线 4.2 对齐）：
        {"type": "switch_model", "fallback_model": "deepseek-v3"}
        {"type": "reduce_input", "max_items": 5}
    """
    cfg = dict(strategy_config or {})
    s_type = str(cfg.pop("type", "")).strip().lower()
    if not s_type:
        raise ValueError("strategy config missing 'type'")

    cls = _STRATEGY_REGISTRY.get(s_type)
    if cls is None:
        raise ValueError(
            f"unknown recovery strategy: {s_type!r}, "
            f"available: {sorted(_STRATEGY_REGISTRY)}"
        )

    # 字段名兼容（YAML 里写 fallback_model / Python __init__ 用 fallback）
    if s_type == "switch_model" and "fallback_model" in cfg:
        cfg["fallback"] = cfg.pop("fallback_model")

    try:
        return cls(**cfg)
    except TypeError as e:
        raise ValueError(f"invalid config for {s_type}: {e}") from e


def from_config_list(configs: list[dict[str, Any]]) -> list[RecoveryStrategy]:
    """从策略列表配置构建策略列表。"""
    return [from_config(c) for c in (configs or [])]
