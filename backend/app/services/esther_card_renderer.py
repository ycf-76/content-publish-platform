"""Esther Design System 卡片渲染器：HTML -> PNG。

基于 esther-design-system template-cards.html 完整还原：
- 品牌三色：主色(#2B7FD8)60% + 强调色(#F4D758)30% + 点缀色(#E84A5F)10%
- 暖底背景：#fefcf6(奶白) / #faf6eb(深奶)
- 墨色文字：#1A1A2E（非纯黑）
- 字体混搭：标题衬线(Noto Serif SC) + 正文无衬线(Noto Sans SC)
- 装饰数字：Fraunces italic oversized
- 封面网格质感、深色面板三色线、尾页oversized引号
"""

from __future__ import annotations

import logging
from typing import Any

from .card_renderer import (
    CARD_WIDTH,
    CARD_HEIGHT,
    _html_skeleton,
    _get_size_dimensions,
    render_html_to_base64,
)

logger = logging.getLogger(__name__)

ESTHER_BRAND = {
    "blue": "#2B7FD8",
    "yellow": "#F4D758",
    "red": "#E84A5F",
    "cream": "#fefcf6",
    "creamDark": "#faf6eb",
    "ink": "#1A1A2E",
    "inkLight": "#4A4A5A",
    "inkFaint": "#8A8A9A",
}

ESTHER_THEMES: dict[str, dict[str, str]] = {
    "esther_brand": {
        "name": "Esther品牌",
        "bg_primary": ESTHER_BRAND["cream"],
        "bg_secondary": ESTHER_BRAND["creamDark"],
        "text_primary": ESTHER_BRAND["ink"],
        "text_secondary": ESTHER_BRAND["inkLight"],
        "accent": ESTHER_BRAND["blue"],
        "accent_light": "#D6E9F8",
        "font_title": '"Noto Serif SC", "Songti SC", "Huiwen Mincho", Georgia, serif',
        "font_body": '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
    },
    "esther_dark": {
        "name": "Esther墨韵",
        "bg_primary": ESTHER_BRAND["ink"],
        "bg_secondary": "#2A2A3E",
        "text_primary": "#E8E4DE",
        "text_secondary": ESTHER_BRAND["inkFaint"],
        "accent": ESTHER_BRAND["yellow"],
        "accent_light": "#3A3A4E",
        "font_title": '"Noto Serif SC", "Songti SC", "Huiwen Mincho", Georgia, serif',
        "font_body": '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
    },
    "esther_warm": {
        "name": "Esther暖阳",
        "bg_primary": "#FFF8F0",
        "bg_secondary": "#FFE8D6",
        "text_primary": "#3E2F23",
        "text_secondary": "#8B7355",
        "accent": "#D97706",
        "accent_light": "#FDE68A",
        "font_title": '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
        "font_body": '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
    },
}


def _get_esther_theme(style_name: str) -> dict[str, str]:
    return ESTHER_THEMES.get(style_name, ESTHER_THEMES["esther_brand"])


_TRICOLOR_CSS = (
    f"background: linear-gradient(90deg, {ESTHER_BRAND['blue']} 60%, "
    f"{ESTHER_BRAND['yellow']} 80%, {ESTHER_BRAND['red']} 100%);"
)


def build_esther_cover_html(
    title: str,
    subtitle: str = "",
    highlight: str = "",
    tag: str = "",
    footer: str = "",
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    if highlight and highlight in title:
        title_parts = title.split(highlight, 1)
        title_html = (
            f'{title_parts[0]}<span class="highlight">{highlight}</span>'
            f'{title_parts[1] if len(title_parts) > 1 else ""}'
        )
    else:
        title_html = title or "今日分享"

    tag_display = tag or "笔记 · 精选"
    footer_display = footer or "@灵犀工坊"
    author_name = footer_display.replace("@", "") or "灵犀工坊"
    author_initial = author_name[0] if author_name else "E"

    body = f"""
    <div class="p-cover">
        <div class="deco-top"></div>
        <span class="cover-tag">{tag_display}</span>
        <h1 class="cover-title">{title_html}</h1>
        <p class="cover-subtitle">{subtitle}</p>
        <div class="cover-author-row">
            <div class="cover-avatar-ring">
                <div class="cover-avatar-placeholder">{author_initial}</div>
            </div>
            <div>
                <div class="cover-author-name">{author_name}</div>
                <div class="cover-author-desc">用设计让知识更好看</div>
            </div>
        </div>
        <div class="cover-grid-texture"></div>
    </div>"""

    css = f"""
    .p-cover {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        justify-content: center;
        padding: 80px 90px; position: relative;
    }}
    .deco-top {{
        position: absolute; top: 0; left: 0; right: 0;
        height: 8px; {_TRICOLOR_CSS} z-index: 3;
    }}
    .cover-tag {{
        font-size: 28px; font-weight: 700; color: #fff;
        background: {ESTHER_BRAND['blue']};
        display: inline-block; padding: 8px 24px;
        border-radius: 6px; margin-bottom: 40px;
        letter-spacing: 2px; align-self: flex-start;
        font-family: {theme['font_body']};
    }}
    .cover-title {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 88px; line-height: 1.2;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 24px 0;
        word-break: break-word;
    }}
    .highlight {{ color: {ESTHER_BRAND['blue']}; }}
    .cover-subtitle {{
        font-size: 42px; color: {ESTHER_BRAND['inkLight']};
        font-weight: 500; line-height: 1.6; margin: 0 0 80px 0;
        font-family: {theme['font_body']};
    }}
    .cover-author-row {{
        display: flex; align-items: center; gap: 24px; margin-top: auto;
    }}
    .cover-avatar-ring {{
        width: 88px; height: 88px; border-radius: 50%;
        border: 4px solid {ESTHER_BRAND['yellow']};
        display: flex; align-items: center; justify-content: center;
        overflow: hidden; flex-shrink: 0;
    }}
    .cover-avatar-placeholder {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['blue']}; color: #fff;
        font-size: 36px; font-weight: 700;
        display: flex; align-items: center; justify-content: center;
        font-family: {theme['font_title']};
    }}
    .cover-author-name {{
        font-size: 36px; font-weight: 700; color: {ESTHER_BRAND['ink']};
        font-family: {theme['font_body']};
    }}
    .cover-author-desc {{
        font-size: 24px; color: {ESTHER_BRAND['inkLight']}; margin-top: 4px;
        font-family: {theme['font_body']};
    }}
    .cover-grid-texture {{
        position: absolute; top: 0; left: 0; right: 0; bottom: 0;
        background-image:
            linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px);
        background-size: 40px 40px;
        z-index: 0; pointer-events: none;
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


def build_esther_dark_panel_html(
    title: str,
    items: list[str],
    emoji: str = "",
    deco_number: str = "",
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    default_emojis = ["💡", "⚡", "🔥", "🎯", "🚀"]
    items_html = ""
    for i, item in enumerate(items):
        icon = default_emojis[i % len(default_emojis)]
        items_html += f"""
        <div class="dark-item">
            <span class="dark-item-icon">{icon}</span>
            <span class="dark-item-text">{item}</span>
        </div>"""

    deco_num_html = f'<span class="dark-page-num">{deco_number or "02"}</span>'
    emoji_html = f'<p class="dark-sub">{emoji}</p>' if emoji else ""

    body = f"""
    <div class="p-dark">
        {deco_num_html}
        <h2 class="dark-title">{title}</h2>
        {emoji_html}
        <div class="dark-items">{items_html}</div>
        <div class="dark-deco-line"></div>
    </div>"""

    css = f"""
    .p-dark {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['ink']}; color: #e8e4de;
        display: flex; flex-direction: column;
        padding: 80px 80px; position: relative;
    }}
    .dark-page-num {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 120px; font-weight: 700;
        color: {ESTHER_BRAND['yellow']}; opacity: 0.15;
        position: absolute; top: 40px; right: 80px;
        line-height: 1; user-select: none;
    }}
    .dark-title {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 52px;
        color: {ESTHER_BRAND['cream']}; margin-bottom: 16px;
    }}
    .dark-sub {{
        font-size: 48px; color: {ESTHER_BRAND['yellow']};
        margin-bottom: 60px; font-weight: 500;
    }}
    .dark-items {{
        flex: 1; display: flex; flex-direction: column;
        justify-content: center; gap: 36px;
    }}
    .dark-item {{
        display: flex; align-items: flex-start; gap: 24px;
    }}
    .dark-item-icon {{
        font-size: 40px; flex-shrink: 0; width: 56px; text-align: center;
    }}
    .dark-item-text {{
        font-size: 38px; color: #e8e4de;
        line-height: 1.5; font-weight: 500;
        font-family: {theme['font_body']};
    }}
    .dark-deco-line {{
        position: absolute; bottom: 80px; left: 80px; right: 80px;
        height: 4px;
        background: linear-gradient(90deg, {ESTHER_BRAND['blue']} 50%, {ESTHER_BRAND['yellow']} 75%, {ESTHER_BRAND['red']} 100%);
        border-radius: 2px; opacity: 0.6;
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["ink"])


def build_esther_content_html(
    title: str,
    content: str,
    deco_number: str = "",
    footer: str = "",
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
    paras_html = "".join(f'<p class="list-paragraph">{p}</p>' for p in paragraphs)
    footer_html = f'<div class="list-footer">{footer}</div>' if footer else ""

    body = f"""
    <div class="p-list">
        <span class="list-page-num">{deco_number or "03"}</span>
        <h2 class="list-title">{title or "正文"}</h2>
        <div class="list-content-area">{paras_html}</div>
        {footer_html}
    </div>"""

    css = f"""
    .p-list {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        padding: 72px 80px; position: relative;
    }}
    .list-page-num {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 120px; font-weight: 700;
        color: {ESTHER_BRAND['blue']}; opacity: 0.12;
        position: absolute; top: 40px; right: 80px;
        line-height: 1; user-select: none;
    }}
    .list-title {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 52px;
        margin-bottom: 48px; color: {ESTHER_BRAND['ink']};
        position: relative;
    }}
    .list-title::after {{
        content: ''; display: block;
        width: 80px; height: 6px;
        background: {ESTHER_BRAND['yellow']};
        margin-top: 16px; border-radius: 3px;
    }}
    .list-content-area {{
        flex: 1; display: flex; flex-direction: column;
        justify-content: center; gap: 28px;
    }}
    .list-paragraph {{
        font-size: 38px; line-height: 1.8;
        color: {ESTHER_BRAND['ink']}; margin: 0;
        word-break: break-word; font-family: {theme['font_body']};
    }}
    .list-footer {{
        font-size: 28px; color: {ESTHER_BRAND['inkLight']};
        padding-top: 24px; border-top: 2px solid {ESTHER_BRAND['creamDark']};
        font-family: {theme['font_body']};
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


def build_esther_quote_html(
    quote: str,
    footer: str = "",
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    body = f"""
    <div class="p-quote">
        <div class="quote-deco-top"></div>
        <div class="quote-mark">"</div>
        <p class="quote-text">{quote or "金句"}</p>
        <p class="quote-attr">{footer}</p>
        <div class="quote-deco-bottom"></div>
    </div>"""

    css = f"""
    .p-quote {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        justify-content: center; align-items: center;
        padding: 80px 90px; text-align: center; position: relative;
    }}
    .quote-deco-top {{
        position: absolute; top: 0; left: 0; right: 0;
        height: 8px; {_TRICOLOR_CSS} z-index: 3;
    }}
    .quote-mark {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 200px; color: {ESTHER_BRAND['blue']}; opacity: 0.15;
        line-height: 0.6; margin-bottom: -20px; user-select: none;
    }}
    .quote-text {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 60px; line-height: 1.5;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 32px 0;
        max-width: 900px; word-break: break-word;
    }}
    .quote-attr {{
        font-size: 32px; color: {ESTHER_BRAND['inkLight']}; font-weight: 500;
        font-family: {theme['font_body']};
    }}
    .quote-deco-bottom {{
        position: absolute; bottom: 0; left: 0; right: 0;
        height: 8px; {_TRICOLOR_CSS} z-index: 3;
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


def build_esther_list_html(
    title: str,
    items: list[str],
    footer: str = "",
    deco_number: str = "",
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    items_html = ""
    for i, item in enumerate(items):
        alt_class = " list-row-alt" if i % 2 == 1 else ""
        items_html += f"""
        <div class="list-row{alt_class}">
            <span class="list-row-num">{i+1:02d}</span>
            <span class="list-row-text">{item}</span>
        </div>"""

    footer_html = f'<div class="list-footer">{footer}</div>' if footer else ""

    body = f"""
    <div class="p-list">
        <span class="list-page-num">{deco_number or "04"}</span>
        <h2 class="list-title">{title}</h2>
        <div class="list-content-area">{items_html}</div>
        {footer_html}
    </div>"""

    css = f"""
    .p-list {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        padding: 72px 80px; position: relative;
    }}
    .list-page-num {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 120px; font-weight: 700;
        color: {ESTHER_BRAND['blue']}; opacity: 0.12;
        position: absolute; top: 40px; right: 80px;
        line-height: 1; user-select: none;
    }}
    .list-title {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 52px;
        margin-bottom: 48px; color: {ESTHER_BRAND['ink']};
        position: relative;
    }}
    .list-title::after {{
        content: ''; display: block;
        width: 80px; height: 6px;
        background: {ESTHER_BRAND['yellow']};
        margin-top: 16px; border-radius: 3px;
    }}
    .list-content-area {{
        flex: 1; display: flex; flex-direction: column;
        justify-content: center; gap: 0;
    }}
    .list-row {{
        display: flex; align-items: flex-start; gap: 24px;
        padding: 24px 28px; border-radius: 12px;
    }}
    .list-row-alt {{
        background: {ESTHER_BRAND['creamDark']};
    }}
    .list-row-num {{
        font-family: 'Fraunces', Georgia, serif;
        font-size: 36px; font-weight: 700;
        color: {ESTHER_BRAND['blue']}; flex-shrink: 0; min-width: 56px;
    }}
    .list-row-text {{
        font-size: 38px; line-height: 1.6;
        color: {ESTHER_BRAND['ink']}; word-break: break-word;
        font-family: {theme['font_body']};
    }}
    .list-footer {{
        font-size: 28px; color: {ESTHER_BRAND['inkLight']};
        padding-top: 24px; border-top: 2px solid {ESTHER_BRAND['creamDark']};
        font-family: {theme['font_body']};
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


def build_esther_end_page_html(
    quote: str,
    cta_text: str = "",
    footer: str = "",
    deco_symbol: str = '"',
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    footer_display = footer or "@灵犀工坊"
    author_name = footer_display.replace("@", "") or "灵犀工坊"
    author_initial = author_name[0] if author_name else "E"

    body = f"""
    <div class="p-end">
        <div class="end-deco-bottom"></div>
        <div class="end-quote-mark">{deco_symbol}</div>
        <p class="end-quote">{quote or "一句让人记住你的话。"}</p>
        <div class="end-avatar-ring">
            <div class="end-avatar-placeholder">{author_initial}</div>
        </div>
        <p class="end-author-name">{author_name}</p>
        <p class="end-cta">{cta_text or "关注我，获取更多"}</p>
        <p class="end-tagline">用设计让知识更好看<br>Design makes knowledge beautiful</p>
    </div>"""

    css = f"""
    .p-end {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        justify-content: center; align-items: center;
        padding: 80px 90px; text-align: center; position: relative;
    }}
    .end-deco-bottom {{
        position: absolute; bottom: 0; left: 0; right: 0;
        height: 8px; {_TRICOLOR_CSS} z-index: 3;
    }}
    .end-quote-mark {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 200px; color: {ESTHER_BRAND['blue']}; opacity: 0.15;
        line-height: 0.6; margin-bottom: -20px; user-select: none;
    }}
    .end-quote {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 60px; line-height: 1.5;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 32px 0;
        max-width: 900px; word-break: break-word;
    }}
    .end-avatar-ring {{
        width: 100px; height: 100px; border-radius: 50%;
        border: 3px solid {ESTHER_BRAND['yellow']};
        display: flex; align-items: center; justify-content: center;
        overflow: hidden; flex-shrink: 0; margin-bottom: 20px;
    }}
    .end-avatar-placeholder {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['blue']}; color: #fff;
        font-size: 40px; font-weight: 700;
        display: flex; align-items: center; justify-content: center;
        font-family: {theme['font_title']};
    }}
    .end-author-name {{
        font-size: 40px; font-weight: 700;
        color: {ESTHER_BRAND['ink']}; margin-bottom: 8px;
        font-family: {theme['font_body']};
    }}
    .end-cta {{
        font-size: 32px; color: {ESTHER_BRAND['blue']};
        font-weight: 600; margin-bottom: 48px;
        font-family: {theme['font_body']};
    }}
    .end-tagline {{
        font-size: 26px; color: {ESTHER_BRAND['inkLight']};
        letter-spacing: 2px; line-height: 1.6;
        font-family: {theme['font_body']};
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


def build_esther_compare_html(
    title: str,
    left_title: str = "传统做法",
    right_title: str = "新方法",
    left_items: list[str] | None = None,
    right_items: list[str] | None = None,
    deco_number: str = "",
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    left_items = left_items or ["效率低", "成本高"]
    right_items = right_items or ["效率高", "成本低"]

    left_items_html = "".join(
        f'<div class="compare-row compare-row-left">{item}</div>'
        for item in left_items
    )
    right_items_html = "".join(
        f'<div class="compare-row compare-row-right">{item}</div>'
        for item in right_items
    )

    body = f"""
    <div class="p-compare">
        <span class="compare-page-num">{deco_number or "05"}</span>
        <h2 class="compare-title">{title}</h2>
        <div class="compare-columns">
            <div class="compare-col compare-col-left">
                <div class="compare-col-head">
                    <span class="compare-icon compare-icon-x">✕</span>
                    <span class="compare-col-label">{left_title}</span>
                </div>
                {left_items_html}
            </div>
            <div class="compare-col compare-col-right">
                <div class="compare-col-head">
                    <span class="compare-icon compare-icon-check">✓</span>
                    <span class="compare-col-label">{right_title}</span>
                </div>
                {right_items_html}
            </div>
        </div>
    </div>"""

    css = f"""
    .p-compare {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        padding: 72px 80px; position: relative;
    }}
    .compare-page-num {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 120px; font-weight: 700;
        color: {ESTHER_BRAND['blue']}; opacity: 0.12;
        position: absolute; top: 40px; right: 80px;
        line-height: 1; user-select: none;
    }}
    .compare-title {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 52px;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 16px 0;
    }}
    .compare-title::after {{
        content: ''; display: block;
        width: 80px; height: 6px;
        background: {ESTHER_BRAND['yellow']};
        margin-top: 16px; border-radius: 3px;
    }}
    .compare-columns {{
        flex: 1; display: grid;
        grid-template-columns: 1fr 1fr; gap: 24px;
        margin-top: 40px; align-content: center;
    }}
    .compare-col {{
        display: flex; flex-direction: column; gap: 16px;
        padding: 32px 28px; border-radius: 16px;
    }}
    .compare-col-left {{
        background: rgba(232, 74, 95, 0.06);
        border: 2px solid rgba(232, 74, 95, 0.15);
    }}
    .compare-col-right {{
        background: rgba(43, 127, 216, 0.06);
        border: 2px solid rgba(43, 127, 216, 0.15);
    }}
    .compare-col-head {{
        display: flex; align-items: center; gap: 12px; margin-bottom: 8px;
    }}
    .compare-icon {{
        width: 44px; height: 44px; border-radius: 50%;
        display: flex; align-items: center; justify-content: center;
        font-size: 22px; font-weight: 700; flex-shrink: 0;
    }}
    .compare-icon-x {{
        background: {ESTHER_BRAND['red']}; color: #fff;
    }}
    .compare-icon-check {{
        background: {ESTHER_BRAND['blue']}; color: #fff;
    }}
    .compare-col-label {{
        font-size: 36px; font-weight: 700;
        color: {ESTHER_BRAND['ink']};
        font-family: {theme['font_title']};
    }}
    .compare-row {{
        font-size: 34px; line-height: 1.5;
        padding: 14px 18px; border-radius: 10px;
        font-family: {theme['font_body']};
    }}
    .compare-row-left {{
        background: rgba(232, 74, 95, 0.06); color: #8B3A3A;
    }}
    .compare-row-right {{
        background: rgba(43, 127, 216, 0.06); color: #1A4A7A;
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


def build_esther_icon_text_html(
    title: str,
    pairs: list[dict[str, str]],
    deco_number: str = "",
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    color_classes = ["icontext-icon-blue", "icontext-icon-yellow", "icontext-icon-red"]
    pairs_html = ""
    for i, pair in enumerate(pairs):
        color_cls = color_classes[i % 3]
        pairs_html += f"""
        <div class="icontext-card">
            <div class="icontext-icon-area {color_cls}">{pair.get('icon', '🎯')}</div>
            <div class="icontext-card-title">{pair.get('text', '')}</div>
        </div>"""

    body = f"""
    <div class="p-icon-text">
        <span class="icontext-page-num">{deco_number or "06"}</span>
        <h2 class="icontext-title">{title}</h2>
        <div class="icontext-grid">{pairs_html}</div>
    </div>"""

    css = f"""
    .p-icon-text {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        padding: 72px 80px; position: relative;
    }}
    .icontext-page-num {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 120px; font-weight: 700;
        color: {ESTHER_BRAND['blue']}; opacity: 0.12;
        position: absolute; top: 40px; right: 80px;
        line-height: 1; user-select: none;
    }}
    .icontext-title {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 52px;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 16px 0;
    }}
    .icontext-title::after {{
        content: ''; display: block;
        width: 80px; height: 6px;
        background: {ESTHER_BRAND['yellow']};
        margin-top: 16px; border-radius: 3px;
    }}
    .icontext-grid {{
        flex: 1; display: grid;
        grid-template-columns: 1fr 1fr; gap: 24px;
        align-content: center; margin-top: 40px;
    }}
    .icontext-card {{
        position: relative; padding: 36px 28px 28px;
        background: #fff; border-radius: 16px;
        overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        display: flex; flex-direction: column;
        align-items: center; text-align: center; gap: 16px;
    }}
    .icontext-icon-area {{
        width: 80px; height: 80px; border-radius: 20px;
        display: flex; align-items: center; justify-content: center;
        font-size: 40px;
    }}
    .icontext-icon-blue {{ background: rgba(43, 127, 216, 0.1); }}
    .icontext-icon-yellow {{ background: rgba(244, 215, 88, 0.25); }}
    .icontext-icon-red {{ background: rgba(232, 74, 95, 0.1); }}
    .icontext-card-title {{
        font-family: {theme['font_title']};
        font-size: 32px; font-weight: 700;
        color: {ESTHER_BRAND['ink']}; line-height: 1.4;
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


def build_esther_steps_html(
    title: str,
    steps: list[dict[str, str]],
    deco_number: str = "",
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    step_colors = [ESTHER_BRAND["blue"], ESTHER_BRAND["yellow"], ESTHER_BRAND["red"]]
    steps_html = ""
    for i, step in enumerate(steps):
        color = step_colors[i % 3]
        steps_html += f"""
        <div class="step-block">
            <div class="step-arrow-head" style="background: {color}"></div>
            <div class="step-content">
                <span class="step-num" style="color: {color}">{i+1:02d}</span>
                <div class="step-text">
                    <h3 class="step-name">{step.get('title', '')}</h3>
                    <p class="step-desc">{step.get('desc', '')}</p>
                </div>
            </div>
        </div>"""

    body = f"""
    <div class="p-steps">
        <div class="deco-top"></div>
        <span class="steps-page-num">{deco_number or "01"}</span>
        <h2 class="steps-title">{title}</h2>
        <div class="steps-flow">{steps_html}</div>
        <div class="steps-grid-texture"></div>
    </div>"""

    css = f"""
    .p-steps {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        padding: 72px 80px; position: relative;
    }}
    .deco-top {{
        position: absolute; top: 0; left: 0; right: 0;
        height: 8px; {_TRICOLOR_CSS} z-index: 3;
    }}
    .steps-page-num {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 120px; font-weight: 700;
        color: {ESTHER_BRAND['blue']}; opacity: 0.12;
        position: absolute; top: 40px; right: 80px;
        line-height: 1; user-select: none;
    }}
    .steps-title {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 52px;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 16px 0;
    }}
    .steps-title::after {{
        content: ''; display: block;
        width: 80px; height: 6px;
        background: {ESTHER_BRAND['yellow']};
        margin-top: 16px; border-radius: 3px;
    }}
    .steps-flow {{
        flex: 1; display: flex; flex-direction: column;
        justify-content: center; gap: 0; margin-top: 40px;
    }}
    .step-block {{
        position: relative; display: flex; align-items: stretch; gap: 0;
    }}
    .step-arrow-head {{
        width: 48px; flex-shrink: 0;
        display: flex; align-items: center; justify-content: center;
        position: relative;
    }}
    .step-content {{
        flex: 1; background: #fff; border-radius: 16px;
        padding: 32px 36px; margin: 8px 0;
        box-shadow: 0 2px 8px rgba(0,0,0,0.04);
        display: flex; align-items: center; gap: 28px;
    }}
    .step-num {{
        font-family: 'Fraunces', Georgia, serif;
        font-size: 56px; font-weight: 900;
        line-height: 1; flex-shrink: 0; opacity: 0.8;
    }}
    .step-text {{ flex: 1; }}
    .step-name {{
        font-family: {theme['font_title']};
        font-size: 40px; font-weight: 900;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 8px 0;
    }}
    .step-desc {{
        font-size: 32px; color: {ESTHER_BRAND['inkLight']};
        line-height: 1.5; margin: 0;
        font-family: {theme['font_body']};
    }}
    .steps-grid-texture {{
        position: absolute; top: 0; left: 0; right: 0; bottom: 0;
        background-image:
            linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px);
        background-size: 40px 40px;
        z-index: 0; pointer-events: none;
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


def build_esther_code_panel_html(
    title: str,
    code_content: str = "",
    code_lang: str = "code",
    deco_number: str = "",
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    import html as html_module
    escaped_code = html_module.escape(code_content or "// code here")

    body = f"""
    <div class="p-code">
        <div class="deco-top"></div>
        <span class="code-page-num">{deco_number or "02"}</span>
        <h2 class="code-title">{title}</h2>
        <div class="code-panel">
            <div class="code-title-bar">
                <span class="code-dot code-dot-red"></span>
                <span class="code-dot code-dot-yellow"></span>
                <span class="code-dot code-dot-green"></span>
                <span class="code-lang">{code_lang}</span>
            </div>
            <pre class="code-body"><code>{escaped_code}</code></pre>
        </div>
        <div class="code-grid-texture"></div>
    </div>"""

    css = f"""
    .p-code {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        padding: 72px 80px; position: relative;
    }}
    .deco-top {{
        position: absolute; top: 0; left: 0; right: 0;
        height: 8px; {_TRICOLOR_CSS} z-index: 3;
    }}
    .code-page-num {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 120px; font-weight: 700;
        color: {ESTHER_BRAND['blue']}; opacity: 0.12;
        position: absolute; top: 40px; right: 80px;
        line-height: 1; user-select: none;
    }}
    .code-title {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 52px;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 16px 0;
    }}
    .code-title::after {{
        content: ''; display: block;
        width: 80px; height: 6px;
        background: {ESTHER_BRAND['yellow']};
        margin-top: 16px; border-radius: 3px;
    }}
    .code-panel {{
        flex: 1; background: #1a1a2e; border-radius: 16px;
        overflow: hidden; margin-top: 40px;
        display: flex; flex-direction: column;
        box-shadow: 0 8px 32px rgba(0,0,0,0.15);
    }}
    .code-title-bar {{
        display: flex; align-items: center; gap: 10px;
        padding: 20px 28px; background: #151821;
        border-bottom: 1px solid rgba(255,255,255,0.08);
    }}
    .code-dot {{
        width: 16px; height: 16px; border-radius: 50%;
    }}
    .code-dot-red {{ background: #E84A5F; }}
    .code-dot-yellow {{ background: #F4D758; }}
    .code-dot-green {{ background: #4ade80; }}
    .code-lang {{
        font-family: 'Fira Code', 'Consolas', monospace;
        font-size: 22px; color: #8A8A9A;
        margin-left: auto; text-transform: uppercase; letter-spacing: 1px;
    }}
    .code-body {{
        flex: 1; margin: 0; padding: 32px 36px;
        font-family: 'Fira Code', 'Consolas', 'Courier New', monospace;
        font-size: 30px; line-height: 1.7;
        color: #e8e4de; overflow: hidden;
        white-space: pre; tab-size: 4;
    }}
    .code-grid-texture {{
        position: absolute; top: 0; left: 0; right: 0; bottom: 0;
        background-image:
            linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px);
        background-size: 40px 40px;
        z-index: 0; pointer-events: none;
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


def build_esther_numbered_cards_html(
    title: str,
    items: list[dict[str, str]],
    deco_number: str = "",
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    step_colors = [ESTHER_BRAND["blue"], ESTHER_BRAND["yellow"], ESTHER_BRAND["red"]]
    items_html = ""
    for i, item in enumerate(items):
        color = step_colors[i % 3]
        items_html += f"""
        <div class="numcard-item">
            <span class="numcard-num" style="color: {color}">{i+1:02d}</span>
            <div class="numcard-body">
                <h3 class="numcard-name">{item.get('title', '')}</h3>
                <p class="numcard-desc">{item.get('desc', '')}</p>
            </div>
        </div>"""

    body = f"""
    <div class="p-numcards">
        <div class="deco-top"></div>
        <span class="numcards-page-num">{deco_number or "03"}</span>
        <h2 class="numcards-title">{title}</h2>
        <div class="numcards-grid">{items_html}</div>
        <div class="numcards-grid-texture"></div>
    </div>"""

    css = f"""
    .p-numcards {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        padding: 72px 80px; position: relative;
    }}
    .deco-top {{
        position: absolute; top: 0; left: 0; right: 0;
        height: 8px; {_TRICOLOR_CSS} z-index: 3;
    }}
    .numcards-page-num {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 120px; font-weight: 700;
        color: {ESTHER_BRAND['blue']}; opacity: 0.12;
        position: absolute; top: 40px; right: 80px;
        line-height: 1; user-select: none;
    }}
    .numcards-title {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 52px;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 16px 0;
    }}
    .numcards-title::after {{
        content: ''; display: block;
        width: 80px; height: 6px;
        background: {ESTHER_BRAND['yellow']};
        margin-top: 16px; border-radius: 3px;
    }}
    .numcards-grid {{
        flex: 1; display: flex; flex-direction: column;
        gap: 24px; margin-top: 40px; justify-content: center;
    }}
    .numcard-item {{
        display: flex; align-items: flex-start; gap: 28px;
        background: #fff; border-radius: 16px;
        padding: 36px 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    }}
    .numcard-num {{
        font-family: 'Fraunces', Georgia, serif;
        font-size: 64px; font-weight: 900;
        line-height: 1; flex-shrink: 0; opacity: 0.7;
    }}
    .numcard-body {{ flex: 1; }}
    .numcard-name {{
        font-family: {theme['font_title']};
        font-size: 38px; font-weight: 900;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 8px 0; line-height: 1.3;
    }}
    .numcard-desc {{
        font-size: 30px; color: {ESTHER_BRAND['inkLight']};
        line-height: 1.5; margin: 0;
        font-family: {theme['font_body']};
    }}
    .numcards-grid-texture {{
        position: absolute; top: 0; left: 0; right: 0; bottom: 0;
        background-image:
            linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px);
        background-size: 40px 40px;
        z-index: 0; pointer-events: none;
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


def build_esther_newspaper_html(
    masthead: str = "THE DAILY BRIEF",
    columns: list[dict[str, str]] | None = None,
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    columns = columns or [
        {"headline": "核心发现", "body": "简要描述"},
        {"headline": "关键数据", "body": "简要描述"},
        {"headline": "行动建议", "body": "简要描述"},
    ]

    cols_html = ""
    for i, col in enumerate(columns):
        border_cls = " newspaper-col-border" if i < len(columns) - 1 else ""
        cols_html += f"""
        <div class="newspaper-col{border_cls}">
            <h3 class="newspaper-headline">{col.get('headline', '')}</h3>
            <p class="newspaper-body">{col.get('body', '')}</p>
        </div>"""

    body = f"""
    <div class="p-newspaper">
        <div class="deco-top"></div>
        <div class="newspaper-masthead">{masthead}</div>
        <div class="newspaper-divider"></div>
        <div class="newspaper-columns">{cols_html}</div>
        <div class="newspaper-footer-bar"></div>
    </div>"""

    css = f"""
    .p-newspaper {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        padding: 72px 80px; position: relative;
    }}
    .deco-top {{
        position: absolute; top: 0; left: 0; right: 0;
        height: 8px; {_TRICOLOR_CSS} z-index: 3;
    }}
    .newspaper-masthead {{
        font-family: 'Fraunces', Georgia, serif;
        font-weight: 900; font-size: 56px;
        letter-spacing: 8px; text-align: center;
        color: {ESTHER_BRAND['ink']};
        border-top: 4px solid {ESTHER_BRAND['ink']};
        border-bottom: 4px solid {ESTHER_BRAND['ink']};
        padding: 20px 0; margin-bottom: 0;
    }}
    .newspaper-divider {{
        height: 2px;
        background: linear-gradient(90deg, {ESTHER_BRAND['blue']} 60%, {ESTHER_BRAND['yellow']} 80%, {ESTHER_BRAND['red']} 100%);
        margin: 0;
    }}
    .newspaper-columns {{
        flex: 1; display: flex; gap: 0; align-items: stretch;
    }}
    .newspaper-col {{
        flex: 1; padding: 32px 28px;
        display: flex; flex-direction: column;
    }}
    .newspaper-col-border {{
        border-right: 1px solid rgba(26, 26, 46, 0.15);
    }}
    .newspaper-headline {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 36px; line-height: 1.3;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 16px 0;
        border-bottom: 2px solid {ESTHER_BRAND['yellow']};
        padding-bottom: 12px;
    }}
    .newspaper-body {{
        font-size: 28px; line-height: 1.7;
        color: {ESTHER_BRAND['inkLight']}; margin: 0;
        font-family: {theme['font_body']};
    }}
    .newspaper-footer-bar {{
        height: 4px;
        background: linear-gradient(90deg, {ESTHER_BRAND['blue']} 60%, {ESTHER_BRAND['yellow']} 80%, {ESTHER_BRAND['red']} 100%);
        margin-top: auto; border-radius: 2px;
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


def build_esther_big_quote_html(
    quote: str,
    footer: str = "",
    deco_symbol: str = '"',
    style_name: str = "esther_brand",
    size: str = "3:4",
) -> str:
    theme = _get_esther_theme(style_name)
    width, height = _get_size_dimensions(size)

    body = f"""
    <div class="p-bigquote">
        <div class="bigquote-deco-top"></div>
        <div class="bigquote-mark">{deco_symbol}</div>
        <p class="bigquote-text">{quote or "一句足够大的话"}</p>
        <p class="bigquote-attr">{footer}</p>
        <div class="bigquote-deco-bottom"></div>
        <div class="bigquote-grid-texture"></div>
    </div>"""

    css = f"""
    .p-bigquote {{
        width: 100%; height: 100%;
        background: {ESTHER_BRAND['cream']};
        display: flex; flex-direction: column;
        justify-content: center; align-items: center;
        padding: 80px 90px; text-align: center; position: relative;
    }}
    .bigquote-deco-top {{
        position: absolute; top: 0; left: 0; right: 0;
        height: 8px; {_TRICOLOR_CSS} z-index: 3;
    }}
    .bigquote-mark {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 260px; color: {ESTHER_BRAND['blue']}; opacity: 0.12;
        line-height: 0.5; margin-bottom: -40px; user-select: none;
    }}
    .bigquote-text {{
        font-family: {theme['font_title']};
        font-weight: 900; font-size: 72px; line-height: 1.4;
        color: {ESTHER_BRAND['ink']}; margin: 0 0 40px 0;
        max-width: 900px; word-break: break-word;
    }}
    .bigquote-attr {{
        font-family: 'Fraunces', Georgia, serif; font-style: italic;
        font-size: 32px; color: {ESTHER_BRAND['blue']}; font-weight: 500;
    }}
    .bigquote-deco-bottom {{
        position: absolute; bottom: 0; left: 0; right: 0;
        height: 8px; {_TRICOLOR_CSS} z-index: 3;
    }}
    .bigquote-grid-texture {{
        position: absolute; top: 0; left: 0; right: 0; bottom: 0;
        background-image:
            linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px);
        background-size: 40px 40px;
        z-index: 0; pointer-events: none;
    }}
    """

    return _html_skeleton(body, css, width, height, ESTHER_BRAND["cream"])


ESTHER_TEMPLATE_BUILDERS = {
    "esther_cover": build_esther_cover_html,
    "esther_content": build_esther_content_html,
    "esther_dark_panel": build_esther_dark_panel_html,
    "esther_end_page": build_esther_end_page_html,
    "esther_compare": build_esther_compare_html,
    "esther_icon_text": build_esther_icon_text_html,
    "esther_list": build_esther_list_html,
    "esther_quote": build_esther_quote_html,
    "esther_steps": build_esther_steps_html,
    "esther_code_panel": build_esther_code_panel_html,
    "esther_numbered_cards": build_esther_numbered_cards_html,
    "esther_newspaper": build_esther_newspaper_html,
    "esther_big_quote": build_esther_big_quote_html,
}


async def render_esther_template_to_base64(
    template_type: str,
    data: dict,
    style: str = "esther_brand",
    size: str = "3:4",
) -> str:
    style_name = style or "esther_brand"
    size_name = size or "3:4"

    if template_type == "esther_cover":
        html = build_esther_cover_html(
            title=str(data.get("title", "")).strip() or "今日分享",
            subtitle=str(data.get("subtitle", "")).strip(),
            highlight=str(data.get("highlight", "")).strip(),
            tag=str(data.get("tag", "")).strip(),
            footer=str(data.get("footer", "")).strip(),
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_content":
        html = build_esther_content_html(
            title=str(data.get("title", "")).strip() or "正文",
            content=str(data.get("content", "")).strip(),
            deco_number=str(data.get("decoNumber", "")).strip(),
            footer=str(data.get("footer", "")).strip(),
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_dark_panel":
        items = data.get("listItems", data.get("items", []))
        if not items:
            raise ValueError("esther_dark_panel template requires 'listItems' or 'items' field")
        html = build_esther_dark_panel_html(
            title=str(data.get("title", "")).strip() or "核心要点",
            items=[str(item) for item in items],
            emoji=str(data.get("emoji", "")).strip(),
            deco_number=str(data.get("decoNumber", "")).strip(),
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_end_page":
        html = build_esther_end_page_html(
            quote=str(data.get("content", data.get("quote", ""))).strip() or "一句让人记住你的话。",
            cta_text=str(data.get("ctaText", "")).strip(),
            footer=str(data.get("footer", "")).strip(),
            deco_symbol=str(data.get("decoNumber", '"')).strip(),
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_compare":
        left_items = data.get("compareLeftItems", data.get("left_items", []))
        right_items = data.get("compareRightItems", data.get("right_items", []))
        if not left_items or not right_items:
            raise ValueError("esther_compare template requires 'compareLeftItems' and 'compareRightItems'")
        html = build_esther_compare_html(
            title=str(data.get("title", "")).strip() or "对比分析",
            left_title=str(data.get("compareLeftTitle", "传统做法")).strip(),
            right_title=str(data.get("compareRightTitle", "新方法")).strip(),
            left_items=[str(item) for item in left_items],
            right_items=[str(item) for item in right_items],
            deco_number=str(data.get("decoNumber", "")).strip(),
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_icon_text":
        pairs = data.get("iconTextPairs", data.get("pairs", []))
        if not pairs:
            raise ValueError("esther_icon_text template requires 'iconTextPairs' or 'pairs' field")
        html = build_esther_icon_text_html(
            title=str(data.get("title", "")).strip() or "核心能力",
            pairs=pairs,
            deco_number=str(data.get("decoNumber", "")).strip(),
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_list":
        items = data.get("listItems", data.get("items", []))
        if not items:
            raise ValueError("esther_list template requires 'listItems' or 'items' field")
        html = build_esther_list_html(
            title=str(data.get("title", "")).strip() or "清单",
            items=[str(item) for item in items],
            footer=str(data.get("footer", "")).strip(),
            deco_number=str(data.get("decoNumber", "")).strip(),
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_quote":
        html = build_esther_quote_html(
            quote=str(data.get("content", data.get("quote", ""))).strip() or "金句",
            footer=str(data.get("footer", "")).strip(),
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_steps":
        steps = data.get("steps", [])
        if not steps:
            raise ValueError("esther_steps template requires 'steps' field")
        html = build_esther_steps_html(
            title=str(data.get("title", "")).strip() or "操作步骤",
            steps=steps,
            deco_number=str(data.get("decoNumber", "")).strip(),
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_code_panel":
        html = build_esther_code_panel_html(
            title=str(data.get("title", "")).strip() or "核心代码",
            code_content=str(data.get("codeContent", "")).strip(),
            code_lang=str(data.get("codeLang", "code")).strip(),
            deco_number=str(data.get("decoNumber", "")).strip(),
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_numbered_cards":
        items = data.get("numberedItems", data.get("items", []))
        if not items:
            raise ValueError("esther_numbered_cards template requires 'numberedItems' or 'items' field")
        html = build_esther_numbered_cards_html(
            title=str(data.get("title", "")).strip() or "关键要点",
            items=items,
            deco_number=str(data.get("decoNumber", "")).strip(),
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_newspaper":
        columns = data.get("newspaperCols", data.get("columns", []))
        html = build_esther_newspaper_html(
            masthead=str(data.get("masthead", "THE DAILY BRIEF")).strip(),
            columns=columns if columns else None,
            style_name=style_name,
            size=size_name,
        )
    elif template_type == "esther_big_quote":
        html = build_esther_big_quote_html(
            quote=str(data.get("content", data.get("quote", ""))).strip() or "一句足够大的话",
            footer=str(data.get("footer", "")).strip(),
            deco_symbol=str(data.get("decoNumber", '"')).strip(),
            style_name=style_name,
            size=size_name,
        )
    else:
        raise ValueError(
            f"Unknown esther template type: {template_type}. "
            f"Supported: {list(ESTHER_TEMPLATE_BUILDERS.keys())}"
        )

    width, height = _get_size_dimensions(size_name)
    return await render_html_to_base64(html, width, height)