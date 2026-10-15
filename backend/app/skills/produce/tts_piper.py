r"""离线 TTS Skill — piper（本地推理，无需 API key / 联网）。

2026-10-14 接线。环境：D:/om-runtime（piper.exe + espeak-ng + cmn model.onnx）。
用途：edge-tts（在线）不可用时的离线配音降级——auto_short_video 的
_generate_narration 两级降级链的第二级。

接线时实测结论（改配置前先读这段）：
  1. PATH 里的 piper（Python312\Scripts\piper）缺 espeak-ng-data 不可用
     （报 phontab not found，只产出 0 字节文件）——必须用
     D:/om-runtime/piper/piper.exe（espeak-ng.dll + data 在其同目录）
  2. piper 是 Windows 程序，-m/-f 必须传 Windows 风格路径（D:\...），
     MSYS/Git Bash 的 /d/... 会被当字面路径，静默不写文件
  3. 文本从 stdin 传（避免命令行长度限制和引号地狱）
  4. RTF≈0.09：4.7s 音频 0.4s 推理完，比实时快 10 倍
  5. 输出：pcm_s16le / 22050Hz / 单声道 wav（compose_video 内有 aresample）
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.skill_base import Skill
from app.core.skill_registry import register

logger = logging.getLogger(__name__)

_DEFAULT_PIPER_BINARY = r"D:\om-runtime\piper\piper.exe"
_DEFAULT_PIPER_MODEL = r"D:\om-runtime\model.onnx"


def _resolve_piper_paths(binary: str | None, model_path: str | None) -> tuple[str, str]:
    """按优先级解析 piper 可执行与模型路径：显式参数 > settings > 内置默认。"""
    b, m = binary, model_path
    if not b or not m:
        try:
            from app.config import get_settings
            s = get_settings()
            b = b or getattr(s, "piper_binary", "") or _DEFAULT_PIPER_BINARY
            m = m or getattr(s, "piper_model_path", "") or _DEFAULT_PIPER_MODEL
        except Exception:
            b = b or _DEFAULT_PIPER_BINARY
            m = m or _DEFAULT_PIPER_MODEL
    return b, m


async def synthesize_piper(
    text: str,
    output_path: str | Path,
    *,
    binary: str | None = None,
    model_path: str | None = None,
) -> str:
    """调 piper 合成语音（模块级函数，供 auto_short_video 降级链直接 import）。

    与 PiperTTSSkill 的关系：本函数不依赖 skill 注册，内部调用零开销。
    返回输出文件路径（str）。二进制/模型缺失抛 FileNotFoundError，推理失败抛 RuntimeError。
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("synthesize_piper: 文本为空")

    binary, model_path = _resolve_piper_paths(binary, model_path)
    bin_p = Path(binary)
    model_p = Path(model_path)
    if not bin_p.is_file():
        raise FileNotFoundError(f"piper 可执行不存在：{binary}")
    if not model_p.is_file():
        raise FileNotFoundError(f"piper 模型不存在：{model_path}")

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    proc = await asyncio.create_subprocess_exec(
        str(bin_p),
        "-m", str(model_p),
        "-f", str(out_p),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await proc.communicate(input=text.encode("utf-8"))
    if proc.returncode != 0:
        tail = (stderr or b"").decode("utf-8", "ignore").splitlines()[-8:]
        raise RuntimeError(
            f"piper 推理失败（rc={proc.returncode}）：\n" + "\n".join(tail)
        )
    if not (out_p.is_file() and out_p.stat().st_size > 0):
        raise RuntimeError(f"piper 未产出有效音频：{out_p}")
    return str(out_p)


class PiperTTSInput(BaseModel):
    text: str = Field(min_length=1, max_length=5000, description="要合成的文本")


@register
class PiperTTSSkill(Skill):
    node_type = "produce"
    name = "piper_tts"
    display_name = "离线语音合成"
    description = (
        "用 piper 在本地离线合成中文语音（无需 API key、无需联网）。"
        "edge-tts 在线配音不可用（断网/限流）时的备份方案，音色为 cmn 中文模型。"
        "用户明确要求'离线配音''本地合成''不联网'时调用。"
    )
    skill_category = "create"
    skill_priority = "warm"
    trigger_words = ["离线配音", "本地合成", "不联网配音", "piper"]
    input_schema = PiperTTSInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        params = PiperTTSInput.model_validate({
            k: v for k, v in inputs.items() if k in PiperTTSInput.model_fields
        })
        _OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent.parent / "outputs"
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = _OUTPUT_DIR / "tts_piper_output.wav"
        try:
            result_path = await synthesize_piper(params.text, out)
        except Exception as e:
            logger.exception("piper TTS failed")
            return {"error": f"离线语音合成失败: {e}"}
        return {
            "output_path": result_path,
            "text_length": len(params.text),
            "card_draft": {
                "title": "离线语音合成",
                "template": "piper_tts",
                "pages": [{
                    "id": "page_piper_tts", "type": "content", "mediaType": "audio",
                    "title": "离线语音合成",
                    "audioUrl": f"/outputs/{Path(result_path).name}",
                    "width": 800, "height": 200,
                }],
                "pngUrls": [], "htmlUrls": [],
            },
        }
