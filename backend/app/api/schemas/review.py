"""Review API schemas."""

from typing import Any

from pydantic import BaseModel, Field


class ReviewActionRequest(BaseModel):
    """Review action request."""

    action: str = Field(..., description="pass（通过）/ reject（拒绝）")
    feedback: str = Field(default="", description="审核反馈（可选）")
    payload: dict[str, Any] = Field(default_factory=dict)
    # 候选模式：用户选中的 candidate id（如 "list_fresh_natural"）
    selected_candidate: str = Field(
        default="",
        description="候选模式下用户选中的 candidate id（如 list_fresh_natural）",
    )


class ReviewResponse(BaseModel):
    """Review response."""

    review_id: str
    workflow_id: str
    node_id: str
    review_type: str
    status: str
    payload: dict[str, Any]
