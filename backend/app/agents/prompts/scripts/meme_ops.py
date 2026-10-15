"""Meme image operations using Pillow.

Two modes:
  classic  — top/bottom white text with black stroke overlaid on image
  reaction — colored caption bar above/below image

Usage:
  python -m app.agents.prompts.scripts.meme_ops classic --image in.png --top "TOP" --bottom "BOTTOM" -o out.png
  python -m app.agents.prompts.scripts.meme_ops reaction --image in.png --caption "caption" -o out.png
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_DEFAULT_FONT_SIZE = 72
_STROKE_WIDTH = 3
_STROKE_COLOR = (0, 0, 0)
_TEXT_COLOR = (255, 255, 255)
_CAPTION_BG = (0, 0, 0)
_CAPTION_TEXT_COLOR = (255, 255, 255)
_CAPTION_BAR_HEIGHT_RATIO = 0.18
_MAX_CHARS_PER_LINE = 14


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opengoogle/noto/NotoSansCJK-Regular.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _auto_font_size(img_width: int, text: str, max_ratio: float = 0.45) -> int:
    n_lines = max(1, -(-len(text) // _MAX_CHARS_PER_LINE))
    available = int(img_width * max_ratio / n_lines)
    return max(24, min(available, _DEFAULT_FONT_SIZE))


def _wrap_text(text: str, max_chars: int = _MAX_CHARS_PER_LINE) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    lines = textwrap.wrap(text, width=max_chars, break_long_words=False)
    return lines or [text]


def _draw_text_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    y_center: int,
    img_width: int,
    font: ImageFont.FreeTypeFont,
) -> None:
    lines = _wrap_text(text)
    line_spacing = font.size + 4
    total_h = len(lines) * line_spacing
    y_start = y_center - total_h // 2
    for i, line in enumerate(lines):
        bbox = font.getbbox(line)
        tw = bbox[2] - bbox[0]
        x = (img_width - tw) // 2
        y = y_start + i * line_spacing
        draw.text(
            (x, y), line, fill=_TEXT_COLOR, font=font,
            stroke_width=_STROKE_WIDTH, stroke_fill=_STROKE_COLOR,
        )


def render_classic(
    image_path: str | Path,
    top_text: str = "",
    bottom_text: str = "",
    output_path: str | Path | None = None,
) -> Path:
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    draw = ImageDraw.Draw(img)

    if top_text:
        font = _load_font(_auto_font_size(w, top_text))
        _draw_text_centered(draw, top_text, h // 6, w, font)

    if bottom_text:
        font = _load_font(_auto_font_size(w, bottom_text))
        _draw_text_centered(draw, bottom_text, h * 5 // 6, w, font)

    out = Path(output_path) if output_path else Path("meme_classic.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out, "PNG")
    return out


def render_reaction(
    image_path: str | Path,
    caption: str = "",
    output_path: str | Path | None = None,
) -> Path:
    img = Image.open(image_path).convert("RGBA")
    w, h = img.size
    bar_h = int(h * _CAPTION_BAR_HEIGHT_RATIO)
    canvas = Image.new("RGBA", (w, h + bar_h), _CAPTION_BG)
    canvas.paste(img, (0, bar_h))

    draw = ImageDraw.Draw(canvas)
    if caption:
        font = _load_font(min(_auto_font_size(w, caption, 0.85), bar_h - 10))
        _draw_text_centered(draw, caption, bar_h // 2, w, font)

    out = Path(output_path) if output_path else Path("meme_reaction.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(out, "PNG")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Meme image generator")
    sub = parser.add_subparsers(dest="mode", required=True)

    classic = sub.add_parser("classic")
    classic.add_argument("--image", required=True)
    classic.add_argument("--top", default="")
    classic.add_argument("--bottom", default="")
    classic.add_argument("-o", "--output", default=None)

    reaction = sub.add_parser("reaction")
    reaction.add_argument("--image", required=True)
    reaction.add_argument("--caption", default="")
    reaction.add_argument("-o", "--output", default=None)

    args = parser.parse_args()

    if args.mode == "classic":
        out = render_classic(args.image, args.top, args.bottom, args.output)
    else:
        out = render_reaction(args.image, args.caption, args.output)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()