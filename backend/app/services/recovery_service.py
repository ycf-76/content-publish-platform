"""Recovery Service（手册 Phase 6 Part D + Part F）。

封装 RecoveryLoop 耗尽后的全局编排逻辑：
1. handle_recovery_exhausted: 调用 SupervisorRecovery.decide
   - 技术性恢复 → 自动重跑（不打扰用户）
   - 结构性恢复 → 创建 pending_suggestion + 推送 supervisor_suggestion + 启动 30min 计时器
   - terminate   → 推送 workflow_error + 终止工作流
2. handle_user_confirm_suggestion: 用户确认/拒绝建议
   - confirm → 触发 LangGraph rollback（target_node）
   - reject  → terminate
3. resume_suspended_workflow: 用户主动恢复挂起的工作流
   - 取消 30min 计时器
   - 重新拉起工作流（从 current_node_id 续跑）

红线：
- 不让 LLM 决定重试次数（红线 4.1）
- 结构性恢复必须经用户确认（红线 4.1）
- 30 分钟超时挂起（红线 4.1）
- 监督决策用 V3（红线 9 + 4.1）
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.core.harness.recovery.supervisor import (
    RecoveryAction,
    RecoveryActionType,
    SupervisorRecovery,
)
from app.db.models import (
    NodeStatus,
    PendingSuggestion,
    SuggestionStatus,
    SuggestionType,
    SuggestionSeverity,
    Workflow,
    WorkflowNode,
    WorkflowStatus,
)
from app.services.sse_bus import sse_bus

if TYPE_CHECKING:
    from app.agents.adapters.llm_base import BaseLLM
    from app.agents.core.schemas import WorkflowContext

logger = logging.getLogger(__name__)


class RecoveryService:
    """Recovery 子系统的服务层编排器。

    每个工作流共享一个 RecoveryService 实例。
    通过 30min 计时器字典维护挂起任务的到期回调。
    """

    def __init__(
        self,
        db: AsyncSession,
        supervisor_llm: BaseLLM | None = None,
        structural_recovery_timeout_seconds: int = 1800,
    ) -> None:
        self.db = db
        self.supervisor = SupervisorRecovery(
            llm=supervisor_llm,
            structural_recovery_timeout_seconds=structural_recovery_timeout_seconds,
        )
        self.timeout_seconds = structural_recovery_timeout_seconds
        # workflow_id -> asyncio.Task（30min 超时计时器）
        self._suspension_timers: dict[str, asyncio.Task[None]] = {}

    # ------------------------------------------------------------------
    # Part D-1: RecoveryLoop 耗尽入口
    # ------------------------------------------------------------------

    async def handle_recovery_exhausted(
        self,
        workflow_id: str,
        node_id: str,
        crash_reason: str,
        crash_context: dict[str, Any] | None,
        context: WorkflowContext,
    ) -> RecoveryAction:
        """RecoveryLoop 三次策略全失败后的入口。

        步骤：
        1. 调 SupervisorRecovery.decide 得到 RecoveryAction
        2. 根据 action_type 分流：
           - TECHNICAL_RETRY     → 标记节点重跑（status=PENDING），推送 node_started
           - STRUCTURAL_ROLLBACK → 创建 pending_suggestion，推送 supervisor_suggestion，启动 30min 计时器
           - TERMINATE           → 推送 workflow_error，置 workflow.status=terminated
        """
        logger.warning(
            f"[recovery_service] workflow={workflow_id} node={node_id} "
            f"exhausted, crash_reason={crash_reason}"
        )

        action = await self.supervisor.decide(
            crashed_node=node_id,
            crash_reason=crash_reason,
            crash_context=crash_context,
            context=context,
        )

        if action.action_type is RecoveryActionType.TECHNICAL_RETRY:
            await self._handle_technical_retry(
                workflow_id, node_id, action, context
            )
        elif action.action_type is RecoveryActionType.STRUCTURAL_ROLLBACK:
            await self._handle_structural_rollback(
                workflow_id, node_id, action, context
            )
        else:
            await self._handle_terminate(workflow_id, node_id, action, context)

        return action

    # ------------------------------------------------------------------
    # Part D-2: 用户确认/拒绝建议
    # ------------------------------------------------------------------

    async def handle_user_confirm_suggestion(
        self,
        workflow_id: str,
        suggestion_id: str,
        decision: str,
    ) -> dict[str, Any]:
        """用户对 pending_suggestion 的拍板。

        Args:
            workflow_id: 工作流 ID
            suggestion_id: 建议 ID
            decision: "confirm" | "reject"

        Returns:
            {"success": bool, "action": str, "target_node": str | None}
        """
        stmt = select(PendingSuggestion).where(
            PendingSuggestion.id == suggestion_id,
            PendingSuggestion.workflow_id == workflow_id,
        )
        suggestion = await self.db.scalar(stmt)
        if suggestion is None:
            return {"success": False, "action": "not_found", "target_node": None}

        if suggestion.status != SuggestionStatus.pending:
            return {
                "success": False,
                "action": f"already_{suggestion.status.value}",
                "target_node": None,
            }

        # 取消 30min 计时器
        self._cancel_suspension_timer(workflow_id)

        now = datetime.now(UTC)
        if decision == "confirm":
            suggestion.status = SuggestionStatus.user_confirmed
            suggestion.resolved_at = now
            await self.db.commit()

            # 触发 LangGraph rollback：从 proposed_action.target_node 重跑
            target_node = self._extract_target_node(suggestion)
            await self._trigger_rollback(workflow_id, target_node)

            await sse_bus.publish(
                workflow_id,
                "suggestion_processed",
                {
                    "suggestion_id": suggestion_id,
                    "decision": "confirm",
                    "target_node": target_node,
                },
            )
            return {
                "success": True,
                "action": "rollback_triggered",
                "target_node": target_node,
            }

        if decision == "reject":
            suggestion.status = SuggestionStatus.user_rejected
            suggestion.resolved_at = now
            await self.db.commit()

            # 用户拒绝 → 终止工作流
            await self._terminate_workflow(workflow_id, reason="用户拒绝结构性恢复建议")
            await sse_bus.publish(
                workflow_id,
                "suggestion_processed",
                {
                    "suggestion_id": suggestion_id,
                    "decision": "reject",
                },
            )
            return {
                "success": True,
                "action": "workflow_terminated",
                "target_node": None,
            }

        return {"success": False, "action": "invalid_decision", "target_node": None}

    # ------------------------------------------------------------------
    # Part D-3: 用户主动恢复挂起的工作流
    # ------------------------------------------------------------------

    async def resume_suspended_workflow(
        self,
        workflow_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        """用户主动调 POST /api/workflows/{id}/resume-from-suspension。

        步骤：
        1. 取消 30min 计时器
        2. 校验 workflow 当前状态必须是 suspended
        3. 清空 suspended_until / suspension_reason
        4. 置 workflow.status = running
        5. 推送 workflow_resumed 事件
        6. 从 current_node_id 重新拉起（具体由 WorkflowService 调度）
        """
        workflow = await self._get_workflow(workflow_id, user_id)
        if workflow is None:
            return {"success": False, "message": "Workflow not found"}

        if workflow.status != WorkflowStatus.SUSPENDED:
            return {
                "success": False,
                "message": f"Workflow not suspended (status={workflow.status.value})",
            }

        # 1. 取消计时器
        self._cancel_suspension_timer(workflow_id)

        # 2. 清挂起字段 + 恢复 running
        workflow.suspended_until = None
        workflow.suspension_reason = None
        workflow.status = WorkflowStatus.RUNNING
        await self.db.commit()

        # 3. 推送恢复事件
        await sse_bus.publish(
            workflow_id,
            "workflow_resumed",
            {
                "workflow_id": workflow_id,
                "resumed_by": "user",
                "resumed_at": datetime.now(UTC).isoformat(),
                "resume_from_node": workflow.current_node_id,
            },
        )

        logger.info(
            f"[recovery_service] workflow={workflow_id} resumed by user, "
            f"from node={workflow.current_node_id}"
        )
        return {
            "success": True,
            "message": "Workflow resumed",
            "resume_from_node": workflow.current_node_id,
        }

    # ------------------------------------------------------------------
    # 内部：技术性恢复（自动执行，不打扰用户）
    # ------------------------------------------------------------------

    async def _handle_technical_retry(
        self,
        workflow_id: str,
        node_id: str,
        action: RecoveryAction,
        context: WorkflowContext,
    ) -> None:
        """技术性恢复：重置节点为 PENDING，等待调度器重跑。"""
        # 重置节点状态
        await self.db.execute(
            update(WorkflowNode)
            .where(
                WorkflowNode.workflow_id == workflow_id,
                WorkflowNode.node_key == node_id,
            )
            .values(
                status=NodeStatus.PENDING,
                error_message=None,
                recovery_attempts=0,
                # 把 supervisor 决策的技术参数（force_model 等）写进 input_data
                # 由后续 Executor 读取
            )
        )
        await self.db.commit()

        await sse_bus.publish(
            workflow_id,
            "recovery_action",
            {
                "workflow_id": workflow_id,
                "node_id": node_id,
                "action_type": "technical_retry",
                "technical_params": action.technical_params,
                "reason": action.reason,
                "require_user_confirm": False,
            },
        )
        logger.info(
            f"[recovery_service] technical retry scheduled for "
            f"workflow={workflow_id} node={node_id}"
        )

    # ------------------------------------------------------------------
    # 内部：结构性恢复（用户拍板 + 30min 计时）
    # ------------------------------------------------------------------

    async def _handle_structural_rollback(
        self,
        workflow_id: str,
        node_id: str,
        action: RecoveryAction,
        context: WorkflowContext,
    ) -> None:
        """结构性恢复：创建 pending_suggestion + 启动 30min 计时器。"""
        target_node = action.target_node or node_id

        # 1. 把当前节点状态置为 SUSPENDED
        await self.db.execute(
            update(WorkflowNode)
            .where(
                WorkflowNode.workflow_id == workflow_id,
                WorkflowNode.node_key == node_id,
            )
            .values(
                status=NodeStatus.SUSPENDED,
                crash_reason=action.reason,
            )
        )

        # 2. 创建 pending_suggestion 记录
        suggestion = PendingSuggestion(
            workflow_id=workflow_id,
            node_id=node_id,
            severity=SuggestionSeverity.error,
            suggestion_type=SuggestionType.structural,
            message=action.reason,
            trace={
                "crash_reason": context.extra.get("crash_reason", "") if context else "",
                "workflow_id": workflow_id,
                "node_id": node_id,
            },
            proposed_action={
                "target_node": target_node,
                "action_type": "structural_rollback",
                "technical_params": action.technical_params,
            },
            status=SuggestionStatus.pending,
        )
        self.db.add(suggestion)
        await self.db.commit()
        await self.db.refresh(suggestion)

        # 3. 推送 supervisor_suggestion 事件给前端
        await sse_bus.publish(
            workflow_id,
            "supervisor_suggestion",
            {
                "workflow_id": workflow_id,
                "node_id": node_id,
                "suggestion_id": suggestion.id,
                "severity": suggestion.severity.value,
                "suggestion_type": suggestion.suggestion_type.value,
                "message": action.reason,
                "target_node": target_node,
                "require_user_confirm": True,
                "timeout_seconds": self.timeout_seconds,
                "expires_at": (
                    datetime.now(UTC) + timedelta(seconds=self.timeout_seconds)
                ).isoformat(),
            },
        )

        # 4. 启动 30min 超时计时器
        self._start_suspension_timer(workflow_id, suggestion.id)

        logger.info(
            f"[recovery_service] structural rollback pending user decision: "
            f"workflow={workflow_id} node={node_id} target={target_node} "
            f"suggestion={suggestion.id}"
        )

    # ------------------------------------------------------------------
    # 内部：终止
    # ------------------------------------------------------------------

    async def _handle_terminate(
        self,
        workflow_id: str,
        node_id: str,
        action: RecoveryAction,
        context: WorkflowContext,
    ) -> None:
        """无法恢复：终止工作流 + 推送 workflow_error。"""
        await self._terminate_workflow(
            workflow_id, reason=action.reason or "Recovery 不可恢复，工作流终止"
        )
        await sse_bus.publish(
            workflow_id,
            "recovery_action",
            {
                "workflow_id": workflow_id,
                "node_id": node_id,
                "action_type": "terminate",
                "reason": action.reason,
            },
        )

    # ------------------------------------------------------------------
    # Part F: 30 分钟超时挂起计时器
    # ------------------------------------------------------------------

    def _start_suspension_timer(self, workflow_id: str, suggestion_id: str) -> None:
        """启动 30min 超时计时器。到点后挂起工作流。"""
        # 如果已有计时器，先取消
        self._cancel_suspension_timer(workflow_id)

        task = asyncio.create_task(
            self._suspension_timeout_callback(workflow_id, suggestion_id)
        )
        self._suspension_timers[workflow_id] = task
        logger.info(
            f"[recovery_service] suspension timer started: "
            f"workflow={workflow_id} timeout={self.timeout_seconds}s"
        )

    def _cancel_suspension_timer(self, workflow_id: str) -> None:
        """取消 30min 计时器（用户确认/拒绝/主动恢复时调用）。"""
        task = self._suspension_timers.pop(workflow_id, None)
        if task is not None and not task.done():
            task.cancel()
            logger.info(
                f"[recovery_service] suspension timer cancelled: "
                f"workflow={workflow_id}"
            )

    async def _suspension_timeout_callback(
        self,
        workflow_id: str,
        suggestion_id: str,
    ) -> None:
        """30min 超时回调：挂起工作流 + 释放资源。"""
        try:
            await asyncio.sleep(self.timeout_seconds)
        except asyncio.CancelledError:
            logger.info(
                f"[recovery_service] suspension timer cancelled: "
                f"workflow={workflow_id}"
            )
            return

        try:
            # 1. 标记 suggestion 超时
            await self.db.execute(
                update(PendingSuggestion)
                .where(
                    PendingSuggestion.id == suggestion_id,
                    PendingSuggestion.status == SuggestionStatus.pending,
                )
                .values(
                    status=SuggestionStatus.timeout,
                    resolved_at=datetime.now(UTC),
                )
            )

            # 2. 标记 workflow 挂起
            suspended_until = datetime.now(UTC) + timedelta(hours=24)
            await self.db.execute(
                update(Workflow)
                .where(Workflow.id == workflow_id)
                .values(
                    status=WorkflowStatus.SUSPENDED,
                    suspended_until=suspended_until,
                    suspension_reason=f"30min 超时挂起（suggestion={suggestion_id}）",
                )
            )
            await self.db.commit()

            # 3. 推送 workflow_suspended 事件
            await sse_bus.publish(
                workflow_id,
                "workflow_suspended",
                {
                    "workflow_id": workflow_id,
                    "suggestion_id": suggestion_id,
                    "reason": "30 分钟超时未确认",
                    "suspended_until": suspended_until.isoformat(),
                },
            )

            logger.warning(
                f"[recovery_service] workflow={workflow_id} suspended "
                f"after 30min timeout (suggestion={suggestion_id})"
            )
        except Exception as e:
            logger.error(
                f"[recovery_service] suspension timeout callback failed: {e}",
                exc_info=True,
            )
        finally:
            self._suspension_timers.pop(workflow_id, None)

    # ------------------------------------------------------------------
    # 内部：触发 LangGraph rollback
    # ------------------------------------------------------------------

    async def _trigger_rollback(
        self, workflow_id: str, target_node: str
    ) -> None:
        """触发 LangGraph checkpoint 回退到 target_node。

        MVP 实现：把 target_node 及其下游节点的 status 重置为 PENDING，
        真正的 LangGraph checkpoint 恢复由 WorkflowService.execute_graph 完成。
        """
        # 重置 target_node 及下游节点的状态
        # 这里按 node_type 顺序硬编码下游节点列表（与 graph.py 路由对齐）
        node_order = [
            "search",
            "analyze",
            "image_gen",
            "image_review",
            "copywrite",
            "audit",
            "final_review",
            "publish",
        ]
        try:
            start_idx = node_order.index(target_node)
        except ValueError:
            start_idx = 0

        downstream_keys = node_order[start_idx:]

        await self.db.execute(
            update(WorkflowNode)
            .where(
                WorkflowNode.workflow_id == workflow_id,
                WorkflowNode.node_key.in_(downstream_keys),
            )
            .values(
                status=NodeStatus.PENDING,
                error_message=None,
                crash_reason=None,
                recovery_attempts=0,
                started_at=None,
                completed_at=None,
            )
        )

        # 设置 workflow.current_node_id = target_node
        await self.db.execute(
            update(Workflow)
            .where(Workflow.id == workflow_id)
            .values(
                status=WorkflowStatus.RUNNING,
                current_node_id=target_node,
                suspended_until=None,
                suspension_reason=None,
            )
        )
        await self.db.commit()

        await sse_bus.publish(
            workflow_id,
            "workflow_rollback",
            {
                "workflow_id": workflow_id,
                "target_node": target_node,
                "triggered_by": "user_confirm",
            },
        )

        logger.info(
            f"[recovery_service] rollback triggered: workflow={workflow_id} "
            f"target={target_node} downstream={downstream_keys}"
        )

    # ------------------------------------------------------------------
    # 内部：终止工作流
    # ------------------------------------------------------------------

    async def _terminate_workflow(
        self, workflow_id: str, reason: str
    ) -> None:
        """置 workflow.status=terminated，取消计时器，推送 workflow_error。"""
        self._cancel_suspension_timer(workflow_id)

        await self.db.execute(
            update(Workflow)
            .where(Workflow.id == workflow_id)
            .values(
                status=WorkflowStatus.TERMINATED,
                suspension_reason=reason,
                completed_at=datetime.now(UTC),
            )
        )
        await self.db.commit()

        await sse_bus.publish(
            workflow_id,
            "workflow_error",
            {
                "workflow_id": workflow_id,
                "message": reason,
                "fatal": True,
            },
        )
        logger.warning(
            f"[recovery_service] workflow={workflow_id} terminated: {reason}"
        )

    # ------------------------------------------------------------------
    # 内部：DB 查询辅助
    # ------------------------------------------------------------------

    async def _get_workflow(
        self, workflow_id: str, user_id: str
    ) -> Workflow | None:
        stmt = select(Workflow).where(
            Workflow.id == workflow_id,
            Workflow.user_id == user_id,
        )
        return await self.db.scalar(stmt)

    @staticmethod
    def _extract_target_node(suggestion: PendingSuggestion) -> str:
        """从 pending_suggestion.proposed_action 提取 target_node。"""
        action = suggestion.proposed_action or {}
        return str(action.get("target_node") or suggestion.node_id or "")


def get_recovery_service(
    db: AsyncSession,
    supervisor_llm: BaseLLM | None = None,
) -> RecoveryService:
    """获取 RecoveryService 实例（由路由通过 Depends 注入）。"""
    return RecoveryService(db=db, supervisor_llm=supervisor_llm)
