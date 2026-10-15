"""视频合成 Skill：分镜素材（图/片段 + 配音 + BGM + 字幕）→ 成品短视频。

设计依据：
  - Easel assemble.py 的确定性合成流程（cmd_assemble L289-490）
  - Skill 类模式：复用你项目 GenerateCardImageSkill（card_image_gen.py）的同构模式
  - 输入校验：Pydantic BaseModel（与 VideoGenInput 同模式）
  - 素材存储：save_video_asset()（与 GenerateVideoSkill.execute() 同模式）
  - "零件可缺"原则：缺配音/BGM 时自动跳过，不阻断合成
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.adapters.video_compose import ComposeError, compose_video
from app.core.skill_base import Skill
from app.core.skill_registry import register

logger = logging.getLogger(__name__)


class VideoComposeInput(BaseModel):
    """视频合成输入参数。

    字段设计依据：
      storyboard: Easel assemble.py 输入的 storyboard JSON
        （auto-short-video SKILL.md L44-58 定义的结构）
      output_filename: 成片文件名（不含路径，路径由 asset_library 决定）
      pad_mode: Easel assemble.py _make_shot_clip 的 pad_mode 参数
        （auto/stretch/loop/freeze/trim，默认 auto）
      sub_font: Easel assemble.py DEFAULT_SUB_FONT（字幕字体）
    """
    storyboard: dict[str, Any] = Field(
        description="分镜 JSON（shots/narration/bgm/subtitle/size/image_motion）",
    )
    output_filename: str = Field(
        default="final.mp4",
        description="成片文件名",
    )
    pad_mode: str = Field(
        default="auto",
        description="片段不足时长时的填充模式（auto/stretch/loop/freeze/trim）",
    )
    sub_font: str | None = Field(
        default=None,
        description="字幕字体（None 时用默认 Noto Sans CJK SC）",
    )


@register
class ComposeVideoSkill(Skill):
    """视频合成：分镜素材 → 成品短视频。

    依据：Easel assemble.py cmd_assemble，把分镜素材（图/片段 + 配音 + BGM + 字幕）
    确定性合成一条成品短视频（ffmpeg）。
    """
    node_type = "produce"
    name = "compose_video"
    display_name = "视频合成"
    description = (
        "把分镜素材（图片/视频片段 + 配音 + BGM + 字幕）合成为成品短视频，输出可播放的视频文件。"
        "用户说'合成视频''拼接视频''出片'时必须调用此工具。"
    )
    skill_category = "create"
    skill_priority = "hot"
    trigger_words = ["合成视频", "视频合成", "拼接视频", "组装视频", "出片"]
    input_schema = VideoComposeInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        # 顺手修 B（2026-10-13）：与其他 skill 一致做字段过滤（inputs 带 _user_id
        # 等下划线上下文字段），并把 ValidationError 转成结构化返回——
        # 旧代码 VideoComposeInput(**inputs) 在 LLM 漏传必填 storyboard 时
        # 会直接冒泡崩掉 skill 执行。
        try:
            parsed = VideoComposeInput(
                **{k: v for k, v in inputs.items() if k in VideoComposeInput.model_fields}
            )
        except ValidationError as e:
            first = e.errors()[0] if e.errors() else {}
            logger.error(f"视频合成入参校验失败：{e}")
            return {
                "success": False,
                "error": f"输入参数错误（{first.get('loc', ['?'])[-1]}：{first.get('msg', '')}）",
                "error_type": "invalid_input",
            }
        sb = parsed.storyboard

        shots = sb.get("shots") or []
        if not shots:
            return {
                "success": False,
                "error": "storyboard.shots 为空，无法合成",
                "error_type": "empty_shots",
            }

        import tempfile
        from app.services.asset_library import save_video_asset

        user_id = inputs.get("_user_id", "default")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = str(Path(tmpdir) / parsed.output_filename)

            try:
                result_path = await compose_video(
                    storyboard=sb,
                    output_path=output_path,
                    pad_mode=parsed.pad_mode,
                    sub_font=parsed.sub_font,
                )
            except ComposeError as e:
                logger.error(f"视频合成失败：{e.error_type} - {e.message}")
                return {
                    "success": False,
                    "error": e.message,
                    "error_type": e.error_type,
                }

            video_bytes = result_path.read_bytes()
            if not video_bytes:
                return {
                    "success": False,
                    "error": "合成产物为空",
                    "error_type": "empty_output",
                }

            size_str = sb.get("size", "1080x1920")
            metadata = {
                "source": "compose",
                "size": size_str,
                "shots_count": len(shots),
                "pad_mode": parsed.pad_mode,
                "has_narration": bool(sb.get("narration")),
                "has_bgm": bool(sb.get("bgm")),
                "has_subtitle": bool(sb.get("subtitle")) or any(
                    s.get("caption") for s in shots
                ),
            }

            asset = await save_video_asset(
                user_id=user_id,
                filename=parsed.output_filename,
                content_type="video/mp4",
                data=video_bytes,
                source="ai",
                metadata=metadata,
            )

        return {
            "success": True,
            "asset_id": asset["id"],
            "url": asset["original_url"],
            "file_size": asset["file_size"],
            "metadata": metadata,
        }