"""用户画像 API（D18 创作者画像）。

端点（《技术架构设计文档》8.1.1）：
- GET  /api/profile          读取当前用户画像（未设置时 data=null，前端引导去设置页）
- PUT  /api/profile          创建/更新画像（primary_domain 必填，缺失 → 422）
- POST /api/profile/validate 启动工作流前的画像完整性检查

错误响应遵循《前后端通信协议》第9章格式：
- {"code": "PROFILE_NOT_FOUND", "message": "请先在设置页完善创作者画像", ...}
- {"code": "PROFILE_INVALID", "message": "...", ...}
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.api.schemas.profile import (
    ProfileValidationResponse,
    ProfileValidationError,
    UpdateProfileRequest,
    UserProfile,
)
from app.db.session import get_db
from app.services.profile_service import get_profile_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.get("", response_model=StandardResponse[UserProfile])
async def get_profile(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[UserProfile]:
    """读取当前用户画像。未设置时 data=null（前端引导去设置页，不报错）。"""
    service = get_profile_service(db)
    profile = await service.get_profile(user_id)
    if profile is None:
        logger.info(f"[profile] GET: no profile for user {user_id}")
        return StandardResponse(success=True, data=None, message="尚未设置创作者画像")
    return StandardResponse(success=True, data=profile)


@router.put("", response_model=StandardResponse[UserProfile])
async def update_profile(
    req: UpdateProfileRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[UserProfile]:
    """创建/更新画像（upsert 语义，1:1 不重复建行）。

    primary_domain 必填：缺失或非法值由 pydantic 校验返回 422。
    """
    service = get_profile_service(db)
    try:
        profile = await service.upsert_profile(user_id, req)
    except ProfileValidationError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "PROFILE_INVALID",
                "message": "画像字段不合法",
                "detail": {"reason": e.reason},
            },
        )
    return StandardResponse(success=True, data=profile, message="画像已保存")


@router.post("/validate", response_model=ProfileValidationResponse)
async def validate_profile(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileValidationResponse:
    """启动工作流前的画像完整性检查。

    前端在启动工作流前调用此接口，invalid 时弹提示引导设置。
    返回 {valid, reason, profile}。
    """
    service = get_profile_service(db)
    try:
        profile = await service.get_or_validate(user_id)
        return ProfileValidationResponse(valid=True, reason=None, profile=profile)
    except ProfileValidationError as e:
        logger.info(f"[profile] validate failed for user {user_id}: {e.reason}")
        return ProfileValidationResponse(valid=False, reason=e.reason, profile=None)
