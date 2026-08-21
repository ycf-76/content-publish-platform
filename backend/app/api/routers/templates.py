"""Template registry API.

Phase 1 exposes builtin template manifests for the future image workspace.
It intentionally does not modify the existing card editor or workflow nodes.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.templates.registry import get_template_registry

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("")
async def list_templates(
    platform: str | None = Query(default=None, description="按平台过滤，如 xiaohongshu"),
    category: str | None = Query(default=None, description="按分类过滤，如 科技/美食/知识"),
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[list[dict]]:
    """列出模板清单。"""
    registry = get_template_registry()
    templates = registry.list(platform=platform, category=category)
    return StandardResponse(data=[template.metadata() for template in templates])


@router.get("/platforms")
async def list_platforms(
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[list[dict]]:
    registry = get_template_registry()
    return StandardResponse(
        data=[profile.model_dump() for profile in registry.list_platform_profiles()]
    )


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """获取单个模板详情。"""
    template = get_template_registry().get(template_id)
    if template is None:
        raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
    return StandardResponse(data=template.metadata())
