"""Feedback Event Router.

记录用户对智能体回复的反馈事件（点赞/点踩/重试），并聚合出重试率。
这是「任务监控 + Agent 自我进化」体系的第一阶段：先把反馈管道打通、落库、可归因。

- POST /api/feedback：记录一次反馈事件
- GET  /api/feedback/stats：聚合反馈统计（赞/踩分布、踩的维度分布、重试率）
- GET  /api/feedback/workflow/{id}：按工作流归因查询反馈
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])

# ════════════════════════════════════════════════════════════════════
# Pydantic Schema
# ════════════════════════════════════════════════════════════════════

class FeedbackType(str, Enum):
    """反馈类型：赞 / 踩 / 重试。"""
    LIKE = "like"
    DISLIKE = "dislike"
    RETRY = "retry"


class FeedbackEventCreate(BaseModel):
    """记录一次反馈事件。"""

    # 反馈类型：like（赞）/ dislike（踩）/ retry（重试）
    type: FeedbackType = Field(..., description="反馈类型")
    # 关联的会话 ID（可空）
    session_id: Optional[str] = Field(None, max_length=26, description="关联的会话 ID")
    # 关联的工作流 ID（可空，用于按工作流归因）
    workflow_id: Optional[str] = Field(None, max_length=26, description="关联的工作流 ID")
    # 点踩的维度（仅 type=dislike 时必填）
    dimension: Optional[str] = Field(None, max_length=64, description="点踩的维度标签")


# ══════════════════════════════════════════════════════════════════
# Core logic
# ══════════════════════════════════════════════════════════════════

async def create_feedback_event(
    user_id: str,
    payload: FeedbackEventCreate,
    db: AsyncSession,
) -> FeedbackEvent:
    """创建反馈事件（核心逻辑）。

    ⚡ 踩（dislike）且带 workflow_id 时，自动异步触发一次 Agent 复盘
    （用户对产出结果不满意 → LLM 分析执行轨迹生成改进建议）。
    复盘异步执行，不阻塞反馈落库；同一 workflow 幂等去重。
    """
    from app.db.models import FeedbackEvent, FeedbackEventType as DBFeedbackEventType

    event_type = DBFeedbackEventType(payload.type)

    if event_type == DBFeedbackEventType.DISLIKE and not payload.dimension:
        raise HTTPException(
            status_code=422,
            detail="点踩反馈必须提供维度（dimension）。",
        )

    try:
        event = FeedbackEvent(
            user_id=user_id,
            workflow_id=payload.workflow_id,
            session_id=payload.session_id,
            event_type=event_type,
            dimension=payload.dimension,
        )
        db.add(event)
        await db.commit()
        await db.refresh(event)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail="反馈事件创建失败（数据库约束冲突）")

    # ⚡ 点踩且关联了工作流 → 异步触发 Agent 复盘（自我进化信号）
    if (
        event_type == DBFeedbackEventType.DISLIKE
        and payload.workflow_id
        and payload.dimension
    ):
        try:
            from app.services.agent_evolution import trigger_reflection_async
            trigger_reflection_async(
                payload.workflow_id,
                user_id,
                trigger_source="auto_dislike",
                trigger_reason=f"用户对结果点了「{payload.dimension}」的踩",
            )
        except Exception:
            logger.exception("点踩触发的 Agent 复盘失败（不影响反馈落库）")

    return event


# ════════════════════════════════════════════════════════════════════
# Endpoints
# ════════════════════════════════════════════════════════════════════

@router.post("", response_model=StandardResponse[dict])
async def record_feedback(
    payload: FeedbackEventCreate,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """记录一次反馈事件（点赞/点踩/重试）。"""
    from app.db.models import FeedbackEvent

    event = await create_feedback_event(user_id, payload, db)

    return StandardResponse(
        data={
            "id": event.id,
            "type": event.event_type.value,
            "workflow_id": event.workflow_id,
            "session_id": event.session_id,
            "dimension": event.dimension,
            "created_at": event.created_at.isoformat() if event.created_at else None,
        },
        message="反馈已记录",
    )


@router.delete("/{feedback_id}", response_model=StandardResponse[dict])
async def delete_feedback(
    feedback_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """删除一条反馈事件。

    用于「取消点赞/取消点踩」的场景：
    - 前端点击已点赞的消息会取消点赞（发送 like → 再发送删除请求）
    - 或直接调用 DELETE 删除对应事件
    """
    from app.db.models import FeedbackEvent

    result = await db.execute(
        delete(FeedbackEvent).where(
            FeedbackEvent.id == feedback_id,
            FeedbackEvent.user_id == user_id,
        )
    )
    await db.commit()

    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="反馈事件不存在或无权删除")

    return StandardResponse(data={"deleted": True}, message="反馈已删除")


@router.get("/stats", response_model=StandardResponse[dict])
async def get_feedback_stats(
    user_id: str = Depends(get_current_user),
    days: int = Query(default=7, ge=1, le=90, description="统计时间范围（天）"),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """聚合反馈统计。

    - 总赞数 / 总踩数 / 总重试数
    - 重试率 = 重试数 / (重试数 + 正常完成数)
    - 踩的维度分布（哪些维度被踩得最多）
    """
    from app.db.models import (
        FeedbackEvent,
        FeedbackEventType,
        Workflow,
        WorkflowStatus,
    )

    since = datetime.utcnow() - timedelta(days=days)

    # ─── 1. 反馈事件聚合 ───
    stmt = (
        select(FeedbackEvent.event_type, func.count(FeedbackEvent.id))
        .where(
            FeedbackEvent.user_id == user_id,
            FeedbackEvent.created_at >= since,
        )
        .group_by(FeedbackEvent.event_type)
    )
    result = await db.execute(stmt)
    event_counts = {row[0].value: row[1] for row in result.fetchall()}

    likes = event_counts.get(FeedbackEventType.LIKE.value, 0)
    dislikes = event_counts.get(FeedbackEventType.DISLIKE.value, 0)
    retries = event_counts.get(FeedbackEventType.RETRY.value, 0)

    # ─── 2. 重试率计算 ───
    # 分母 = 重试事件数 + 正常完成的 workflow 数（同一时间窗口内）
    completed_workflows_stmt = select(func.count(Workflow.id)).where(
        Workflow.user_id == user_id,
        Workflow.created_at >= since,
        Workflow.status == WorkflowStatus.COMPLETED,
    )
    completed_result = await db.execute(completed_workflows_stmt)
    completed_workflows = completed_result.scalar() or 0

    denominator = retries + completed_workflows
    retry_rate = (retries / denominator) if denominator > 0 else 0.0

    # ─── 3. 踩的维度分布 ───
    dimension_stmt = (
        select(FeedbackEvent.dimension, func.count(FeedbackEvent.id))
        .where(
            FeedbackEvent.user_id == user_id,
            FeedbackEvent.created_at >= since,
            FeedbackEvent.event_type == FeedbackEventType.DISLIKE,
            FeedbackEvent.dimension.isnot(None),
        )
        .group_by(FeedbackEvent.dimension)
        .order_by(func.count(FeedbackEvent.id).desc())
    )
    dimension_result = await db.execute(dimension_stmt)
    dimension_distribution = {row[0]: row[1] for row in dimension_result.fetchall()}

    # ─── 4. 会话总数（用于辅助计算会话级重试率） ───
    sessions_stmt = select(func.count(func.distinct(FeedbackEvent.session_id))).where(
        FeedbackEvent.user_id == user_id,
        FeedbackEvent.created_at >= since,
    )
    sessions_result = await db.execute(sessions_stmt)
    affected_sessions = sessions_result.scalar() or 0

    return StandardResponse(
        data={
            "time_range_days": days,
            "likes": likes,
            "dislikes": dislikes,
            "retries": retries,
            "retry_rate": round(retry_rate, 4),
            "completed_workflows": completed_workflows,
            "dislike_dimensions": dimension_distribution,
            "affected_sessions": affected_sessions,
        },
        message="统计成功",
    )


@router.get("/workflow/{workflow_id}", response_model=StandardResponse[list])
async def get_workflow_feedback(
    workflow_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[list]:
    """查询某工作流收到的所有反馈事件（按时间正序）。"""
    from app.db.models import FeedbackEvent

    stmt = (
        select(FeedbackEvent)
        .where(
            FeedbackEvent.workflow_id == workflow_id,
            FeedbackEvent.user_id == user_id,
        )
        .order_by(FeedbackEvent.created_at.asc())
    )
    result = await db.execute(stmt)
    events = result.scalars().all()

    return StandardResponse(
        data=[
            {
                "id": e.id,
                "type": e.event_type.value,
                "dimension": e.dimension,
                "session_id": e.session_id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]
    )
