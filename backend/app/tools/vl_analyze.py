"""VL analyze skill (Qwen-VL).

Analyzes uploaded images and returns structured tags.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.tools.base import Skill
from app.tools.registry import register

if TYPE_CHECKING:
    from app.adapters.llm_base import LLMProtocol

logger = logging.getLogger(__name__)


class VLAnalyzeInput(BaseModel):
    """Input for VL analyze skill."""

    image_base64: str = Field(..., description="Base64-encoded image")
    account_id: str = Field(..., description="XHS account ID")


class VLAnalyzeOutput(BaseModel):
    """Output from VL analyze skill."""

    tags: list[str] = Field(default_factory=list, description="Detected tags")
    mood: str = Field(default="", description="Detected mood")
    composition: str = Field(default="", description="Detected composition")
    color_palette: list[str] = Field(default_factory=list, description="Detected colors")


@register
class VLAnalyzeSkill(Skill):
    """VL analyze skill using Qwen-VL.

    Does NOT store images in DB (D11).
    Analyzes and discards after use.
    """

    node_type = "analyze"
    name = "vl_analyze"
    description = "Analyze image with Qwen-VL"
    input_schema = VLAnalyzeInput
    output_schema = VLAnalyzeOutput

    def __init__(self, llm: LLMProtocol | None = None) -> None:
        super().__init__()
        self.llm = llm

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """Analyze image using Qwen-VL."""
        # Placeholder for Phase 3 implementation
        if not self.llm:
            raise ValueError("VLAnalyzeSkill requires LLM adapter")
        raise NotImplementedError("QwenVLAdapter not yet implemented (Phase 3)")
