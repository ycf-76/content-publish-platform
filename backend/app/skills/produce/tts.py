"""TTS Skill — text-to-speech using edge-tts (free, no API key needed)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agents.prompts.scripts.tts_edge import synthesize, resolve_voice, VOICES_ZH, VOICES_EN
from app.core.skill_base import Skill
from app.core.skill_registry import register

logger = logging.getLogger(__name__)

_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "outputs"


class TTSInput(BaseModel):
    text: str = Field(min_length=1, max_length=5000, description="要合成的文本")
    voice: str = Field(
        default="xiaoxiao",
        description="音色：xiaoxiao/xiaoyi/yunjian/yunxi/yunxia/yunyang(中文), aria/jenny/guy/davis(英文)，或完整voice ID",
    )
    rate: str = Field(default="+0%", description="语速调节，如 +20% 或 -10%")
    volume: str = Field(default="+0%", description="音量调节，如 +50% 或 -20%")


@register
class TTSSkill(Skill):
    node_type = "produce"
    name = "tts_edge"
    display_name = "语音合成"
    description = (
        "使用 edge-tts 将文本转为语音 MP3。免费，无需 API key。"
        "支持中文（晓晓/云希/云扬等）和英文（Aria/Jenny等）音色。"
        "当 voice_builder 产出话术后，调用本 Skill 合成语音。"
    )
    skill_category = "create"
    skill_priority = "warm"
    capability_tier = "external_service"
    trigger_words = ["语音合成", "转语音", "TTS", "读出来", "配音", "朗读"]
    input_schema = TTSInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        params = TTSInput.model_validate({
            k: v for k, v in inputs.items() if k in TTSInput.model_fields
        })

        voice_id = resolve_voice(params.voice)
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = _OUTPUT_DIR / "tts_output.mp3"

        try:
            result_path = await synthesize(
                text=params.text,
                output_path=output_path,
                voice=voice_id,
                rate=params.rate,
                volume=params.volume,
            )
        except Exception as e:
            logger.exception("TTS synthesis failed")
            return {"error": f"语音合成失败: {e}"}

        audio_url = f"/outputs/{result_path.name}"

        return {
            "output_path": str(result_path),
            "voice": voice_id,
            "text_length": len(params.text),
            "card_draft": {
                "title": "语音合成",
                "template": "tts_edge",
                "pages": [{
                    "id": "page_tts",
                    "type": "content",
                    "mediaType": "audio",
                    "title": "语音合成",
                    "audioUrl": audio_url,
                    "width": 800,
                    "height": 200,
                }],
                "pngUrls": [],
                "htmlUrls": [],
            },
        }