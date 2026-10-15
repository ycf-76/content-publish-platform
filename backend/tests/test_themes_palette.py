"""第十一版配色治理：重区分纸色 + 强调色轴（accent axis）的回归锁。

守住五条不变量：
1) 12 套主题 id 全部存在，且 ThemeId 字面量同步覆盖（否则建 Deck 时新 id 被拒）；
2) 旧 THEMES 里写死的 surface/muted/line 已清除，改由 derive_tokens 推导；
3) 每套主题的「强调色板」每个色都满足 bg↔accent ≥ 3.0（UI 对比度下限）；
4) 12 套纸色互不相同（不再出现 5/9 暖米纸色挤在一起的问题）；
5) 强调色轴的 CSS 与运行时映射正确（.accent-i / theme_accent_class / set_accent 入参）。
"""
import pytest

from app.cards.color import contrast
from app.cards.schema import (
    THEMES,
    ThemeId,
    CardDeck,
    CardPage,
    theme_css,
    theme_accent_class,
    _accessible_accents,
)
from app.cards.renderer import to_card_draft
from app.cards.operations import EDIT_OPS


EXPECTED_IDS = [
    "ink", "warm", "swiss", "inkwash", "cream", "terminal",
    "dopamine", "luxe_noir", "journal", "forest", "dune", "botanical",
]


def _minimal_deck(theme_id: str = "swiss") -> CardDeck:
    return CardDeck(deck_id="deck_01", title="x", theme_id=theme_id, pages=[
        CardPage(id="page_01", role="cover", layout_id="cover_display", blocks=[
            {"id": "h1", "type": "heading", "text": "封面"},
            {"id": "t1", "type": "text", "text": "副标题"},
        ]),
        CardPage(id="page_02", role="body", layout_id="content_text", blocks=[
            {"id": "h2", "type": "heading", "text": "说明"},
            {"id": "t2", "type": "text", "text": "一段话"},
        ]),
    ])


def test_all_twelve_theme_ids_present():
    assert set(THEMES) == set(EXPECTED_IDS)
    # ThemeId 字面量必须同步，否则建 Deck 时新 id 会被 Literal 拒掉
    for tid in EXPECTED_IDS:
        assert tid in ThemeId.__args__


def test_no_hardcoded_surface_muted_line():
    for tid, spec in THEMES.items():
        for dead in ("surface", "muted", "line"):
            assert dead not in spec, f"{tid} 仍写死 {dead}，应改用 derive_tokens 推导"


def test_accent_axis_meets_contrast_floor():
    for tid, spec in THEMES.items():
        bg = spec["bg"]
        accents = _accessible_accents(spec)
        assert len(accents) >= 1, f"{tid} 缺少强调色板"
        for acc in accents:
            assert contrast(bg, acc) >= 3.0, f"{tid} 强调色 {acc} 对比度不足 3.0"


def test_paper_colors_distinct():
    bgs = [spec["bg"].lower() for spec in THEMES.values()]
    assert len(set(bgs)) == len(EXPECTED_IDS), "存在重复纸色，强调色轴解决不了纸色单一"


def test_accent_css_emitted_for_multi_accent_theme():
    css = theme_css()
    # swiss 声明了 4 个强调色 → 应发出 .swiss.accent-1/2/3
    assert ".swiss.accent-1{" in css
    assert ".swiss.accent-3{" in css
    # 单强调色主题不应发出 .accent-1
    assert ".luxe_noir.accent-1" not in css


def test_theme_accent_class_mapping():
    assert theme_accent_class("swiss", 0) == ""
    assert theme_accent_class("swiss", 1) == "accent-1"
    assert theme_accent_class("swiss", 3) == "accent-3"
    assert theme_accent_class("swiss", 99) == ""  # 越界回退默认


def test_to_card_draft_exposes_accent_axis():
    draft = to_card_draft(_minimal_deck("swiss"))
    assert draft["accentIndex"] == 0
    assert isinstance(draft["accentOptions"], list) and len(draft["accentOptions"]) == 4
    opt = next(o for o in draft["themeOptions"] if o["id"] == "swiss")
    assert opt["accents"] == draft["accentOptions"]


def test_set_accent_in_edit_ops():
    assert "set_accent" in EDIT_OPS


def test_accent_index_default_backward_compatible():
    # 旧 deck 不传 accent_index 时默认 0，外观不变
    deck = _minimal_deck("ink")
    assert deck.accent_index == 0
    draft = to_card_draft(deck)
    assert "accent-" not in draft["pages"][0]["htmlContent"].split("class=\"card")[1].split("\"")[0]
