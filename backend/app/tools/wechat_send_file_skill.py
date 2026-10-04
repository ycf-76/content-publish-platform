"""WeChat Send File Skill — send video/files via WeChat iLink protocol.

Wraps the wechat_bot_engine.send_file method as a Skill tool
so the LLM can invoke it during the video production workflow.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import Skill
from app.tools.registry import register

logger = logging.getLogger(__name__)


class WeChatSendFileInput(BaseModel):
    to_user_id: str = Field(default="", description="目标微信用户ID (wxid)。留空则自动发给绑定用户（即你自己）。也可以填好友wxid或群ID。")
    file_base64: str = Field(..., description="base64编码的文件内容")
    file_ext: str = Field(default="mp4", description="文件扩展名（如 mp4/png/jpg）")
    file_name: str = Field(default="video.mp4", description="显示的文件名")
    context_token: str = Field(default="", description="会话token（可选，自动获取）")


@register
class WeChatSendFileSkill(Skill):
    node_type = "wechat_send_file"
    name = "wechat_send_file"
    display_name = "微信发送文件"
    description = "发送文件/视频/图片到微信。当用户要求把文件发到微信时调用。to_user_id 留空则自动发给绑定用户（即你自己），用户指定了目标才改。"
    platform = "wechat"
    trigger_words = ["微信", "wechat", "企业微信", "wework"]
    input_schema = WeChatSendFileInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        to_user_id = inputs.get("to_user_id", "").strip()
        file_base64 = inputs.get("file_base64", "").strip()
        file_ext = inputs.get("file_ext", "mp4").strip()
        file_name = inputs.get("file_name", "video.mp4").strip()
        hint_token = inputs.get("context_token", "").strip()

        if not file_base64:
            return {"ok": False, "error": "file_base64 is required"}

        try:
            from app.rpa.wechat_bot_engine import get_wechat_engine
        except ImportError:
            return {"ok": False, "error": "wechat_bot_engine not available"}

        ctx = inputs.get("_context")
        user_id = ctx.user_id if ctx and hasattr(ctx, "user_id") else "default"
        logger.info(f"[WeChatSendFileSkill] user_id={user_id}, to_user_id={to_user_id}, file_name={file_name}")

        engine = get_wechat_engine(user_id)
        if not engine.is_logged_in:
            return {"ok": False, "error": "WeChat bot not logged in. Please go to Settings > 自动化办公 > 微信, click 去绑定 and scan QR code first."}

        if not to_user_id or to_user_id == "filehelper":
            if engine._client and engine._client._credentials and engine._client._credentials.ilink_user_id:
                to_user_id = engine._client._credentials.ilink_user_id
                logger.info(f"[WeChatSendFileSkill] 未指定目标或目标为filehelper，使用绑定用户: {to_user_id}")
            else:
                to_user_id = "filehelper"

        context_token = hint_token
        if not context_token and engine._client:
            context_token = await engine._client.ensure_context_token(to_user_id) or ""

        if not context_token:
            return {
                "ok": False,
                "error": (
                    f"无法获取 {to_user_id} 的 context_token。"
                    f"iLink 协议要求对方先给机器人发一条消息才能建立会话。"
                    f"请在微信上给机器人发任意一条消息，然后重试推送。"
                ),
            }

        logger.info(f"[WeChatSendFileSkill] context_token: (ok), 发送文件到 {to_user_id}")

        raw = file_base64
        if "," in raw:
            raw = raw.split(",", 1)[1]

        try:
            file_data = base64.b64decode(raw)
        except Exception as e:
            return {"ok": False, "error": f"base64 decode failed: {e}"}

        try:
            success = await engine.send_file(
                to_user_id=to_user_id,
                context_token=context_token,
                file_data=file_data,
                file_ext=file_ext,
                file_name=file_name,
            )
        except Exception as e:
            logger.error(f"[WeChatSendFileSkill] send_file failed: {e}")
            return {"ok": False, "error": f"send_file failed: {e}"}

        if success:
            return {
                "ok": True,
                "to_user_id": to_user_id,
                "file_name": file_name,
                "size": len(file_data),
            }
        else:
            return {"ok": False, "error": "send_file returned False. The bot may need the target user to send a message first, or getconfig failed to provide context_token."}