"""一键短视频编排 Skill：主题 → 成品短视频。

设计依据：
  - Easel auto-short-video SKILL.md 的编排流程（L28-58）
  - 编排原则：零件可缺（缺 API key 的环节自动降级，不阻断整体）
  - 先出 Plan：涉及多个付费 API 时先向用户说明将调用哪些
  - 中间产物留档：分镜图/配音/字幕/storyboard 都存 asset_library

编排流程（依据 Easel auto-short-video SKILL.md L28-58）：
  1. 写脚本分镜：LLM 把主题写成口播文案，拆成 N 句
  2. 生成画面：逐句 text2img（有图像 API key）或降级
  3. 配音：TTS 把文案合成口播（edge-tts 在线 → piper 离线降级）或跳过
  4. 合成成片：调 compose_video（ffmpeg 确定性合成）
  5. 交付：产出 final.mp4 + 制作说明
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.skill_base import Skill
from app.core.skill_registry import register

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "outputs"


class AutoShortVideoInput(BaseModel):
    """一键短视频输入参数。

    字段设计依据：
      topic: Easel auto-short-video SKILL.md 输入"主题/文案（必填）"
      target_duration: Easel auto-short-video SKILL.md "可选：目标时长"
      ratio: 画幅比（Easel 要求"画幅确认硬门"，默认 9:16 竖屏）
      style: Easel auto-short-video SKILL.md "可选：风格"
      need_narration: 是否需要配音（Easel "零件可缺"原则）
      need_bgm: 是否需要 BGM（Easel "零件可缺"原则）
      image_motion: Easel assemble.py image_motion（ken-burns / static）
    """

    topic: str = Field(min_length=2, max_length=500, description="视频主题或文案")
    target_duration: float = Field(default=30.0, ge=5.0, le=300.0, description="目标时长（秒），5-300s")
    ratio: Literal["9:16", "16:9"] = Field(
        default="9:16", description="画幅比：9:16 竖屏（小红书/抖音）/ 16:9 横屏（B站）"
    )
    style: str = Field(default="口播", description="风格：口播/科普/种草/教程")
    need_narration: bool = Field(default=True, description="是否需要配音（缺 TTS 时自动降级跳过）")
    need_bgm: bool = Field(default=False, description="是否需要 BGM")
    image_motion: Literal["ken-burns", "static"] = Field(
        default="ken-burns", description="图片默认运动：ken-burns（照片缓动）/ static（文字卡/图表）"
    )


_SIZE_MAP = {"9:16": "1080x1920", "16:9": "1920x1080"}

_SCRIPT_PROMPT = """你是一个短视频脚本编剧。请根据以下要求写出一条短视频的分镜脚本。

主题：{topic}
目标时长：{duration}秒
风格：{style}
画幅：{ratio}

请输出 JSON 格式（不要 markdown 代码块，直接输出 JSON）：
{{
  "title": "视频标题",
  "hook": "开头 hook（3秒内抓住注意力）",
  "shots": [
    {{
      "caption": "这一句的口播文案",
      "image_prompt": "这一句配图的画面描述（英文，用于 AI 生图）",
      "duration": 3.0,
      "motion": "ken-burns"
    }}
  ],
  "closing": "结尾号召语"
}}

要求：
- 每句 15-30 字，口语化，适合口播
- 分镜数 = 目标时长 / 每镜时长（每镜 3-5 秒）
- hook 要有好奇缺口或模式打断
- image_prompt 要具体、有画面感
- 总时长尽量接近目标时长
"""


async def _generate_script(topic: str, duration: float, style: str, ratio: str) -> dict:
    """用 LLM 生成视频脚本分镜。

    依据：Easel auto-short-video SKILL.md Step 1 "写脚本分镜"，
    用 video-script 把主题写成口播文案，拆成 N 句。
    本实现直接用项目 LLM 调用能力生成 JSON 脚本。
    """
    from app.config import get_settings
    from app.engine.llm_client import get_llm

    settings = get_settings()
    prompt = _SCRIPT_PROMPT.format(topic=topic, duration=int(duration), style=style, ratio=ratio)

    try:
        llm = get_llm()
        response = await llm.ainvoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        json_start = text.find("{")
        json_end = text.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            script = json.loads(text[json_start:json_end])
        else:
            script = json.loads(text)
        if "shots" not in script or not script["shots"]:
            raise ValueError("脚本缺少 shots 字段")
        return script
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"LLM 脚本解析失败，使用默认脚本：{e}")
        num_shots = max(2, int(duration / 4))
        per_dur = duration / num_shots
        return {
            "title": topic,
            "hook": f"关于{topic}，你可能不知道这些",
            "shots": [
                {
                    "caption": f"第{i + 1}点：{topic}的相关内容",
                    "image_prompt": f"illustration of {topic}, scene {i + 1}, high quality",
                    "duration": per_dur,
                    "motion": "ken-burns",
                }
                for i in range(num_shots)
            ],
            "closing": "关注我，了解更多",
        }


async def _generate_shot_images(shots: list[dict], ratio: str, user_id: str) -> list[dict]:
    """逐句生成配图。

    依据：Easel auto-short-video SKILL.md Step 2 "生成画面"，
    有图像 API key → WanxAdapter 逐句 text2img。
    缺 key → 降级（返回空 image 字段，compose 会用纯色占位）。
    """
    from app.config import get_settings

    settings = get_settings()
    api_key = (settings.dashscope_api_key or "").strip()
    if not api_key:
        logger.info("未配置图像 API key，跳过配图生成（降级）")
        return shots

    try:
        from app.adapters.image_gen import WanxAdapter

        adapter = WanxAdapter(api_key=api_key)
        size_map = {"9:16": "720x1280", "16:9": "1280x720"}
        size = size_map.get(ratio, "720x1280")

        for shot in shots:
            prompt = shot.get("image_prompt", "")
            if not prompt:
                continue
            try:
                img_bytes = await adapter.generate(prompt=prompt, size=size, count=1)
                if not img_bytes:
                    continue
                from app.services.asset_library import save_asset

                asset = await save_asset(
                    user_id=user_id,
                    filename=f"shot_{hash(prompt) % 10000:04d}.png",
                    content_type="image/png",
                    data=img_bytes,
                )
                from app.services.asset_library import _path_from_url

                local_path = _path_from_url(asset["original_url"])
                shot["image"] = str(local_path) if local_path else asset["original_url"]
                logger.info(f"配图生成成功：{shot.get('caption', '')[:20]}")
            except Exception as e:
                logger.warning(f"配图生成失败，跳过：{e}")
        return shots
    except Exception as e:
        logger.warning(f"图像适配器初始化失败，跳过配图：{e}")
        return shots


async def _generate_narration(script: dict, user_id: str) -> tuple[str | None, str]:
    """生成配音（两级降级：edge-tts 在线 → piper 离线）。

    依据：Easel auto-short-video SKILL.md Step 3 "配音"。
    返回 (配音文件路径, 来源标签)；都失败返回 (None, "none")。
    """
    shots = script.get("shots", [])
    full_text = "。".join(s.get("caption", "") for s in shots if s.get("caption"))
    if not full_text.strip():
        return (None, "none")

    output_dir = _OUTPUT_DIR / "assets" / user_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from app.agents.prompts.scripts.tts_edge import synthesize

        voice_path = output_dir / "narration.mp3"
        result = await synthesize(text=full_text, output_path=voice_path, voice="xiaoxiao")
        return (str(result), "edge-tts")
    except Exception as e:
        logger.warning(f"edge-tts 配音失败，尝试 piper 离线降级：{e}")

    try:
        from app.config import get_settings
        from app.skills.produce.tts_piper import synthesize_piper

        settings = get_settings()
        voice_path = output_dir / "narration_piper.wav"
        result = await synthesize_piper(
            text=full_text,
            output_path=voice_path,
            binary=settings.piper_binary,
            model_path=settings.piper_model_path,
        )
        return (str(result), "piper")
    except Exception as e:
        logger.warning(f"piper 离线配音也不可用：{e}")
        return (None, "none")


@register
class AutoShortVideoSkill(Skill):
    """一键短视频：主题 → 成品短视频。

    依据：Easel auto-short-video SKILL.md 的编排流程，
    自动串联 文案→配图→配音→合成，把制作层零件编排成一条"一键出片"流水线。
    """

    node_type = "produce"
    name = "auto_short_video"
    display_name = "一键短视频"

    description = (
        "一句话主题直接出成品短视频：自动串联 文案→配图→配音→字幕→合成，"
        "输出可播放的视频。用户说'一键生成视频''自动做短视频''帮我做条视频'时必须调用此工具。"
        "缺 API key 的环节自动降级，不阻断整体。"
    )
    skill_category = "create"
    skill_priority = "hot"
    trigger_words = [
        "一键生成视频",
        "自动做短视频",
        "主题生成视频",
        "帮我做条视频",
        "口播视频一条龙",
        "自动出片",
        "短视频一键生成",
    ]

    input_schema = AutoShortVideoInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        parsed = AutoShortVideoInput(
            **{k: v for k, v in inputs.items() if k in AutoShortVideoInput.model_fields}
        )

        user_id = inputs.get("_user_id", "default")

        degradation_notes: list[str] = []

        workflow_id = inputs.get("_workflow_id")

        async def _emit_step(step: int, total: int, label: str, detail: str) -> None:
            if not workflow_id:
                return None
            from app.services.sse_bus import sse_bus

            pct = int(step / total * 100)
            await sse_bus.publish(
                workflow_id,
                "video_pipeline_progress",
                {
                    "skill": "auto_short_video",
                    "step": step,
                    "total": total,
                    "label": label,
                    "detail": detail,
                    "percent": pct,
                },
            )

        size = _SIZE_MAP.get(parsed.ratio, "1080x1920")
        output_dir = _OUTPUT_DIR / parsed.topic[:20] / "assets"
        output_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"[1/4] 生成脚本分镜：{parsed.topic}")
        await _emit_step(1, 4, "生成脚本分镜", parsed.topic)
        script = await _generate_script(
            topic=parsed.topic,
            duration=parsed.target_duration,
            style=parsed.style,
            ratio=parsed.ratio,
        )
        shots = script.get("shots", [])

        logger.info(f"[2/4] 生成配图（{len(shots)} 镜）")
        await _emit_step(2, 4, "生成配图", f"{len(shots)} 镜")
        shots = await _generate_shot_images(shots, parsed.ratio, user_id)
        has_images = any(s.get("image") for s in shots)
        if not has_images:
            degradation_notes.append(
                "配图：未生成任何图片（API key 未配置或全部失败），将用纯色占位"
            )

        narration_path = None
        if parsed.need_narration:
            logger.info("[3/4] 生成配音")
            await _emit_step(3, 4, "生成配音", "TTS 合成口播（edge-tts → piper 降级）")
            narration_path, narration_source = await _generate_narration(script, user_id)
            if not narration_path:
                degradation_notes.append("配音：edge-tts 与 piper 均不可用，跳过配音")
            elif narration_source == "edge-tts":
                degradation_notes.append("配音：edge-tts 在线合成")
            else:
                degradation_notes.append(f"配音：edge-tts 不可用，降级 {narration_source} 离线合成")
        else:
            degradation_notes.append("配音：用户未要求")

        logger.info("[4/4] 合成成片")
        await _emit_step(4, 4, "合成成片", "ffmpeg 确定性合成")

        storyboard = {
            "size": size,
            "image_motion": parsed.image_motion,
            "shots": shots,
        }
        if narration_path:
            storyboard["narration"] = narration_path

        storyboard_path = output_dir / "storyboard.json"
        storyboard_path.write_text(
            json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        final_path = _OUTPUT_DIR / parsed.topic[:20] / "final.mp4"

        try:
            from app.adapters.video_compose import compose_video

            result_path = await compose_video(
                storyboard=storyboard,
                output_path=str(final_path),
                pad_mode="auto",
            )
            video_bytes = result_path.read_bytes()

            from app.services.asset_library import save_video_asset

            asset = await save_video_asset(
                user_id=user_id,
                filename=f"{parsed.topic[:20]}_final.mp4",
                content_type="video/mp4",
                data=video_bytes,
                source="ai",
                metadata={
                    "source": "auto_short_video",
                    "topic": parsed.topic,
                    "ratio": parsed.ratio,
                    "target_duration": parsed.target_duration,
                    "style": parsed.style,
                    "shots_count": len(shots),
                    "has_narration": bool(narration_path),
                    "degradation": degradation_notes,
                },
            )
            return {
                "success": True,
                "asset_id": asset["id"],
                "url": asset["original_url"],
                "file_size": asset["file_size"],
                "title": script.get("title", parsed.topic),
                "shots_count": len(shots),
                "has_narration": bool(narration_path),
                "degradation": degradation_notes,
                "storyboard_path": str(storyboard_path),
            }
        except Exception as e:
            error_type = getattr(e, "error_type", "compose_failed")
            logger.error(f"视频合成失败：{error_type} - {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": error_type,
                "degradation": degradation_notes,
                "storyboard_path": str(storyboard_path),
            }
