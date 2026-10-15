"""Review routers — MIGRATED to workflow-engine project.

All endpoints return migration notice. Original logic preserved in workflow-engine.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.api.schemas.review import ReviewActionRequest
from app.db.session import get_db

router = APIRouter(prefix="/api/workflows", tags=["review"])


class InjectCardImagesRequest(BaseModel):
    images_base64: list[str]
    image_details: list[dict] | None = None
    style: str = ""
    plan_context: dict | None = None


_MIGRATED_MSG = "工作流引擎已迁移至 workflow-engine 独立项目"


@router.post("/{workflow_id}/review")
async def submit_review(workflow_id: str, request: ReviewActionRequest, user_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> StandardResponse[dict]:
    return StandardResponse(data={"success": False, "message": _MIGRATED_MSG}, message=_MIGRATED_MSG)


@router.get("/{workflow_id}/review/pending")
async def get_pending_review(workflow_id: str, user_id: str = Depends(get_current_user)) -> StandardResponse[dict]:
    return StandardResponse(data={"workflow_id": workflow_id, "is_pending": False, "review_required": {}, "review_processed": {}}, message=_MIGRATED_MSG)


@router.post("/{workflow_id}/reviews/{review_id}")
async def process_review_legacy(workflow_id: str, review_id: str, request: ReviewActionRequest, user_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> StandardResponse[dict]:
    return StandardResponse(data={"review_id": review_id, "success": False, "message": _MIGRATED_MSG}, message=_MIGRATED_MSG)


@router.post("/{workflow_id}/inject-card-images")
async def inject_card_images(workflow_id: str, request: InjectCardImagesRequest, user_id: str = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> StandardResponse[dict]:
    return StandardResponse(data={"success": False, "message": _MIGRATED_MSG}, message=_MIGRATED_MSG)