"""Text-to-Speech adapter using edge-tts (free, Microsoft Edge online voices).

Usage:
  python -m app.agents.prompts.scripts.tts_edge -t "Hello world" -o output.mp3 --voice zh-CN-XiaoxiaoNeural
  python -m app.agents.prompts.scripts.tts_edge -i script.txt -o output.mp3
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from typing import Any

import edge_tts

_DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"
_DEFAULT_RATE = "+0%"
_DEFAULT_VOLUME = "+0%"

VOICES_ZH = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",
    "xiaoyi": "zh-CN-XiaoyiNeural",
    "yunjian": "zh-CN-YunjianNeural",
    "yunxi": "zh-CN-YunxiNeural",
    "yunxia": "zh-CN-YunxiaNeural",
    "yunyang": "zh-CN-YunyangNeural",
}

VOICES_EN = {
    "aria": "en-US-AriaNeural",
    "jenny": "en-US-JennyNeural",
    "guy": "en-US-GuyNeural",
    "davis": "en-US-DavisNeural",
}


async def synthesize(
    text: str,
    output_path: str | Path = "output.mp3",
    voice: str = _DEFAULT_VOICE,
    rate: str = _DEFAULT_RATE,
    volume: str = _DEFAULT_VOLUME,
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
    await communicate.save(str(out))
    return out


def resolve_voice(name: str) -> str:
    if name in VOICES_ZH:
        return VOICES_ZH[name]
    if name in VOICES_EN:
        return VOICES_EN[name]
    return name


def main() -> None:
    parser = argparse.ArgumentParser(description="TTS using edge-tts")
    parser.add_argument("-t", "--text", help="Text to synthesize")
    parser.add_argument("-i", "--input", help="Text file path")
    parser.add_argument("-o", "--output", default="output.mp3")
    parser.add_argument("--voice", default=_DEFAULT_VOICE)
    parser.add_argument("--rate", default=_DEFAULT_RATE)
    parser.add_argument("--volume", default=_DEFAULT_VOLUME)

    args = parser.parse_args()

    if args.input:
        text = Path(args.input).read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        print("Error: provide --text or --input", file=__import__("sys").stderr)
        return

    voice = resolve_voice(args.voice)
    out = asyncio.run(synthesize(text, args.output, voice, args.rate, args.volume))
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()