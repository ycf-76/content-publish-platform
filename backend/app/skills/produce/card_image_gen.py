"""User-confirmed AI image generation into the existing owner-scoped asset library."""

from __future__ import annotations

import io
import logging
from typing import Any, Literal

from PIL import Image
from pydantic import BaseModel, Field

from app.adapters.image_gen import WanxAdapter
from app.services.asset_library import save_asset
from app.core.skill_base import Skill
from app.core.skill_registry import register

logger = logging.getLogger(__name__)


class CardImageInput(BaseModel):
    prompt: str = Field(min_length=10, max_length=800, description="只描述画面，不含需要精准排版的中文文字")
    ratio: Literal["3:4", "1:1", "16:9"] = Field(default="3:4", description="图片槽位目标比例")


@register
class GenerateCardImageSkill(Skill):
    node_type = "produce"
    name = "generate_card_image"
    display_name = "生成卡片素材图"
    description = (
        "当用户明确要求文生图、且允许调用可能收费的图片模型时，生成一张图并返回 asset_id；"
        "必须在获得用户确认后调用，再将该 asset_id 交给 compose_card_deck 排版。"
        "不在图内生成中文正文，正文由卡片排版器绘制。"
    )
    skill_category = "create"
    skill_priority = "hot"
    trigger_words = ["生图", "生成图片", "AI配图"]
    input_schema = CardImageInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        context = inputs.get("_context")
        user_id = getattr(context, "user_id", None)
        if not user_id:
            return {"error": "未能确认用户身份，无法保存图片"}
        params = CardImageInput.model_validate({
            key: value for key, value in inputs.items() if key in CardImageInput.model_fields
        })
        # Do not silently use an unauthenticated public provider or incur charges
        # when no first-party key is available; the Guardian also requires confirmation.
        from app.config import get_settings
        key = (get_settings().dashscope_api_key or "").strip()
        if not key:
            return {"error": "未配置 DASHSCOPE_API_KEY，无法使用 AI 生图；可先上传用户图片"}
        model = get_settings().wanx_model or "wanx2.1-t2i-turbo"
        adapter = WanxAdapter(api_key=key, model=model)
        size = {"3:4": "1080x1440", "1:1": "1024x1024", "16:9": "1280x720"}[params.ratio]
        try:
            images = await adapter.generate(params.prompt, size=size, count=1)
            if not images:
                return {"error": adapter.last_error_message or "图片生成失败，请重试或改用已有素材"}
            with Image.open(io.BytesIO(images[0])) as picture:
                image_format = picture.format or "PNG"
            mime = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(image_format)
            if not mime:
                return {"error": "图片模型返回了不支持的格式"}
            asset = await save_asset(
                user_id=str(user_id), filename="ai_card_image." + image_format.lower(),
                content_type=mime, data=images[0], source="ai",
            )
            return {"asset_id": asset["asset_id"], "asset_url": asset["original_url"],
                    "source": "ai", "next_action": "将 asset_id 传给 compose_card_deck 的 asset_ids"}
        except Exception as exc:
            logger.exception("Card image generation failed: %s", type(exc).__name__)
            return {"error": "图片生成暂不可用，请稍后重试或上传图片"}
