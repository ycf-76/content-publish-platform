"""任务清单 API 路由（多日定时发布）。

POST   /api/task-plans/decompose   意图拆解预览（dry_run=true 时不调 LLM，零 token 测试）
POST   /api/task-plans             创建并激活清单（items 为用户确认后的最终清单）
GET    /api/task-plans             列表
GET    /api/task-plans/{id}        详情（逐日条目 + 执行记录）
POST   /api/task-plans/{id}/pause   暂停
POST   /api/task-plans/{id}/resume  恢复
POST   /api/task-plans/{id}/cancel  取消
"""
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.db.session import get_db
from app.services.task_plan import TaskPlanService, decompose_intent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/task-plans", tags=["task-plans"])


class DecomposeRequest(BaseModel):
    """意图拆解请求。"""
    intent_text: str = Field(..., min_length=1, max_length=5000, description="发布意图（多行清单或一句话）")
    daily_time: str | None = Field(None, description="每日发布时间 HH:MM，如 09:00")
    dry_run: bool = Field(False, description="True 时不调用 LLM（规则拆解，零 token 测试路径）")


class CreatePlanItem(BaseModel):
    """清单条目（用户编辑后的最终版）。"""
    day_index: int = Field(..., ge=1, le=60)
    topic: str = Field(..., min_length=1, max_length=500)
    keyword: str | None = Field(None, max_length=200)


class CreatePlanRequest(BaseModel):
    """创建清单请求。"""
    intent_text: str = Field(..., min_length=1, max_length=5000)
    title: str = Field("", max_length=200)
    account_id: str | None = Field(None, description="小红书账号 ID")
    items: list[CreatePlanItem] = Field(..., min_length=1, max_length=60)
    plan_config: dict | None = Field(
        None,
        description=(
            "{daily_time, review_mode: quality_gate|auto|manual, "
            "model_settings, confirm_timeout_min, max_retry, feishu_open_id}"
        ),
    )


@router.post("/decompose")
async def decompose(
    request: DecomposeRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """意图拆解预览（无副作用，不落库）。

    返回 {title, daily_time, total_days, items, warnings}，
    前端展示可编辑预览表，用户确认后调 POST /api/task-plans。
    """
    data = await decompose_intent(
        intent_text=request.intent_text,
        daily_time=request.daily_time,
        dry_run=request.dry_run,
    )
    return StandardResponse(data=data)


@router.post("")
async def create_plan(
    request: CreatePlanRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict[str, Any]]:
    """创建并激活清单（调度器将按 plan_time 逐日自动执行）。"""
    # 服务端兜底校验（前端也应校验）
    day_indexes = [it.day_index for it in request.items]
    if sorted(day_indexes) != list(range(1, len(day_indexes) + 1)):
        raise HTTPException(status_code=400, detail="day_index 必须从 1 开始连续递增")

    service = TaskPlanService(db)
    plan = await service.create_plan(
        user_id=user_id,
        intent_text=request.intent_text,
        items=[it.model_dump() for it in request.items],
        plan_config=request.plan_config,
        account_id=request.account_id,
        title=request.title,
    )
    return StandardResponse(
        data={"id": plan.id, "total_days": plan.total_days, "status": plan.status.value},
        message="清单已创建并生效",
    )


@router.get("")
async def list_plans(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[list[dict[str, Any]]]:
    """清单列表（含进度统计）。"""
    service = TaskPlanService(db)
    data = await service.list_plans(user_id)
    return StandardResponse(data=data)


@router.get("/{plan_id}")
async def get_plan_detail(
    plan_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict[str, Any]]:
    """清单详情（逐日条目 timeline + 最近执行记录）。"""
    service = TaskPlanService(db)
    detail = await service.get_plan_detail(user_id, plan_id)
    if not detail:
        raise HTTPException(status_code=404, detail="清单不存在")
    return StandardResponse(data=detail)


@router.post("/{plan_id}/pause")
async def pause_plan(
    plan_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict[str, Any]]:
    """暂停清单（执行中的当日任务不受影响，后续停止调度）。"""
    service = TaskPlanService(db)
    ok = await service.pause_plan(user_id, plan_id)
    if not ok:
        raise HTTPException(status_code=400, detail="暂停失败（清单不存在或非 active 状态）")
    return StandardResponse(data={"id": plan_id, "status": "paused"}, message="清单已暂停")


@router.post("/{plan_id}/resume")
async def resume_plan(
    plan_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict[str, Any]]:
    """恢复暂停的清单。"""
    service = TaskPlanService(db)
    ok = await service.resume_plan(user_id, plan_id)
    if not ok:
        raise HTTPException(status_code=400, detail="恢复失败（清单不存在或非 paused 状态）")
    return StandardResponse(data={"id": plan_id, "status": "active"}, message="清单已恢复")


@router.post("/{plan_id}/cancel")
async def cancel_plan(
    plan_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict[str, Any]]:
    """取消清单（未执行条目全部取消，不可恢复）。"""
    service = TaskPlanService(db)
    ok = await service.cancel_plan(user_id, plan_id)
    if not ok:
        raise HTTPException(status_code=400, detail="取消失败（清单不存在或已终态）")
    return StandardResponse(data={"id": plan_id, "status": "cancelled"}, message="清单已取消")
