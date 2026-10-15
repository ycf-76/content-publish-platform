"""Meme render skill — Pillow-based image text overlay.

Wraps app.agents.prompts.scripts.meme_ops for use as a registered Skill.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from app.agents.prompts.scripts.meme_ops import render_classic, render_reaction
from app.services.asset_library import save_asset
from app.core.skill_base import Skill
from app.core.skill_registry import register

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "outputs"


class MemeRenderInput(BaseModel):
    image_path: str = Field(default="", description="本地图片路径")
    image_url: str = Field(default="", description="图片URL（二选一）")
    top_text: str = Field(default="", description="上方文字（经典Meme格式）")
    bottom_text: str = Field(default="", description="下方文字（经典Meme格式）")
    caption: str = Field(default="", description="配文（反应图格式）")
    mode: Literal["classic", "reaction", "auto"] = Field(
        default="auto",
        description="排版模式：classic=上下大字, reaction=配文条, auto=自动判断",
    )


@register
class MemeRenderSkill(Skill):
    node_type = "produce"
    name = "meme_render"
    display_name = "表情包渲染"
    description = (
        "用 Pillow 给图片加梗字做表情包。两种模式："
        "classic=白字黑边叠图上下，reaction=纯色配文条。"
        "当 meme-generator 提示词 Skill 产出了文字后，调用本 Skill 渲染图片。"
    )
    skill_category = "create"
    skill_priority = "cold"
    capability_tier = "image_render"
    trigger_words = ["做表情包", "加梗字", "渲染表情包"]
    input_schema = MemeRenderInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        params = MemeRenderInput.model_validate({
            k: v for k, v in inputs.items() if k in MemeRenderInput.model_fields
        })

        local_path = await self._resolve_image(params.image_path, params.image_url)
        if not local_path:
            return {"error": "未提供图片路径或URL，无法渲染表情包"}

        mode = params.mode
        if mode == "auto":
            mode = "classic" if (params.top_text or params.bottom_text) else "reaction"

        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = _OUTPUT_DIR / "meme_output.png"

        try:
            if mode == "classic":
                result_path = render_classic(
                    local_path,
                    top_text=params.top_text,
                    bottom_text=params.bottom_text,
                    output_path=output_path,
                )
            else:
                result_path = render_reaction(
                    local_path,
                    caption=params.caption or params.top_text or params.bottom_text,
                    output_path=output_path,
                )
        except Exception as e:
            logger.exception("Meme render failed")
            return {"error": f"表情包渲染失败: {e}"}

        context = inputs.get("_context")
        user_id = getattr(context, "user_id", None)
        asset_info: dict[str, Any] = {}
        if user_id:
            try:
                data = result_path.read_bytes()
                asset = await save_asset(
                    user_id=str(user_id),
                    filename="meme.png",
                    content_type="image/png",
                    data=data,
                    source="meme_render",
                )
                asset_info = {
                    "asset_id": asset["asset_id"],
                    "asset_url": asset["original_url"],
                }
            except Exception as e:
                logger.warning("Failed to save meme to asset library: %s", e)

        image_url = asset_info.get("asset_url", "")
        if not image_url:
            image_url = f"/outputs/{result_path.name}"

        return {
            "output_path": str(result_path),
            "mode": mode,
            **asset_info,
            "card_draft": {
                "title": "表情包",
                "template": "meme_render",
                "pages": [{
                    "id": "page_meme",
                    "type": "content",
                    "mediaType": "image",
                    "title": "表情包",
                    "imageUrl": image_url,
                    "width": 800,
                    "height": 800,
                }],
                "pngUrls": [image_url] if image_url else [],
                "htmlUrls": [],
            },
        }

    async def _resolve_image(self, path: str, url: str) -> Path | None:
        if path and Path(path).exists():
            return Path(path)
        if url:
            try:
                resp = await httpx.AsyncClient(timeout=30).get(url)
                resp.raise_for_status()
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.write(resp.content)
                tmp.close()
                return Path(tmp.name)
            except Exception as e:
                logger.warning("Failed to download image from URL: %s", e)
        return None