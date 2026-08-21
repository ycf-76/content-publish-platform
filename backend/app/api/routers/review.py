"""Review routers.

人工审核 API：
- POST /api/workflows/{id}/review：提交审核结果（pass/reject）
  - pass: 恢复工作流执行（graph.astream(None, config) resume）
  - reject: 终止工作流

- GET /api/workflows/{id}/review/pending：获取待审核信息

卡片编辑器注入 API：
- POST /api/workflows/{id}/inject-card-images：前端卡片编辑器出图后注入图片
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.api.schemas.review import ReviewActionRequest
from app.db.session import get_db
from app.services.workflow import get_workflow_service

router = APIRouter(prefix="/api/workflows", tags=["review"])


class InjectCardImagesRequest(BaseModel):
    """前端卡片编辑器注入图片的请求体。"""
    images_base64: list[str]
    image_details: list[dict] | None = None
    style: str = ""
    plan_context: dict | None = None


@router.post("/{workflow_id}/review")
async def submit_review(
    workflow_id: str,
    request: ReviewActionRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """提交人工审核结果。

    用于 image_review 和 final_review 节点的人工审核：
    - 工作流在审核节点前 interrupt 暂停
    - 用户审核后调用此 API
    - action=pass: 恢复工作流，继续执行后续节点
    - action=reject: 终止工作流
    """
    service = get_workflow_service(db)

    result = await service.submit_review(
        workflow_id=workflow_id,
        action=request.action,
        user_id=user_id,
        feedback=request.feedback,
        selected_candidate=request.selected_candidate,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Review failed"))

    return StandardResponse(data=result, message=result.get("message", ""))


@router.get("/{workflow_id}/review/pending")
async def get_pending_review(
    workflow_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """获取当前待审核信息（轮询兜底接口）。

    前端在 SSE 不可靠时可通过此接口轮询审核状态。
    返回当前是否处于审核等待状态，以及审核类型。
    """
    from app.services.sse_bus import sse_bus

    events = sse_bus._event_history.get(workflow_id, [])
    # 找最新的 review_required 事件
    latest_review_required = None
    latest_review_processed = None
    for event in events:
        if event.event_type == "review_required":
            latest_review_required = event.payload
        elif event.event_type == "review_processed":
            latest_review_processed = event.payload

    # 如果有 review_required 但没有对应的 review_processed，说明在等待审核
    is_pending = bool(latest_review_required) and not latest_review_processed

    return StandardResponse(data={
        "workflow_id": workflow_id,
        "is_pending": is_pending,
        "review_required": latest_review_required or {},
        "review_processed": latest_review_processed or {},
    })


# 保留旧接口兼容性（review_id 路径参数，简化为统一调用 submit_review）
@router.post("/{workflow_id}/reviews/{review_id}")
async def process_review_legacy(
    workflow_id: str,
    review_id: str,
    request: ReviewActionRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """Legacy review endpoint（保留兼容性）."""
    service = get_workflow_service(db)

    result = await service.submit_review(
        workflow_id=workflow_id,
        action=request.action,
        user_id=user_id,
        feedback=request.feedback,
        selected_candidate=request.selected_candidate,
    )

    return StandardResponse(
        data={"review_id": review_id, **result},
        message=result.get("message", "")
    )


@router.post("/{workflow_id}/inject-card-images")
async def inject_card_images(
    workflow_id: str,
    request: InjectCardImagesRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """前端卡片编辑器出图后，注入图片到 image_gen 节点并 resume 工作流。

    工作流在 image_plan 完成后、image_gen 前 interrupt 暂停。
    前端用 html2canvas 生成卡片图片，调本接口注入：
    - 把图片 base64 写入 state（node_outputs['image_gen']）
    - resume 工作流，image_gen_node 透传图片到 image_review
    """
    service = get_workflow_service(db)

    result = await service.inject_card_images(
        workflow_id=workflow_id,
        images_base64=request.images_base64,
        image_details=request.image_details,
        style=request.style,
        plan_context=request.plan_context,
        user_id=user_id,
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Inject failed"))

    return StandardResponse(data=result, message=result.get("message", ""))