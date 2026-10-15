"""视频生成 Skill：文本/首帧图 → 单段 AI 视频（text2video / image2video）。

设计依据：
  - Easel ai-video-gen 的 generate_* 分派（text2video / image2video 二分支）
  - Skill 类模式：复用本项目 card_image_gen.py 的同构模式
  - 输入校验：Pydantic BaseModel
  - 素材存储：save_video_asset()（asset_library）
  - Provider 解析：_resolve_adapter() 按 settings.video_provider 分派
    （dashscope 万相 / kling 可灵 / ark 火山方舟），模型名走 tier 分级或 provider 默认
  - "零件可缺"原则：未配置对应 provider 的 key 时给出明确结构化错误，不静默

被 multi_image_video 依赖：本模块导出 _resolve_adapter / VideoGenError。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.adapters.video_gen import VideoGenError, create_video_adapter
from app.core.skill_base import Skill
from app.core.skill_registry import register

logger = logging.getLogger(__name__)

__all__ = ["VideoGenError", "GenerateVideoSkill", "VideoGenInput", "_resolve_adapter", "_resolve_image_url"]


class VideoGenInput(BaseModel):
    """视频生成输入参数。"""

    prompt: str = Field(
        min_length=2,
        max_length=2000,
        description="视频画面描述（镜头运动、角色动作、场景转换等）",
    )
    image_asset_id: str | None = Field(
        default=None,
        description="首帧图 asset_id（提供则走 image2video 图生视频；缺省走 text2video 文生视频）",
    )
    ratio: Literal["9:16", "16:9", "1:1"] = Field(
        default="9:16",
        description="画幅比：9:16 竖屏 / 16:9 横屏 / 1:1 方形",
    )
    duration: float = Field(
        default=5.0,
        ge=2.0,
        le=10.0,
        description="视频时长（秒）。wanx2.1-turbo/plus 固定 5s，adapter 内部会钳制",
    )
    provider: Literal["dashscope", "kling", "ark"] | None = Field(
        default=None,
        description="视频生成 provider（None 时用系统默认 settings.video_provider）",
    )
    model: str | None = Field(
        default=None,
        description="覆盖模型名（None 时用 provider 默认 / tier 分级）",
    )
    output_filename: str = Field(
        default="video.mp4",
        description="成片文件名（不含路径，路径由 asset_library 决定）",
    )


def _resolve_adapter(provider: str | None = None) -> tuple[Any, str]:
    """按 provider 名创建视频生成适配器，返回 (adapter, provider_name)。

    依据：Easel resolve_provider() + model_registry configured_providers()，
    结合 Settings 注入各 provider 的 key / model。provider 为空时用
    settings.video_provider（默认 dashscope）。
    """
    from app.config import get_settings

    s = get_settings()
    provider = (provider or getattr(s, "video_provider", "") or "dashscope").strip()

    if provider == "dashscope":
        adapter = create_video_adapter(
            "dashscope",
            api_key=(getattr(s, "dashscope_api_key", "") or "").strip(),
            model=getattr(s, "dashscope_video_model", "") or "wanx2.1-t2v-turbo",
        )
    elif provider == "kling":
        adapter = create_video_adapter(
            "kling",
            access_key=(getattr(s, "kling_access_key", "") or "").strip(),
            secret_key=(getattr(s, "kling_secret_key", "") or "").strip(),
            model=getattr(s, "kling_model", "") or "kling-v1",
        )
    elif provider == "ark":
        adapter = create_video_adapter(
            "ark",
            api_key=(getattr(s, "ark_api_key", "") or "").strip(),
            model=getattr(s, "ark_model", "") or "",
        )
    else:
        raise VideoGenError("bad_provider", f"未知的视频 provider: {provider}（支持: dashscope, kling, ark）")

    return adapter, provider


async def _resolve_image_url(image_asset_id: str, user_id: str) -> str:
    """从 asset_id 解析首帧图 URL（image2video 的 img_url）。"""
    from sqlalchemy import select

    from app.db.models import ImageAsset
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        stmt = select(ImageAsset).where(
            ImageAsset.id == image_asset_id,
            ImageAsset.user_id == user_id,
        )
        result = await session.execute(stmt)
        asset = result.scalar_one_or_none()
        if asset is None:
            raise VideoGenError("bad_request", f"未找到首帧图 asset_id={image_asset_id}")
        return asset.original_url


@register
class GenerateVideoSkill(Skill):
    """视频生成：文本/首帧图 → 单段 AI 视频（text2video / image2video）。"""

    node_type = "produce"
    name = "generate_video"
    display_name = "视频生成"
    description = (
        "用 AI 生成一段视频。提供首帧图走图生视频（image2video），否则走文生视频（text2video）。"
        "支持通义万相/可灵/火山方舟三个 provider。"
    )
    skill_category = "create"
    skill_priority = "hot"
    trigger_words = ["生成视频", "视频生成", "图生视频", "文生视频", "做视频", "video"]
    input_schema = VideoGenInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        parsed = VideoGenInput.model_validate({
            k: v for k, v in inputs.items() if k in VideoGenInput.model_fields
        })
        user_id = inputs.get("_user_id", "default")

        try:
            adapter, provider_name = _resolve_adapter(parsed.provider)
        except VideoGenError as e:
            return {"success": False, "error": e.message, "error_type": e.error_type}

        def _on_progress(elapsed: float, max_wait: float, status: str) -> None:
            logger.info(f"[generate_video] {provider_name} 生成中 {elapsed:.0f}/{max_wait:.0f}s status={status}")

        model = parsed.model
        try:
            if parsed.image_asset_id:
                image_url = await _resolve_image_url(parsed.image_asset_id, user_id)
                video_bytes = await adapter.image2video(
                    image=image_url,
                    prompt=parsed.prompt,
                    ratio=parsed.ratio,
                    duration=parsed.duration,
                    model=model,
                    on_progress=_on_progress,
                )
                mode = "image2video"
            else:
                video_bytes = await adapter.text2video(
                    prompt=parsed.prompt,
                    ratio=parsed.ratio,
                    duration=parsed.duration,
                    model=model,
                    on_progress=_on_progress,
                )
                mode = "text2video"
        except VideoGenError as e:
            logger.error(f"[generate_video] {provider_name} 失败：{e.error_type} - {e.message}")
            return {"success": False, "error": e.message, "error_type": e.error_type}
        except Exception as e:
            logger.exception("[generate_video] 未知错误")
            return {"success": False, "error": str(e), "error_type": "unknown"}

        if not video_bytes:
            return {"success": False, "error": "视频生成为空", "error_type": "empty_output"}

        import tempfile

        from app.services.asset_library import save_video_asset

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / parsed.output_filename
            tmp_path.write_bytes(video_bytes)
            asset = await save_video_asset(
                user_id=user_id,
                filename=parsed.output_filename,
                content_type="video/mp4",
                data=video_bytes,
                source="ai",
                metadata={
                    "source": "video_gen",
                    "provider": provider_name,
                    "mode": mode,
                    "ratio": parsed.ratio,
                    "duration": parsed.duration,
                    "prompt": parsed.prompt[:200],
                },
            )

        return {
            "success": True,
            "asset_id": asset["id"],
            "url": asset["original_url"],
            "file_size": asset["file_size"],
            "provider": provider_name,
            "mode": mode,
            "metadata": {
                "provider": provider_name,
                "mode": mode,
                "ratio": parsed.ratio,
                "duration": parsed.duration,
            },
        }
