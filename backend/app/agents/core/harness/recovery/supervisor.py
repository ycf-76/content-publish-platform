"""监督 Agent Recovery 决策层（架构文档 6.4 + 手册 Phase 6 Part D）。

只在 RecoveryLoop 三次策略全失败后触发。
分类：
- 技术性恢复（模型过载/Token 过期）：自动执行，不打扰用户
- 结构性恢复（输入不足/链路问题）：用户拍板，启动 30min 超时
- 无法恢复：终止 + 告警

红线：
- 决策用 V3，不用 R1（红线 9 + 红线 4.1）
- 不让 LLM 决定重试次数（重试策略硬编码）
- 结构性恢复必须经用户确认（建议权）
- 30 分钟超时挂起（红线 4.1）
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.agents.adapters.llm_base import BaseLLM
    from app.agents.core.schemas import WorkflowContext

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 决策类型
# ----------------------------------------------------------------------


class RecoveryActionType(Enum):
    """Recovery 决策类型（架构文档 6.4）。"""
    TECHNICAL_RETRY = "technical_retry"          # 技术性：自动执行
    STRUCTURAL_ROLLBACK = "structural_rollback"  # 结构性：用户拍板
    TERMINATE = "terminate"                      # 终止


@dataclass
class RecoveryAction:
    """监督 Agent 输出的恢复动作。"""
    action_type: RecoveryActionType
    target_node: str | None = None           # 结构性回退的目标节点
    technical_params: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    require_user_confirm: bool = False       # True=用户拍板；False=自动执行
    timeout_seconds: int = 1800              # ★ 结构性恢复 30 分钟超时（D15）


# ----------------------------------------------------------------------
# crash_reason 分类映射（硬编码，不让 LLM 决定）
# ----------------------------------------------------------------------


# 技术性 crash_reason → 自动执行
_TECHNICAL_CRASH_REASONS: frozenset[str] = frozenset(
    {
        "model_overload",
        "model_timeout",
        "rate_limit",
        "timeout",
        "http_5xx",
        "http_429",
        "network_error",
        "token_expired",   # token 过期归技术性，自动刷新
    }
)

# 结构性 crash_reason → 用户拍板
_STRUCTURAL_CRASH_REASONS: frozenset[str] = frozenset(
    {
        "input_insufficient",
        "quality_check_failed",
        "empty_result",        # 空结果若发生在 analyze 节点，需回退到 search
        "image_gen_failed",
        "schema_validation_failed",
    }
)


# ----------------------------------------------------------------------
# SupervisorRecovery
# ----------------------------------------------------------------------


class SupervisorRecovery:
    """监督 Agent 恢复决策（Layer4）。

    使用 V3 模型，输入崩溃上下文，输出 RecoveryAction。
    当 LLM 不可用时降级为基于 crash_reason 的硬编码规则（保证可用性）。
    """

    SYSTEM_PROMPT = (
        "你是监督 Agent，负责在子 Agent 恢复循环耗尽后做恢复决策。\n"
        "严格遵守以下分类规则：\n"
        "- 技术性恢复（模型过载/Token 过期/网络超时）：自动执行，不打扰用户\n"
        "- 结构性恢复（输入不足/质量不达标/链路问题）：用户拍板，30分钟超时\n"
        "- 无法恢复：终止+告警\n"
        "只输出 STRICT JSON：\n"
        '{"action_type": "technical_retry|structural_rollback|terminate",'
        ' "target_node": "<node_id 或 null>",'
        ' "technical_params": {},'
        ' "reason": "<必填>",'
        ' "require_user_confirm": <bool>,'
        ' "timeout_seconds": 1800}'
    )

    def __init__(
        self,
        llm: BaseLLM | None = None,
        structural_recovery_timeout_seconds: int = 1800,
    ) -> None:
        self.llm = llm
        self.timeout_seconds = structural_recovery_timeout_seconds

    async def decide(
        self,
        crashed_node: str,
        crash_reason: str,
        crash_context: dict[str, Any] | None,
        context: WorkflowContext,
    ) -> RecoveryAction:
        """根据崩溃原因分类决策。"""
        # 1. 优先用硬编码规则（不依赖 LLM，保证可用性 + 红线"不让 LLM 决策"）
        action = self._rule_based_decision(crashed_node, crash_reason)
        if action is not None:
            logger.info(
                f"[supervisor] {crashed_node} rule-based: {action.action_type.value}"
            )
            return action

        # 2. LLM 兜底：未匹配规则的复杂场景
        if self.llm is not None:
            try:
                action = await self._llm_decision(
                    crashed_node, crash_reason, crash_context, context
                )
                logger.info(
                    f"[supervisor] {crashed_node} llm-based: {action.action_type.value}"
                )
                return action
            except Exception as e:
                logger.warning(f"[supervisor] LLM decision failed, fallback: {e}")

        # 3. 兜底：终止
        return RecoveryAction(
            action_type=RecoveryActionType.TERMINATE,
            reason=f"无法分类的崩溃: {crash_reason}",
            require_user_confirm=True,
            timeout_seconds=self.timeout_seconds,
        )

    # ------------------------------------------------------------------
    # 规则决策（硬编码，红线"不让 LLM 决策重试"）
    # ------------------------------------------------------------------

    def _rule_based_decision(
        self, crashed_node: str, crash_reason: str
    ) -> RecoveryAction | None:
        """基于 crash_reason 的硬编码分类。

        返回 None 表示该 crash_reason 不在硬编码列表里，需 LLM 兜底。
        """
        reason = (crash_reason or "").lower().strip()

        # 技术性：自动执行
        if reason in _TECHNICAL_CRASH_REASONS:
            if reason == "token_expired" and crashed_node == "publish":
                return RecoveryAction(
                    action_type=RecoveryActionType.TECHNICAL_RETRY,
                    target_node=crashed_node,
                    technical_params={"refresh_token_first": True},
                    reason="Token 过期，自动刷新后重试",
                    require_user_confirm=False,
                )
            # 模型过载/限流/超时 → 切 V3
            return RecoveryAction(
                action_type=RecoveryActionType.TECHNICAL_RETRY,
                target_node=crashed_node,
                technical_params={"force_model": "deepseek-v3"},
                reason=f"技术性故障（{reason}），自动切换到 V3 重试",
                require_user_confirm=False,
            )

        # 结构性：用户拍板
        if reason in _STRUCTURAL_CRASH_REASONS:
            target = self._structural_rollback_target(crashed_node, reason)
            return RecoveryAction(
                action_type=RecoveryActionType.STRUCTURAL_ROLLBACK,
                target_node=target,
                reason=self._structural_reason(crashed_node, reason, target),
                require_user_confirm=True,
                timeout_seconds=self.timeout_seconds,
            )

        return None

    @staticmethod
    def _structural_rollback_target(crashed_node: str, reason: str) -> str:
        """结构性回退的目标节点（硬编码路由，不让 LLM 决定）。"""
        # analyze 输入不足 → 回退到 search
        if crashed_node == "analyze":
            return "search"
        # image_gen 持续失败 → 回退到 analyze（重新生成视觉标签）
        if crashed_node == "image_gen":
            return "analyze"
        # copywrite 质量不达标 → 回退到 image_review（重新审核图片再写文案）
        if crashed_node == "copywrite":
            return "image_review"
        # audit 不达标 → 回退到 copywrite
        if crashed_node == "audit":
            return "copywrite"
        # publish 失败 → 回退到 final_review
        if crashed_node == "publish":
            return "final_review"
        # 默认：回退到上一个节点
        return crashed_node

    @staticmethod
    def _structural_reason(
        crashed_node: str, reason: str, target: str
    ) -> str:
        return (
            f"节点 {crashed_node} 触发结构性故障（{reason}），"
            f"建议回退到 {target} 重跑"
        )

    # ------------------------------------------------------------------
    # LLM 决策（兜底，仅用于未匹配规则的复杂场景）
    # ------------------------------------------------------------------

    async def _llm_decision(
        self,
        crashed_node: str,
        crash_reason: str,
        crash_context: dict[str, Any] | None,
        context: WorkflowContext,
    ) -> RecoveryAction:
        """用 V3 做复杂场景的恢复决策。"""
        user_prompt = (
            f"工作流 {context.workflow_id} 的节点 {crashed_node} 崩溃。\n"
            f"crash_reason: {crash_reason}\n"
            f"crash_context: {json.dumps(crash_context or {}, ensure_ascii=False)}\n"
            f"主题: {context.topic}\n"
            f"\n请按系统提示的 JSON schema 输出决策。"
        )

        result = await self.llm.chat(
            messages=[
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = result.get("content", "")
        return self._parse_llm_decision(content)

    def _parse_llm_decision(self, content: str) -> RecoveryAction:
        """解析 LLM 输出的 JSON 决策。"""
        text = content.strip()
        # 容忍 markdown fence
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # 截取首个 JSON 对象
            first = text.find("{")
            last = text.rfind("}")
            if first >= 0 and last > first:
                data = json.loads(text[first : last + 1])
            else:
                raise

        action_str = str(data.get("action_type", "")).lower().strip()
        try:
            action_type = RecoveryActionType(action_str)
        except ValueError:
            action_type = RecoveryActionType.TERMINATE

        return RecoveryAction(
            action_type=action_type,
            target_node=data.get("target_node") or None,
            technical_params=data.get("technical_params") or {},
            reason=str(data.get("reason", "")),
            require_user_confirm=bool(data.get("require_user_confirm", False)),
            timeout_seconds=int(data.get("timeout_seconds", self.timeout_seconds)),
        )
