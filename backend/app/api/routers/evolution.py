"""EvolutionProposal API Router — Agent 自我进化建议的人审与触发。

- GET  /api/evolution/proposals          — 查询建议列表（按状态过滤）
- GET  /api/evolution/proposals/{id}      — 查看建议详情（含 suggestion_md）
- POST /api/evolution/proposals/{id}/review — 人审操作（approve/reject）
- POST /api/evolution/reflect/{workflow_id} — 手动触发某个工作流的 LLM 复盘
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.db.models import (
    EvolutionProposal,
    EvolutionProposalStatus,
    FeedbackEvent,
    Workflow,
)
from app.db.session import get_db
from app.services.agent_evolution import trigger_reflection_async, review_proposal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/evolution", tags=["evolution"])


# ══════════════════════════════════════════════════════════
# Pydantic Schema
# ══════════════════════════════════════════════════════════

class ReviewDecision(BaseModel):
    """人审操作请求体"""
    decision: str = Field(..., description="审核决定", pattern="^(approve|reject)$")
    comment: Optional[str] = Field(None, max_length=500, description="审核备注（拒绝时建议填写原因）")


# ══════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════

def _proposal_to_dict(p: EvolutionProposal) -> dict:
    """将 ORM 对象转换为 API 响应 dict"""
    return {
        "id": p.id,
        "user_id": p.user_id,
        "workflow_id": p.workflow_id,
        "trigger_source": p.trigger_source,
        "trigger_reason": p.trigger_reason,
        "suggestion_md": p.suggestion_md,
        "status": p.status.value if hasattr(p.status, "value") else str(p.status),
        "review_comment": p.review_comment,
        "reviewed_at": p.reviewed_at.isoformat() if p.reviewed_at else None,
        "applied_at": p.applied_at.isoformat() if p.applied_at else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ══════════════════════════════════════════════════════════
# 端点
# ══════════════════════════════════════════════════════════

@router.get("/proposals", response_model=StandardResponse[dict])
async def list_proposals(
    status: Optional[str] = Query(
        None,
        description="按状态过滤：pending_review / approved / rejected，不传则返回全部"
    ),
    limit: int = Query(20, ge=1, le=100, description="返回数量上限"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """查询当前用户的 Agent 自我进化建议列表。

    按创建时间倒序返回。`status` 参数支持按状态过滤。
    列表项不含 `suggestion_md`（避免响应过大），需要查看详情请调
    GET /api/evolution/proposals/{id}。
    """
    stmt = (
        select(EvolutionProposal)
        .where(EvolutionProposal.user_id == user_id)
        .order_by(desc(EvolutionProposal.created_at))
    )

    # 状态过滤
    if status:
        try:
            status_enum = EvolutionProposalStatus(status)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"无效的状态值: {status}，有效值：pending_review / approved / rejected"
            )
        stmt = stmt.where(EvolutionProposal.status == status_enum)

    # 分页
    stmt = stmt.offset(offset).limit(limit)

    # 执行查询
    result = await db.execute(stmt)
    proposals = result.scalars().all()

    # 总数（用于前端分页）
    count_stmt = select(func.count(EvolutionProposal.id)).where(
        EvolutionProposal.user_id == user_id
    )
    if status:
        count_stmt = count_stmt.where(EvolutionProposal.status == status_enum)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 转换为响应格式（列表项不含 suggestion_md）
    items = []
    for p in proposals:
        d = _proposal_to_dict(p)
        d.pop("suggestion_md", None)
        items.append(d)

    return StandardResponse(
        data={"items": items, "total": total, "limit": limit, "offset": offset},
        message="查询成功"
    )


@router.get("/proposals/{proposal_id}", response_model=StandardResponse[dict])
async def get_proposal_detail(
    proposal_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """查看单条建议的完整详情（含 markdown 渲染的建议草稿）"""
    stmt = select(EvolutionProposal).where(
        EvolutionProposal.id == proposal_id,
        EvolutionProposal.user_id == user_id,
    )
    result = await db.execute(stmt)
    proposal = result.scalar_one_or_none()

    if not proposal:
        raise HTTPException(status_code=404, detail="建议不存在或无权访问")

    return StandardResponse(
        data=_proposal_to_dict(proposal),
        message="查询成功"
    )


@router.post("/proposals/{proposal_id}/review", response_model=StandardResponse[dict])
async def review_proposal_endpoint(
    proposal_id: str,
    payload: ReviewDecision,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """人审操作：approve（批准，将建议内容应用到 Agent 行为）或 reject（拒绝）。

    - approve：将建议标记为 approved，后续会注入 Agent 的行为系统
    - reject：将建议标记为 rejected，不会影响 Agent 行为

    审批过的建议不能再次审批（幂等保护）。
    """
    # 查找建议
    stmt = select(EvolutionProposal).where(
        EvolutionProposal.id == proposal_id,
        EvolutionProposal.user_id == user_id,
    )
    result = await db.execute(stmt)
    proposal = result.scalar_one_or_none()

    if not proposal:
        raise HTTPException(status_code=404, detail="建议不存在或无权访问")

    # 幂等检查：已审批过的建议不允许再次审批
    if proposal.status != EvolutionProposalStatus.PENDING_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"该建议已经过审核（当前状态: {proposal.status.value}），不允许重复审批"
        )

    # 更新状态
    proposal.review_comment = payload.comment

    if payload.decision == "approve":
        proposal.status = EvolutionProposalStatus.APPROVED
        proposal.reviewed_at = datetime.now(timezone.utc)
        proposal.applied_at = datetime.now(timezone.utc)
        message = "建议已批准，将在后续任务中应用到 Agent 行为"
    else:
        proposal.status = EvolutionProposalStatus.REJECTED
        proposal.reviewed_at = datetime.now(timezone.utc)
        message = "建议已拒绝"

    await db.commit()
    await db.refresh(proposal)

    return StandardResponse(
        data=_proposal_to_dict(proposal),
        message=message
    )


@router.post("/reflect/{workflow_id}", response_model=StandardResponse[dict])
async def trigger_reflection_endpoint(
    workflow_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """手动触发某个工作流的 LLM 复盘。

    通常用于：
    - 工作流成功完成但用户对结果不满意（无点踩但有隐含不满）
    - 想要针对特定工作流获取改进建议
    """
    # 验证工作流归属权
    stmt = select(Workflow).where(
        Workflow.id == workflow_id,
        Workflow.user_id == user_id,
    )
    result = await db.execute(stmt)
    workflow = result.scalar_one_or_none()

    if not workflow:
        raise HTTPException(status_code=404, detail="工作流不存在或无权访问")

    # 异步触发复盘（不阻塞 HTTP 响应）
    trigger_reflection_async(
        workflow_id=workflow_id,
        user_id=user_id,
        trigger_source="manual",
        trigger_reason="用户手动触发复盘"
    )

    return StandardResponse(
        data={"workflow_id": workflow_id, "reflection_triggered": True},
        message="复盘任务已触发，稍后可在建议列表中查看结果"
    )
