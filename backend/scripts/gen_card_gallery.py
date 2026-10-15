#!/usr/bin/env python3
"""生成 outputs/card-gallery.html —— 12 套主题 + 强调色轴的可视化总览。

与 gen_card_previews.py（产出 PNG 给前端静态目录）不同，本脚本只产出一份
单文件 HTML，方便直接在浏览器里对照配色与点缀轴效果，不需要 headless 浏览器。

用法：
    python scripts/gen_card_gallery.py
"""
from __future__ import annotations

import html
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parent / "outputs" / "card-gallery.html"

from app.cards.renderer import render_page  # noqa: E402
from app.cards.schema import THEMES, _accessible_accents  # noqa: E402
from scripts.gen_card_previews import build_sample_deck  # noqa: E402


def _scaled_frame(srcdoc: str, scale: float = 0.42) -> str:
    w = int(1080 * scale)
    h = int(1440 * scale)
    return (
        f'<div class="frame" style="width:{w}px;height:{h}px">'
        f'<iframe srcdoc={html.escape(srcdoc)!r} '
        f'style="width:1080px;height:1440px;transform:scale({scale});'
        f'transform-origin:top left;border:0"></iframe></div>'
    )


def main() -> int:
    # 每套主题用同一份示例内容（封面 / 清单 / 结尾），只换主题与点缀色，便于对照
    seq = ("cover_display", "list_ledger", "end_cta")

    sections: list[str] = []
    for name, spec in THEMES.items():
        accents = _accessible_accents(spec)
        deck = build_sample_deck(seq, name)
        # 默认强调色卡片
        default_card = render_page(deck, deck.pages[1], 1)
        frames = [_scaled_frame(default_card)]
        # 若有多个强调色，额外渲染 accent-1 那张，直观展示点缀轴
        if len(accents) > 1:
            deck.accent_index = 1
            alt_card = render_page(deck, deck.pages[1], 1)
            frames.append(_scaled_frame(alt_card))

        swatches = "".join(
            f'<span class="sw" title="强调色 {i}" style="background:{c}"></span>'
            for i, c in enumerate(accents)
        )
        sections.append(
            f'<section class="theme">'
            f'<div class="meta"><h2>{html.escape(spec["label"])} '
            f'<code>{html.escape(name)}</code></h2>'
            f'<p class="hint">{html.escape(spec.get("hint", ""))}</p>'
            f'<div class="swatches">{swatches}'
            f'<span class="cnt">{len(accents)} 个强调色</span></div></div>'
            f'<div class="cards">{"".join(frames)}</div>'
            f'<p class="note">左：默认强调色　右：accent-1（点缀轴切换）</p>'
            f'</section>'
        )

    doc = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>结构化卡片 · 配色与强调色轴总览</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:'Noto Sans SC','Microsoft YaHei',system-ui,sans-serif;
background:#0f1115;color:#e8eaed;padding:32px}}
h1{{font-size:24px;margin:0 0 4px}}
.sub{{color:#9aa0a6;margin:0 0 28px;font-size:14px}}
section.theme{{background:#171a21;border:1px solid #262b36;border-radius:12px;
padding:18px 20px;margin-bottom:22px}}
.meta h2{{font-size:18px;margin:0 0 4px}}
.meta h2 code{{font-size:13px;color:#7dd3fc;background:#0d1b2a;padding:2px 6px;border-radius:4px}}
.hint{{color:#9aa0a6;font-size:13px;margin:0 0 10px}}
.swatches{{display:flex;align-items:center;gap:8px;margin-bottom:12px}}
.sw{{width:22px;height:22px;border-radius:50%;border:2px solid #2a2f3a;display:inline-block}}
.cnt{{font-size:12px;color:#9aa0a6;margin-left:6px}}
.cards{{display:flex;gap:18px;flex-wrap:wrap}}
.frame{{overflow:hidden;border-radius:8px;background:#fff;box-shadow:0 6px 20px rgba(0,0,0,.35)}}
.note{{color:#6b7280;font-size:12px;margin:10px 0 0}}
footer{{color:#6b7280;font-size:12px;margin-top:30px}}
</style></head><body>
<h1>结构化卡片 · 配色与强调色轴总览</h1>
<p class="sub">第十一版：12 套差异化纸色 + 每套可切换的强调色板（accent axis）。共 {len(THEMES)} 套主题。</p>
{''.join(sections)}
<footer>由 scripts/gen_card_gallery.py 生成 · 渲染器 = backend/app/cards/renderer.py</footer>
</body></html>"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(f"OK  {OUT}  （{len(THEMES)} 套主题）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
