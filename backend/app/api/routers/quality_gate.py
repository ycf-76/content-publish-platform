"""Quality Gate API：共享质量门禁的统一入口。

前端在以下场景调用：
- 卡片编辑器 html2canvas 导出前预检（POST /api/quality-gate/check）
- 最终 review 节点复核
- 对话式创作拿到 blueprint 后即时展示质量 badge

后端 image_plan_planner / image_gen_skill / image_gen 节点内部已直接调用服务，
此路由主要用于「前端已渲染 / 已拿到 card_draft」的补充校验与展示。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.services.quality_gate import gate_badge, run_quality_gate

router = APIRouter(prefix="/api/quality-gate", tags=["quality-gate"])


class CheckRequest(BaseModel):
    card_draft: dict[str, Any] = Field(default_factory=dict)
    expected_count: int | None = None


@router.post("/check")
async def check(
    payload: CheckRequest,
    _user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """对一份 card_draft 跑共享质量门禁，返回完整报告与精简 badge。"""
    report = run_quality_gate(
        payload.card_draft,
        expected_count=payload.expected_count,
    )
    return StandardResponse(data={
        "report": report.model_dump(),
        "badge": gate_badge(report),
    })
