"""用户级智能体记忆 API。

提供两个端点：
- GET /api/memory：查看当前用户的记忆概览（偏好 / 统计 / 最近选题 / 最近发布）
- PUT /api/memory/preferences：显式设置偏好（覆盖工作流推断）

红线：
- 用户身份从 JWT 解析（get_current_user），记忆按 user_id 隔离
- 设置偏好用 source="user_explicit"（优先级高于 workflow_inferred）
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.services import agent_memory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/memory", tags=["memory"])


class PreferencesUpdate(BaseModel):
    """用户偏好设置请求体。所有字段可选，未提供则不修改。"""

    writing_style: str | None = Field(
        default=None,
        description="偏好文风（如 '活泼少女风'）。空串视为不修改。",
    )
    image_style: str | None = Field(
        default=None,
        description="偏好图片风格（如 'minimal_white'）。",
    )
    preferred_topics: list[str] | None = Field(
        default=None,
        description="偏好主题类别列表。空列表会清空已有偏好主题。",
    )
    avoided_topics: list[str] | None = Field(
        default=None,
        description="避免主题类别列表。空列表会清空已有避免主题。",
    )


@router.get("")
async def get_memory_overview(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """查看当前用户的智能体记忆概览。"""
    overview = await agent_memory.get_user_memory_overview(user_id)
    return StandardResponse(data=overview)


@router.put("/preferences")
async def update_preferences(
    payload: PreferencesUpdate,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """显式设置用户偏好（覆盖工作流推断的偏好）。

    所有字段可选；未提供的字段保持不变。空列表会清空对应偏好。
    """
    await agent_memory.update_preferences(
        user_id=user_id,
        writing_style=payload.writing_style,
        image_style=payload.image_style,
        preferred_topics=payload.preferred_topics,
        avoided_topics=payload.avoided_topics,
    )
    # 返回最新概览，方便前端即时回显
    overview = await agent_memory.get_user_memory_overview(user_id)
    return StandardResponse(data=overview, message="偏好已更新")
