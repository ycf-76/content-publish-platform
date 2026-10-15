"""Per-kind visual variant (Task B) regression.

- Renderer emits `variant-<v>` only when a block's `variant` is non-empty,
  leaving the classic rendering untouched.
- `set_variant` op applies the variant to the right block and rejects unknown ones.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.cards.schema import (
    BentoGrid, CardDeck, CardPage, Cell, Compare, CompareRow, Heading, Item, ListBlock, Stat,
    Steps, Timeline, TimelineItem,
)
from app.cards.renderer import render_page, to_card_draft
from app.cards.operations import CardEdit, apply_card_edit


def _deck_with(variant_map: dict[str, str]) -> CardDeck:
    """Build a deck whose every page carries one of each variant-supporting block."""
    pages = [CardPage(id="page_00", role="cover", layout_id="cover_display",
                     blocks=[Heading(id="h0", text="封面")])]
    # list + steps share the list_ledger / steps_flow layouts.
    pages.append(CardPage(
        id="page_01", role="body", layout_id="list_ledger",
        blocks=[Heading(id="h1", text="清单"),
                ListBlock(id="l1", variant=variant_map.get("list", ""),
                          items=[Item(text="苹果"), Item(text="香蕉")])]))
    pages.append(CardPage(
        id="page_02", role="body", layout_id="steps_flow",
        blocks=[Heading(id="h2", text="步骤"),
                Steps(id="s1", variant=variant_map.get("steps", ""),
                      items=[Item(text="看天气"), Item(text="收拾")])]))
    pages.append(CardPage(
        id="page_03", role="body", layout_id="compare_split",
        blocks=[Heading(id="h3", text="对比"),
                Compare(id="c1", variant=variant_map.get("compare", ""),
                        left_title="旧", right_title="新",
                        rows=[CompareRow(left="慢", right="快"),
                              CompareRow(left="多", right="少")])]))
    pages.append(CardPage(
        id="page_04", role="body", layout_id="bento_grid",
        blocks=[Heading(id="h4", text="矩阵"),
                BentoGrid(id="b1", variant=variant_map.get("bento_grid", ""),
                          cells=[Cell(big="62"), Cell(big="38")])]))
    pages.append(CardPage(
        id="page_05", role="body", layout_id="stat_card",
        blocks=[Heading(id="h5", text="数据"),
                Stat(id="st1", variant=variant_map.get("stat", ""), cell=Cell(big="3.2x"))]))
    pages.append(CardPage(
        id="page_06", role="body", layout_id="timeline_flow",
        blocks=[Heading(id="h6", text="时间线"),
                Timeline(id="t1", variant=variant_map.get("timeline", ""),
                         items=[TimelineItem(date="Q1", text="立项"),
                                TimelineItem(date="Q2", text="上线"),
                                TimelineItem(date="Q3", text="复盘")])]))
    return CardDeck(deck_id="d1", title="变体测试", theme_id="ink", pages=pages)


def _uses_variant(html: str, variant: str) -> bool:
    """A block actually *uses* a variant when its class attribute carries it.

    We match the ` class="… <variant>"` pattern, not the bare substring — the CSS
    stylesheet itself contains `.rows.variant-cards{…}` definitions regardless of use.
    """
    return (" " + variant + '"') in html


def test_renderer_emits_variant_class_only_when_set():
    deck = _deck_with({"list": "cards", "steps": "chips", "compare": "table",
                       "bento_grid": "masonry", "stat": "ring", "timeline": "dots"})
    html = "".join(render_page(deck, p, i) for i, p in enumerate(deck.pages))
    assert _uses_variant(html, "variant-cards")
    assert _uses_variant(html, "variant-chips")
    assert _uses_variant(html, "variant-table")
    assert _uses_variant(html, "variant-masonry")
    assert _uses_variant(html, "variant-ring")
    assert _uses_variant(html, "variant-dots")


def test_renderer_classic_has_no_variant_class():
    deck = _deck_with({})  # all empty -> classic
    html = "".join(render_page(deck, p, i) for i, p in enumerate(deck.pages))
    assert not _uses_variant(html, "variant-cards")
    assert not _uses_variant(html, "variant-table")
    assert 'class="rows"' in html


def test_to_card_draft_exposes_variant_options():
    deck = _deck_with({})
    draft = to_card_draft(deck)
    assert draft["variantOptions"]["list"] == ["", "cards", "tags"]
    assert draft["variantOptions"]["stat"] == ["", "ring", "underline"]


class _FakeArtifact:
    def __init__(self, deck: CardDeck):
        self.card_deck = deck.model_dump()
        self.version = 1
        self.owner_user_id = "u1"
        self.artifact_id = "a1"
        self.source = SimpleNamespace(session_id=None)
        self.storyboard = None


class _NoopLock:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _noop_lock(_artifact_id):
    return _NoopLock()


@pytest.mark.asyncio
async def test_set_variant_applies_and_persists():
    deck = _deck_with({})
    artifact = _FakeArtifact(deck)

    def _load(aid):
        return artifact

    with patch("app.cards.operations.load_artifact", _load), \
         patch("app.cards.operations.save_artifact", lambda a: a), \
         patch("app.cards.operations.artifact_lock", _noop_lock):
        draft = await apply_card_edit("a1", "u1", 1,
                                     CardEdit(page_id="page_01", block_id="l1", op="set_variant", value="tags"))

    pages = draft["deck"]["pages"]
    list_block = next(b for p in pages for b in p["blocks"] if b["type"] == "list")
    assert list_block["variant"] == "tags"


@pytest.mark.asyncio
async def test_set_variant_rejects_unknown_variant():
    deck = _deck_with({})
    artifact = _FakeArtifact(deck)

    with patch("app.cards.operations.load_artifact", lambda aid: artifact), \
         patch("app.cards.operations.save_artifact", lambda a: a), \
         patch("app.cards.operations.artifact_lock", _noop_lock):
        with pytest.raises(ValueError, match="不支持的变体"):
            await apply_card_edit("a1", "u1", 1,
                                 CardEdit(page_id="page_01", block_id="l1", op="set_variant", value="bogus"))


@pytest.mark.asyncio
async def test_set_variant_rejects_non_variant_block():
    deck = _deck_with({})
    # heading is not variant-capable
    deck.pages[0].blocks[0] = Heading(id="h1", text="标题")
    artifact = _FakeArtifact(deck)

    with patch("app.cards.operations.load_artifact", lambda aid: artifact), \
         patch("app.cards.operations.save_artifact", lambda a: a), \
         patch("app.cards.operations.artifact_lock", _noop_lock):
        with pytest.raises(ValueError, match="不支持切换视觉变体"):
            await apply_card_edit("a1", "u1", 1,
                                 CardEdit(page_id="page_01", block_id="h1", op="set_variant", value="cards"))
