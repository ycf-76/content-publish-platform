"""Xiaohongshu publish skill.

Publishes via MCP Client Manager (plugin primary + local fallback).
已接通 mcp_manager：plugin client NotImplementedError 时由 local Playwright 兜底。
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.agents.skills.base import Skill
from app.agents.skills.permissions import Permission

if TYPE_CHECKING:
    from app.agents.adapters.llm_base import LLMProtocol

logger = logging.getLogger(__name__)


class XhsPublishInput(BaseModel):
    """Input for XHS publish skill."""

    title: str = Field(..., description="Post title")
    content: str = Field(..., description="Post content")
    images_base64: list[str] = Field(default_factory=list, description="Base64 images")
    account_id: str = Field(default="", description="XHS account ID (optional)")


class XhsPublishOutput(BaseModel):
    """Output from XHS publish skill."""

    post_id: str = Field(default="", description="Published post ID")
    status: str = Field(..., description="Publish status (success/failed)")
    message: str = Field(default="", description="Error message if failed")


class XhsPublishSkill(Skill):
    """Xiaohongshu publish skill.

    Uses MCP Client Manager (plugin primary + local fallback).
    Plugin client 通过浏览器扩展在用户真实浏览器里操作发布页（RPA 方案），
    无 webdriver 痕迹，规避风控。失败时回退到 local client（Playwright）。
    """

    name = "xhs_publish"
    description = "Publish to Xiaohongshu"
    input_schema = XhsPublishInput
    output_schema = XhsPublishOutput
    required_permissions = [Permission.XHS_PUBLISH]

    def __init__(self, llm: LLMProtocol | None = None) -> None:
        super().__init__()
        self.llm = llm

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = XhsPublishInput.model_validate(inputs)
        client = self._get_xhs_client()

        try:
            result = await client.publish_note(
                in_.title, in_.content, in_.images_base64
            )
        except NotImplementedError as e:
            # Plugin client 不支持发布
            return {
                "post_id": "",
                "status": "failed",
                "message": f"publish not supported by active MCP client: {e}",
            }

        success = bool(result.get("success", False))
        # 半自动模式：worker 填好内容但不点击，返回 success=true +
        # message 含"手动点击"→ 标记 awaiting_manual，节点保持 running 等前端轮询 check
        message = str(result.get("message", ""))
        if success and "手动点击" in message:
            return {
                "post_id": "",
                "status": "awaiting_manual",
                "message": message,
            }
        return {
            "post_id": str(result.get("post_id", "") or result.get("url", "")),
            "status": "success" if success else "failed",
            "message": message,
        }

    def _get_xhs_client(self):
        """返回全局 MCPClientManager。"""
        from app.agents.skills.mcp.xhs_client import mcp_manager
        if mcp_manager._plugin_client is None and mcp_manager._local_client is None:
            raise RuntimeError(
                "MCPClientManager 未初始化：请先在 lifespan 调用 init_mcp_clients()"
            )
        return mcp_manager
