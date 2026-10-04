"""WeChat Send Text Skill — send text messages via WeChat iLink protocol.

Wraps the wechat_bot_engine.send_text method as a Skill tool
so the LLM can invoke it during chat or workflow.
Auto-splits long text into multiple messages (WeChat limit ~2048 chars per message).
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import Skill
from app.tools.registry import register

logger = logging.getLogger(__name__)

_MAX_MSG_LEN = 1800


class WeChatSendTextInput(BaseModel):
    to_user_id: str = Field(default="", description="目标微信用户ID (wxid)。留空则自动发给绑定用户（即你自己）。也可以填好友wxid或群ID。")
    text: str = Field(..., description="要发送的完整文本内容。必须包含完整文案，不要只发标题或摘要。如果内容很长，skill会自动分段发送。")
    context_token: str = Field(default="", description="会话token（可选，自动获取）")


@register
class WeChatSendTextSkill(Skill):
    node_type = "wechat_send_text"
    name = "wechat_send_text"
    display_name = "微信发送文本"
    description = (
        "发送文本消息到微信。当用户要求把内容发到微信/推送到微信/转发到微信时调用。"
        "重要：text参数必须传入完整内容（标题+正文+标签等），不要只发标题或摘要！"
        "长文本会自动分段发送。to_user_id留空则发给绑定用户。"
    )
    platform = "wechat"
    trigger_words = ["微信", "wechat", "企业微信", "wework"]
    input_schema = WeChatSendTextInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        to_user_id = inputs.get("to_user_id", "").strip()
        text = inputs.get("text", "").strip()
        hint_token = inputs.get("context_token", "").strip()

        if not text:
            return {"ok": False, "error": "text is required"}

        try:
            from app.rpa.wechat_bot_engine import get_wechat_engine
        except ImportError:
            return {"ok": False, "error": "wechat_bot_engine not available"}

        ctx = inputs.get("_context")
        user_id = ctx.user_id if ctx and hasattr(ctx, "user_id") else "default"
        logger.info(f"[WeChatSendTextSkill] user_id={user_id}, to_user_id={to_user_id}, text_len={len(text)}")

        engine = get_wechat_engine(user_id)
        if not engine.is_logged_in:
            return {"ok": False, "error": "WeChat bot not logged in. Please go to Settings > 自动化办公 > 微信, click 去绑定 and scan QR code first."}

        if not to_user_id or to_user_id == "filehelper":
            if engine._client and engine._client._credentials and engine._client._credentials.ilink_user_id:
                to_user_id = engine._client._credentials.ilink_user_id
                logger.info(f"[WeChatSendTextSkill] 未指定目标或目标为filehelper，使用绑定用户: {to_user_id}")
            else:
                to_user_id = "filehelper"

        context_token = hint_token
        if not context_token and engine._client:
            context_token = await engine._client.ensure_context_token(to_user_id) or ""

        if not context_token:
            return {
                "ok": False,
                "error": (
                    "⚠️ 微信推送需要先激活会话\n\n"
                    "iLink 协议要求：对方必须先给机器人发一条消息，机器人才能回复/推送。\n\n"
                    "激活方法：在微信上找到机器人（iLink助手），发送任意一条消息（如\"hi\"），即可建立会话。\n"
                    "激活后重试推送即可成功。\n\n"
                    "注意：这是微信iLink协议的硬限制，无法绕过。"
                ),
                "permanent": True,
            }

        chunks = self._split_text(text)
        logger.info(f"[WeChatSendTextSkill] context_token: (ok), 发送到 {to_user_id}, 分{len(chunks)}段发送")

        sent_count = 0
        for i, chunk in enumerate(chunks):
            try:
                success = await engine.send_text(
                    to_user_id=to_user_id,
                    context_token=context_token,
                    text=chunk,
                )
                if success:
                    sent_count += 1
                    logger.info(f"[WeChatSendTextSkill] 第{i+1}/{len(chunks)}段发送成功")
                else:
                    logger.error(f"[WeChatSendTextSkill] 第{i+1}/{len(chunks)}段发送失败 (iLink API error)")
                    if sent_count == 0:
                        return {"ok": False, "error": f"第{i+1}段发送失败 (iLink API error)"}
            except Exception as e:
                logger.error(f"[WeChatSendTextSkill] 第{i+1}/{len(chunks)}段发送异常: {e}")
                if sent_count == 0:
                    return {"ok": False, "error": f"第{i+1}段发送失败: {e}"}

        return {
            "ok": True,
            "to_user_id": to_user_id,
            "text_length": len(text),
            "chunks_sent": sent_count,
            "chunks_total": len(chunks),
        }

    @staticmethod
    def _split_text(text: str, max_len: int = _MAX_MSG_LEN) -> list[str]:
        if len(text) <= max_len:
            return [text]
        chunks = []
        remaining = text
        while remaining:
            if len(remaining) <= max_len:
                chunks.append(remaining)
                break
            split_at = remaining.rfind("\n", 0, max_len)
            if split_at <= max_len // 2:
                split_at = remaining.rfind("。", 0, max_len)
            if split_at <= max_len // 2:
                split_at = max_len
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip("\n")
        return chunks