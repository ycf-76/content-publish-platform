"""ReAct card vertical slice: semantic plan, owned assets, HTML, and tool contract."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from app.cards.composer import compose_deck
from app.cards.operations import CardEdit, apply_card_edit
from app.cards.schema import CardDeck, CardPage, Compare, Heading, Item, Quote, Timeline
from app.cards.audit import FILL_MIN, audit_page
from app.cards.renderer import render_page
from app.tools.card_compose import ComposeCardDeckSkill


class FakeLLM:
    async def chat(self, **kwargs):
        return {"content": '{"subtitle":"三点速览","sections":['
                '{"kind":"list","title":"准备物品","items":["雨衣","充电宝"]},'
                '{"kind":"steps","title":"出门步骤","items":["看天气","收拾背包"]},'
                '{"kind":"compare","title":"方式对比","left_title":"旧","right_title":"新",'
                '"rows":[["慢","快"],["多","少"]]}],"closing":"收藏清单"}'}


@pytest.mark.asyncio
async def test_distinct_geometry_and_escaped_content():
    draft = await compose_deck(topic="旅行清单<script>alert(1)</script>", content="准备旅行", user_id="u1", llm=FakeLLM())
    deck = CardDeck.model_validate(draft["deck"])
    assert [page.layout_id for page in deck.pages] == [
        "cover_display", "list_ledger", "steps_flow", "compare_split", "end_cta"
    ]
    assert draft["pages"][0]["htmlContent"].count("<script>") == 0
    assert "&lt;script&gt;" in draft["pages"][0]["htmlContent"]
    assert all(page["htmlContent"].startswith("<!doctype html>") for page in draft["pages"])


@pytest.mark.asyncio
async def test_owned_image_layouts():
    asset = {"asset_id": "a1", "original_url": "/uploads/assets/u1/a1.png", "filename": "产品.png"}
    with patch("app.cards.composer.list_assets", new_callable=AsyncMock, return_value=[asset]):
        top = await compose_deck(topic="测试", content="第一条。第二条", user_id="u1", asset_ids=["a1"], llm=FakeLLM())
        side = await compose_deck(topic="测试", content="第一条。第二条", user_id="u1", asset_ids=["a1"], llm=FakeLLM(), image_layout="side")
        overlay = await compose_deck(topic="测试", content="第一条。第二条", user_id="u1", asset_ids=["a1"],
                                     llm=None, image_layout="overlay")
    assert top["deck"]["pages"][0]["layout_id"] == "cover_top_image"
    assert side["deck"]["pages"][1]["layout_id"] == "image_right_ledger"
    assert overlay["deck"]["pages"][1]["layout_id"] == "image_bg_overlay"
    assert "a1.png" in top["pages"][0]["htmlContent"]


@pytest.mark.asyncio
async def test_reject_foreign_asset():
    with patch("app.cards.composer.list_assets", new_callable=AsyncMock, return_value=[]):
        with pytest.raises(ValueError, match="不属于当前用户"):
            await compose_deck(topic="测试", content="内容", user_id="u1", asset_ids=["foreign"])


def test_reject_unapproved_image_url_and_wrong_layout():
    with pytest.raises(ValidationError):
        CardPage.model_validate({"id": "page_01", "role": "cover", "layout_id": "cover_top_image",
                                 "blocks": [{"id": "h", "type": "heading", "text": "标题"},
                                            {"id": "i", "type": "image", "media_id": "x",
                                             "resolved_url": "https://example.com/pixel.png"}]})
    with pytest.raises(ValidationError):
        CardPage.model_validate({"id": "page_01", "role": "cover", "layout_id": "image_right_ledger",
                                 "blocks": [{"id": "h", "type": "heading", "text": "标题"}]})


@pytest.mark.asyncio
async def test_skill_emits_versioned_draft():
    skill = ComposeCardDeckSkill()
    result = await skill.execute({"topic": "旅行", "content": "内容", "llm": FakeLLM(),
                                  "_context": SimpleNamespace(user_id="u1")})
    assert result["card_draft"]["schema_version"] == 1
    assert result["card_draft"]["template"] == "structured_cards"
    assert "deck" in result["card_draft"]


@pytest.mark.asyncio
async def test_card_reads_are_owner_scoped():
    from app.cards.operations import get_owned_artifact

    artifact = SimpleNamespace(
        artifact_id="ca_one",
        owner_user_id="owner-1",
        source=SimpleNamespace(session_id=""),
    )
    with patch("app.cards.operations.load_artifact", return_value=artifact):
        assert await get_owned_artifact("ca_one", "owner-1") is artifact
        with pytest.raises(PermissionError):
            await get_owned_artifact("ca_one", "owner-2")
        with pytest.raises(LookupError):
            await get_owned_artifact("ca_other", "owner-1")


@pytest.mark.asyncio
async def test_update_card_enforces_version_and_compiles_new_html():
    from app.cards.operations import update_card

    initial = await compose_deck(topic="旅行", content="第一句。第二句。", user_id="u1", llm=FakeLLM())
    deck = CardDeck.model_validate(initial["deck"])
    artifact = SimpleNamespace(
        artifact_id="ca_one",
        owner_user_id="u1", source=SimpleNamespace(session_id=""),
        card_deck=deck.model_dump(mode="json"), version=4,
        storyboard=[], brief=SimpleNamespace(template_id=""),
    )
    with patch("app.cards.operations.load_artifact", return_value=artifact), \
         patch("app.cards.operations.save_artifact", side_effect=lambda item: item):
        with pytest.raises(RuntimeError, match="版本已更新"):
            await update_card("ca_one", "u1", 3, deck.pages[0].id, deck.pages[0].blocks[0].id, new_text="新标题")
        result = await update_card(
            "ca_one", "u1", 4, deck.pages[0].id, deck.pages[0].blocks[0].id, new_text="新标题"
        )
    assert result["version"] == 5
    assert "新标题" in result["pages"][0]["htmlContent"]


@pytest.mark.asyncio
async def test_card_edit_route_maps_stale_version_to_conflict():
    from fastapi import HTTPException
    from app.api.routers.creative_artifact import CardEditRequest, patch_card_draft

    payload = CardEditRequest(expected_version=1, page_id="page_1", block_id="heading_1", new_text="x")
    with patch("app.api.routers.creative_artifact.apply_card_edit", new_callable=AsyncMock,
               side_effect=RuntimeError("卡片版本已更新，请刷新后重试")):
        with pytest.raises(HTTPException) as exc:
            await patch_card_draft("ca_one", payload, "u1")
    assert exc.value.status_code == 409


def test_legacy_payload_infers_edit_op():
    from app.api.routers.creative_artifact import CardEditRequest, _to_card_edit

    assert _to_card_edit(CardEditRequest(expected_version=1, page_id="p", block_id="b", new_text="标题")).op == "set_text"
    assert _to_card_edit(CardEditRequest(expected_version=1, page_id="p", block_id="b", new_asset_id="a1")).op == "set_image"
    explicit = _to_card_edit(CardEditRequest(expected_version=1, page_id="p", block_id="b",
                                             op="set_item", index=2, value="第三项"))
    assert (explicit.op, explicit.index, explicit.value) == ("set_item", 2, "第三项")


def _fake_artifact(deck: CardDeck, version: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        artifact_id="ca_one",
        owner_user_id="u1", source=SimpleNamespace(session_id=""),
        card_deck=deck.model_dump(mode="json"), version=version,
        storyboard=[], brief=SimpleNamespace(template_id=""),
    )


async def _apply(deck: CardDeck, edit: CardEdit, version: int = 1, expected: int | None = None) -> dict:
    artifact = _fake_artifact(deck, version)
    with patch("app.cards.operations.load_artifact", return_value=artifact), \
         patch("app.cards.operations.save_artifact", side_effect=lambda item: item):
        return await apply_card_edit("ca_one", "u1", version if expected is None else expected, edit)


def _page_of(result: dict, page_id: str) -> dict:
    return next(page for page in result["deck"]["pages"] if page["id"] == page_id)


def _block_of(result: dict, page_id: str, block_type: str) -> dict:
    return next(b for b in _page_of(result, page_id)["blocks"] if b["type"] == block_type)


def _html_of(result: dict, page_id: str) -> str:
    deck_pages = result["deck"]["pages"]
    position = next(i for i, page in enumerate(deck_pages) if page["id"] == page_id)
    return result["pages"][position]["htmlContent"]


@pytest.mark.asyncio
async def test_item_level_edits_for_list_and_steps():
    deck = CardDeck.model_validate(
        (await compose_deck(topic="旅行", content="第一句。第二句。", user_id="u1", llm=FakeLLM()))["deck"]
    )
    page = next(page for page in deck.pages if page.layout_id == "list_ledger")
    block = next(b for b in page.blocks if b.type == "list")

    edited = await _apply(deck, CardEdit(page_id=page.id, block_id=block.id, op="set_item", index=0, value="雨衣"))
    assert _block_of(edited, page.id, "list")["items"][0]["text"] == "雨衣"

    edited = await _apply(CardDeck.model_validate(edited["deck"]),
                          CardEdit(page_id=page.id, block_id=block.id, op="add_item", value="充电宝"))
    assert _block_of(edited, page.id, "list")["items"][-1]["text"] == "充电宝"

    grown = CardDeck.model_validate(edited["deck"])
    size = len(_block_of(edited, page.id, "list")["items"])
    edited = await _apply(grown, CardEdit(page_id=page.id, block_id=block.id, op="remove_item", index=0))
    assert len(_block_of(edited, page.id, "list")["items"]) == size - 1
    assert "雨衣" not in _html_of(edited, page.id)

    with pytest.raises(ValueError, match="位置不存在"):
        await _apply(deck, CardEdit(page_id=page.id, block_id=block.id, op="set_item", index=9, value="越界"))
    with pytest.raises(ValueError, match="内容不能为空"):
        await _apply(deck, CardEdit(page_id=page.id, block_id=block.id, op="set_item", index=0, value="   "))


@pytest.mark.asyncio
async def test_compare_cells_rows_and_titles_are_editable():
    deck = CardDeck.model_validate(
        (await compose_deck(topic="旅行", content="第一句。第二句。", user_id="u1", llm=FakeLLM()))["deck"]
    )
    page = next(page for page in deck.pages if page.layout_id == "compare_split")
    block = next(b for b in page.blocks if b.type == "compare")

    edited = await _apply(deck, CardEdit(page_id=page.id, block_id=block.id,
                                         op="set_cell", index=0, column="left", value="更快"))
    assert _block_of(edited, page.id, "compare")["rows"][0]["left"] == "更快"
    assert "更快" in _html_of(edited, page.id)

    edited = await _apply(CardDeck.model_validate(edited["deck"]),
                          CardEdit(page_id=page.id, block_id=block.id, op="add_row", value_pair=["便宜", "省心"]))
    assert _block_of(edited, page.id, "compare")["rows"][-1]["left"] == "便宜"

    edited = await _apply(CardDeck.model_validate(edited["deck"]),
                          CardEdit(page_id=page.id, block_id=block.id, op="set_title", column="right", value="新方式"))
    assert _block_of(edited, page.id, "compare")["right_title"] == "新方式"

    shrunk = CardDeck.model_validate(edited["deck"])
    rows = len(_block_of(edited, page.id, "compare")["rows"])
    edited = await _apply(shrunk, CardEdit(page_id=page.id, block_id=block.id, op="remove_row", index=0))
    assert len(_block_of(edited, page.id, "compare")["rows"]) == rows - 1

    with pytest.raises(ValueError, match="必须指定左列或右列"):
        await _apply(deck, CardEdit(page_id=page.id, block_id=block.id, op="set_cell", index=0, value="缺列"))


@pytest.mark.asyncio
async def test_items_carry_a_note_and_a_right_hand_tag():
    """条目从「一个字符串」升级成「主行 + 副行 + 右侧标签」。

    这是密度的杠杆：填满同一块画幅，单行需要 6 条光秃短语，带副行只要 4 条
    「是什么 + 为什么」，而模型本来就愿意写带说明的要点。
    副行与标签必须能单独改、单独清空，且不能因为只改副行就把主行弄丢。
    """
    deck = CardDeck.model_validate(
        (await compose_deck(topic="旅行", content="第一句。第二句。", user_id="u1", llm=FakeLLM()))["deck"]
    )
    page = next(page for page in deck.pages if page.layout_id == "list_ledger")
    block = next(b for b in page.blocks if b.type == "list")
    original = block.items[0].text

    edited = await _apply(deck, CardEdit(page_id=page.id, block_id=block.id, op="set_item",
                                         index=0, note="主行下面的灰色小字"))
    item = _block_of(edited, page.id, "list")["items"][0]
    assert item["text"] == original, "只改副行时主行必须保留"
    assert item["note"] == "主行下面的灰色小字"

    edited = await _apply(CardDeck.model_validate(edited["deck"]),
                          CardEdit(page_id=page.id, block_id=block.id, op="set_item", index=0, tag="必带"))
    item = _block_of(edited, page.id, "list")["items"][0]
    assert item["tag"] == "必带"
    assert item["note"] == "主行下面的灰色小字", "只改标签时副行必须保留"

    html = _html_of(edited, page.id)
    assert 'class="note"' in html and "主行下面的灰色小字" in html
    assert 'class="tag"' in html and "必带" in html

    # 可选字段允许留空（清空副行），这与主行不同——主行空了条目就没有意义。
    edited = await _apply(CardDeck.model_validate(edited["deck"]),
                          CardEdit(page_id=page.id, block_id=block.id, op="set_item", index=0, note=""))
    assert _block_of(edited, page.id, "list")["items"][0]["note"] == ""
    assert 'class="note"' not in _html_of(edited, page.id)

    # 新增条目时副行与标签要能一次带上。
    grown = CardDeck.model_validate(edited["deck"])
    edited = await _apply(grown, CardEdit(page_id=page.id, block_id=block.id, op="add_item",
                                          value="护照", note="有效期要超过半年", tag="证件"))
    assert _block_of(edited, page.id, "list")["items"][-1] == {
        "text": "护照", "note": "有效期要超过半年", "tag": "证件"}


@pytest.mark.asyncio
async def test_compare_rows_can_carry_a_dimension_label():
    """对比行多的那个 label 回答「这一行到底在比什么」。

    没有它时，两栏里散着「慢 / 快」这种孤立词，读者得自己猜维度；
    有了它，对比表从「两列词」变成「一张有表头的表」。
    """
    deck = CardDeck.model_validate(
        (await compose_deck(topic="旅行", content="第一句。第二句。", user_id="u1", llm=FakeLLM()))["deck"]
    )
    page = next(page for page in deck.pages if page.layout_id == "compare_split")
    block = next(b for b in page.blocks if b.type == "compare")

    edited = await _apply(deck, CardEdit(page_id=page.id, block_id=block.id, op="add_row",
                                         value="价格", value_pair=["贵", "便宜"]))
    rows = _block_of(edited, page.id, "compare")["rows"]
    assert rows[-1]["label"] == "价格"
    assert (rows[-1]["left"], rows[-1]["right"]) == ("贵", "便宜")

    html = _html_of(edited, page.id)
    assert 'compare labeled' in html, "有维度标签时必须切到三列网格"
    assert 'class="rowlabel"' in html and "价格" in html


def test_legacy_plain_string_items_and_two_tuples_still_load():
    """历史 Deck 里条目是裸字符串、对比行是二元组——升级后必须原样读出来。

    artifact 里存的是 deck dict，没有迁移脚本，所以归一化只能写在模型里。
    """
    deck = CardDeck.model_validate({
        "deck_id": "legacy", "title": "旧卡片", "pages": [{
            "id": "page_one", "role": "cover", "layout_id": "list_ledger", "blocks": [
                {"id": "head_one", "type": "heading", "text": "标题"},
                {"id": "list_one", "type": "list", "items": ["雨衣", "充电宝"]},
            ],
        }],
    })
    blocks = {block.id: block for block in deck.pages[0].blocks}
    assert [item.text for item in blocks["list_one"].items] == ["雨衣", "充电宝"]
    assert blocks["list_one"].items[0].note == "" and blocks["list_one"].items[0].tag == ""

    compare = Compare.model_validate({"id": "c", "left_title": "旧", "right_title": "新",
                                      "rows": [["慢", "快"], ["维度", "多", "少"]]})
    assert (compare.rows[0].left, compare.rows[0].right) == ("慢", "快")
    assert compare.rows[0].label == ""
    assert (compare.rows[1].label, compare.rows[1].left, compare.rows[1].right) == ("维度", "多", "少")

    with pytest.raises(ValidationError):
        Item.model_validate("")


@pytest.mark.asyncio
async def test_bento_grid_renders_six_cells_with_full_data_layers():
    """矩阵 Bento 是 Easel 9 骨架里我们之前缺失的「D 矩阵」。

    每格必须把「kicker / big / unit / note / source」五层都填上——
    只给一个数字看起来像孤立大数字，密度审计照样 FAIL。
    """
    cells = [
        {"kicker": "盈利能力", "big": "73", "unit": "%", "note": "同比去年提升 12 个百分点", "source": "公司年报 2024"},
        {"kicker": "用户规模", "big": "1.2", "unit": "亿", "note": "覆盖一二三线城市", "source": "QuestMobile"},
        {"kicker": "复购率", "big": "45", "unit": "%", "note": "高于同行 18%", "source": "艾瑞咨询"},
        {"kicker": "研发占比", "x": "18", "unit": "%", "note": "持续高于行业均值", "source": "招股书"},
        {"kicker": "客单价", "big": "288", "unit": "元", "note": "高端线带动", "source": "财报披露"},
        {"kicker": "NPS", "big": "62", "unit": "分", "note": "推荐意愿行业领先", "source": "第三方调研"},
    ]
    deck = CardDeck.model_validate({
        "deck_id": "bento", "title": "关键指标", "kicker": "数据看板",
        "pages": [
            {"id": "page_cover", "role": "cover", "layout_id": "cover_display",
             "blocks": [{"id": "h1", "type": "heading", "text": "关键指标"}]},
            {"id": "page_bento", "role": "body", "layout_id": "bento_grid", "blocks": [
                {"id": "h2", "type": "heading", "text": "六个核心数据"},
                {"id": "b2", "type": "bento_grid", "cells": cells},
            ]},
        ],
    })
    report = audit_page(deck, deck.pages[1])
    assert report["fill"] >= FILL_MIN, f"6 格满矩阵也欠填：{report}"
    html = render_page(deck, deck.pages[1], 1)
    assert html.count('class="cell"') == 6, "矩阵必须输出 6 个格子"
    assert 'class="kicker"' in html and "盈利能力" in html
    assert 'class="big"' in html and "1.2" in html
    assert 'class="unit"' in html and "亿" in html
    assert 'class="note"' in html and "同比去年提升" in html
    assert 'class="source"' in html and "公司年报" in html


@pytest.mark.asyncio
async def test_stat_card_renders_giant_number_with_all_five_layers():
    """单数据卡：所有视觉重量集中在一个巨数上，五层信息承载是关键。

    没有 note/source 的「200%」只是孤立大数字——这是 Easel 反复强调的设计系统约束。
    """
    deck = CardDeck.model_validate({
        "deck_id": "stat", "title": "数据卡",
        "pages": [
            {"id": "page_cover", "role": "cover", "layout_id": "cover_display",
             "blocks": [{"id": "h1", "type": "heading", "text": "数据卡"}]},
            {"id": "page_stat", "role": "body", "layout_id": "stat_card", "blocks": [
                {"id": "h2", "type": "heading", "text": "同比增长"},
                {"id": "s2", "type": "stat",
                 "cell": {"kicker": "增长", "big": "200", "unit": "%",
                          "note": "对比去年同期，付费转化率提升了一倍。",
                          "source": "Q4 财报"}},
            ]},
        ],
    })
    report = audit_page(deck, deck.pages[1])
    assert report["fill"] >= FILL_MIN, f"5 层满的 stat 也欠填：{report}"
    html = render_page(deck, deck.pages[1], 1)
    assert 'class="stat"' in html
    assert 'class="big"' in html and ">200<" in html
    assert 'class="kicker"' in html and "增长" in html
    assert 'class="unit"' in html and "％" not in html  # 中文全角 % 不应用上（CSS 用半角）
    assert "Q4 财报" in html


@pytest.mark.asyncio
async def test_bento_grid_density_minimum_is_four_cells():
    """少于 4 格的矩阵过不了最小密度线，必须提示扩格或换骨架。"""
    deck = CardDeck.model_validate({
        "deck_id": "thin", "title": "稀疏矩阵",
        "pages": [
            {"id": "page_x0", "role": "cover", "layout_id": "cover_display",
             "blocks": [{"id": "h_x0", "type": "heading", "text": "稀疏矩阵"}]},
            {"id": "page_x", "role": "body", "layout_id": "bento_grid", "blocks": [
                {"id": "h_x", "type": "heading", "text": "只有两格"},
                {"id": "b_x", "type": "bento_grid", "cells": [
                    {"kicker": "A", "big": "1", "unit": "%", "note": "描述足够长避免审计误判", "source": "源"},
                    {"kicker": "B", "big": "2", "unit": "%", "note": "描述足够长避免审计误判", "source": "源"},
                ]},
            ]},
        ],
    })
    report = audit_page(deck, deck.pages[1])
    assert any("格子" in problem for problem in report["problems"]), report


@pytest.mark.asyncio
async def test_bento_and_stat_cell_edits_merge_partial_fields():
    """set_bento_cell / set_stat_value 任一字段给就改、不给保留——这是 P0 已确立的合并语义。

    与 Item/CompareRow 一致：所有 Cell 字段都是可选修改字段。
    """
    deck = CardDeck.model_validate({
        "deck_id": "edit", "title": "编辑",
        "pages": [
            {"id": "page_e0", "role": "cover", "layout_id": "cover_display",
             "blocks": [{"id": "h_e0", "type": "heading", "text": "编辑"}]},
            {"id": "page_e", "role": "body", "layout_id": "bento_grid", "blocks": [
                {"id": "h_e", "type": "heading", "text": "标题"},
                {"id": "b_e", "type": "bento_grid", "cells": [
                    {"kicker": "原 K", "big": "10", "unit": "原 U", "note": "原 N", "source": "原 S"},
                    {"kicker": "次 K", "big": "20", "unit": "次 U", "note": "次 N", "source": "次 S"},
                ]},
            ]},
        ],
    })

    # 只改 big：kicker/note/source 必须保留。
    page = deck.pages[1]
    block = next(b for b in page.blocks if b.type == "bento_grid")
    edited = await _apply(deck, CardEdit(page_id=page.id, block_id=block.id,
                                         op="set_bento_cell", index=0, value="99"))
    cell = _block_of(edited, page.id, "bento_grid")["cells"][0]
    assert cell["big"] == "99"
    assert cell["kicker"] == "原 K" and cell["note"] == "原 N" and cell["source"] == "原 S"

    # 同时改三字段：unit 与 source 走独立字段，不走 value/note。
    grown = CardDeck.model_validate(edited["deck"])
    edited = await _apply(grown, CardEdit(page_id=page.id, block_id=block.id,
                                          op="set_bento_cell", index=0,
                                          unit="新 U", note="新 N", source="新 S"))
    cell = _block_of(edited, page.id, "bento_grid")["cells"][0]
    assert cell["unit"] == "新 U" and cell["note"] == "新 N" and cell["source"] == "新 S"

    # 跨类型：tag 不是矩阵语法，必须明确报错。
    with pytest.raises(ValueError, match="kicker"):
        await _apply(grown, CardEdit(page_id=page.id, block_id=block.id,
                                     op="set_bento_cell", index=0, tag="BAD"))

    # stat 单卡同样支持五层字段合并编辑。
    stat_deck = CardDeck.model_validate({
        "deck_id": "stat_edit", "title": "t",
        "pages": [
            {"id": "page_s0", "role": "cover", "layout_id": "cover_display",
             "blocks": [{"id": "h_s0", "type": "heading", "text": "t"}]},
            {"id": "page_s", "role": "body", "layout_id": "stat_card", "blocks": [
                {"id": "h_s", "type": "heading", "text": "t"},
                {"id": "s_s", "type": "stat",
                 "cell": {"kicker": "K", "big": "10", "unit": "U", "note": "N", "source": "S"}},
            ]},
        ],
    })
    page = stat_deck.pages[1]
    block = next(b for b in page.blocks if b.type == "stat")
    edited = await _apply(stat_deck, CardEdit(page_id=page.id, block_id=block.id,
                                              op="set_stat_value", value="999"))
    assert _block_of(edited, page.id, "stat")["cell"]["big"] == "999"


@pytest.mark.asyncio
async def test_layout_switch_only_accepts_compatible_targets():
    from app.cards.operations import CardEdit, apply_card_edit
    from app.cards.schema import compatible_layouts

    deck = CardDeck.model_validate(
        (await compose_deck(topic="旅行", content="第一句。第二句。", user_id="u1", llm=FakeLLM()))["deck"]
    )
    page = next(page for page in deck.pages if page.layout_id == "list_ledger")

    assert "steps_flow" in compatible_layouts(page)
    assert "compare_split" not in compatible_layouts(page)

    before = _html_of((await _apply(deck, CardEdit(page_id=page.id, op="set_layout", value="list_ledger"))), page.id)
    edited = await _apply(deck, CardEdit(page_id=page.id, op="set_layout", value="steps_flow"))
    assert _page_of(edited, page.id)["layout_id"] == "steps_flow"
    assert _html_of(edited, page.id) != before

    with pytest.raises(ValueError, match="无法切换"):
        await _apply(deck, CardEdit(page_id=page.id, op="set_layout", value="compare_split"))
    with pytest.raises(ValueError, match="未知版式"):
        await _apply(deck, CardEdit(page_id=page.id, op="set_layout", value="not_a_layout"))


@pytest.mark.asyncio
async def test_theme_switch_recompiles_every_page():
    deck = CardDeck.model_validate(
        (await compose_deck(topic="旅行", content="第一句。第二句。", user_id="u1", llm=FakeLLM()))["deck"]
    )
    edited = await _apply(deck, CardEdit(page_id=deck.pages[0].id, op="set_theme", value="warm"))
    assert edited["deck"]["theme_id"] == "warm"
    assert all('class="card warm' in page["htmlContent"] for page in edited["pages"])

    with pytest.raises(ValueError, match="未知主题"):
        await _apply(deck, CardEdit(page_id=deck.pages[0].id, op="set_theme", value="neon"))


@pytest.mark.asyncio
async def test_direction_switch_regeometries_the_whole_deck():
    from app.cards.schema import available_directions

    deck = CardDeck.model_validate(
        (await compose_deck(topic="旅行", content="第一句。第二句。", user_id="u1", llm=FakeLLM()))["deck"]
    )
    options = available_directions(deck)
    assert "ledger" in options and "flow" in options
    # editorial（文字优先）不出现：欠填修正已把纯文字页升级成清单页，
    # 而文字页正是中段死空白的来源，不该再切回去。
    assert "editorial" not in options
    # 没有任何图片素材时，"图像主导"撑不起来，不应出现在候选里
    assert "visual" not in options

    before = [page.layout_id for page in deck.pages]
    edited = await _apply(deck, CardEdit(page_id=deck.pages[0].id, op="set_direction", value="flow"))
    after = [page["layout_id"] for page in edited["deck"]["pages"]]
    assert after != before
    assert "steps_flow" in after

    settled = CardDeck.model_validate(edited["deck"])
    assert "flow" not in available_directions(settled)
    assert "ledger" in available_directions(settled)

    with pytest.raises(ValueError, match="未知方向"):
        await _apply(settled, CardEdit(page_id=settled.pages[0].id, op="set_direction", value="nope"))
    with pytest.raises(ValueError, match="无需切换"):
        await _apply(settled, CardEdit(page_id=settled.pages[0].id, op="set_direction", value="flow"))


@pytest.mark.asyncio
async def test_editorial_direction_needs_a_text_page():
    """editorial 依赖纯文字页；清单页切不出它，这正是欠填修正想要的结果。"""
    from app.cards.schema import CardPage, available_directions

    # 封面挂了「本期导读」后，就退不回纯文字封面，editorial 因此不可用。
    deck = CardDeck(deck_id="deck_editorial", title="纯文字卡", pages=[
        CardPage(id="page_01", role="cover", layout_id="cover_display", blocks=[
            {"id": "h1", "type": "heading", "text": "封面"},
            {"id": "t1", "type": "text", "text": "副标题"},
            {"id": "l1", "type": "list", "items": ["导读一", "导读二", "导读三"]},
        ]),
        CardPage(id="page_02", role="body", layout_id="list_ledger", blocks=[
            {"id": "h2", "type": "heading", "text": "清单"},
            {"id": "l2", "type": "list", "items": ["一", "二", "三", "四", "五"]},
        ]),
    ])
    assert "editorial" not in available_directions(deck)

    text_deck = CardDeck(deck_id="deck_text", title="文字卡", pages=[
        CardPage(id="page_01", role="cover", layout_id="cover_display", blocks=[
            {"id": "h1", "type": "heading", "text": "封面"},
            {"id": "t1", "type": "text", "text": "副标题"},
        ]),
        CardPage(id="page_02", role="body", layout_id="content_text", blocks=[
            {"id": "h2", "type": "heading", "text": "说明"},
            {"id": "t2", "type": "text", "text": "一段话"},
        ]),
        CardPage(id="page_03", role="ending", layout_id="end_cta", blocks=[
            {"id": "h3", "type": "heading", "text": "收尾"},
            {"id": "c3", "type": "cta", "text": "收藏备用"},
        ]),
    ])
    assert "editorial" in available_directions(text_deck)


@pytest.mark.asyncio
async def test_visual_direction_appears_once_images_exist():
    from app.cards.schema import available_directions

    asset = {"asset_id": "a1", "original_url": "/uploads/assets/u1/a1.png", "filename": "产品.png"}
    with patch("app.cards.composer.list_assets", new_callable=AsyncMock, return_value=[asset]), \
         patch("app.cards.operations.list_assets", new_callable=AsyncMock, return_value=[asset]):
        draft = await compose_deck(topic="测试", content="第一条。第二条", user_id="u1",
                                   asset_ids=["a1"], llm=FakeLLM())
        deck = CardDeck.model_validate(draft["deck"])
        assert any(page.layout_id in ("cover_top_image", "image_right_ledger") for page in deck.pages)
        assert "visual" in available_directions(deck)

        edited = await _apply(deck, CardEdit(page_id=deck.pages[0].id, op="set_direction", value="visual"))
    assert edited["deck"]["pages"][0]["layout_id"] == "image_bg_overlay"


@pytest.mark.asyncio
async def test_direction_never_picks_an_incompatible_layout():
    from app.cards.schema import DIRECTIONS, available_directions, compatible_layouts

    deck = CardDeck.model_validate(
        (await compose_deck(topic="旅行", content="第一句。第二句。", user_id="u1", llm=FakeLLM()))["deck"]
    )
    for direction in available_directions(deck):
        probe = deck.model_copy(deep=True)
        from app.cards.schema import apply_direction
        assert apply_direction(probe, direction)
        for page in probe.pages:
            assert page.layout_id in compatible_layouts(page)


@pytest.mark.asyncio
async def test_new_ops_still_enforce_version_and_block_kinds():
    deck = CardDeck.model_validate(
        (await compose_deck(topic="旅行", content="第一句。第二句。", user_id="u1", llm=FakeLLM()))["deck"]
    )
    page = next(page for page in deck.pages if page.layout_id == "compare_split")
    block = next(b for b in page.blocks if b.type == "compare")

    with pytest.raises(RuntimeError, match="版本已更新"):
        await _apply(deck, CardEdit(page_id=page.id, block_id=block.id, op="add_row",
                                    value_pair=["a", "b"]), version=4, expected=1)
    with pytest.raises(ValueError, match="没有可编辑的条目"):
        await _apply(deck, CardEdit(page_id=page.id, block_id=block.id, op="add_item", value="x"))
    with pytest.raises(ValueError, match="组件不存在"):
        await _apply(deck, CardEdit(page_id=page.id, block_id="nope", op="set_text", value="x"))


def test_edit_ops_match_the_declared_literal():
    from typing import get_args
    from app.cards.operations import EDIT_OPS, CardEdit

    assert set(get_args(CardEdit.model_fields["op"].annotation)) == set(EDIT_OPS)


@pytest.mark.asyncio
async def test_react_artifact_persistence_keeps_authenticated_owner():
    from app.engine.harness.executor.loop import LoopExecutor

    draft = await compose_deck(topic="旅行", content="第一条。第二条。", user_id="u1", llm=FakeLLM())
    executor = LoopExecutor.__new__(LoopExecutor)
    saved = []
    with patch("app.services.creative_artifact.save_artifact", side_effect=lambda artifact: saved.append(artifact)):
        artifact_id = await executor._persist_artifact_to_disk(
            "session-1", "compose_card_deck", {"topic": "旅行"}, draft, user_id="u1"
        )
    assert artifact_id
    assert saved[0].owner_user_id == "u1"
    assert saved[0].source.session_id == "session-1"
    assert saved[0].card_deck is not None



THIN_PLAN = (
    '{"subtitle":"副标题","sections":['
    '{"kind":"text","title":"为什么总记混","text":"两个词词根完全不同。"},'
    '{"kind":"list","title":"词根家族","items":["constant 持续的","stance 立场","status 状态"]},'
    '{"kind":"compare","title":"易混淆对比","left_title":"旧","right_title":"新",'
    '"rows":[["慢","快"],["多","少"]]}],"closing":"收藏"}'
)

RICH_PLAN = (
    '{"subtitle":"副标题","sections":['
    '{"kind":"text","title":"为什么总记混","text":"两个词词根完全不同：一个来自 test(见证)，'
    '另一个来自 st(站立)。记住词根就不会再混，这是最省力的一条路径。"},'
    '{"kind":"list","title":"词根家族","items":["constant 一直站着的→持续的",'
    '"stance 站立的位置→立场","status 站的样子→状态","stable 能站稳的→稳定的",'
    '"obstacle 站在对面→障碍","establish 使站立→建立"]},'
    '{"kind":"compare","title":"易混淆对比","left_title":"旧","right_title":"新",'
    '"rows":[["慢","快"],["多","少"],["被动","主动"],["模糊","清晰"],["一次性","可复用"]]}],'
    '"closing":"收藏"}'
)


class ScriptedLLM:
    """第一轮给一份欠填的规划，第二轮按审计缺口补饱满。"""

    def __init__(self, second: str = RICH_PLAN) -> None:
        self.calls = 0
        self.second = second

    async def chat(self, **kwargs):
        self.calls += 1
        return {"content": THIN_PLAN if self.calls == 1 else self.second}


async def _min_fill(llm) -> float:
    from app.cards.audit import deck_density

    draft = await compose_deck(topic="词根笔记", content="contest 和 contrast 总是记混。",
                               user_id="u1", llm=llm)
    return deck_density(CardDeck.model_validate(draft["deck"]))["min_fill"]


@pytest.mark.asyncio
async def test_density_audit_feedback_expands_thin_sections():
    """欠填页应触发一次补内容，且补完必须真的更密——对照组是不补的那次。

    这是欠填修正阶梯的最后一阶：换骨架、挂目录都是确定性的、不新增内容；
    只有当它们仍撑不满时，才把「第几节、缺多少」回灌给模型。
    """
    llm = ScriptedLLM()
    repaired = await _min_fill(llm)
    assert llm.calls > 1, "存在欠填页却没有触发补内容"

    control = await _min_fill(ScriptedLLM(second=THIN_PLAN))
    assert repaired > control, f"补内容后反而没变密：{repaired} <= {control}"


@pytest.mark.asyncio
async def test_timeline_renders_anchored_entries_and_fills():
    """时间线：左侧 mono 时间戳 + 右侧标题/说明，每一条都带 date + text + note。

    与 steps_flow 的区别是「按时间排序」而非「按流程顺序」，纵向更强调日期排列。
    flex:1 的 ul 把 3-8 条均匀铺满画幅，所以满 3 条即过密度审计。
    """
    deck = CardDeck.model_validate({
        "deck_id": "tl", "title": "演化史",
        "pages": [
            {"id": "page_cover", "role": "cover", "layout_id": "cover_display",
             "blocks": [{"id": "h1", "type": "heading", "text": "演化史"}]},
            {"id": "page_tl", "role": "body", "layout_id": "timeline_flow", "blocks": [
                {"id": "h2", "type": "heading", "text": "我的产品演化史"},
                {"id": "tl2", "type": "timeline", "items": [
                    {"date": "2021 Q1", "text": "第一个原型", "note": "脚本拼的静态页"},
                    {"date": "2022 Q3", "text": "结构化卡片上线", "note": "Deck 单一事实源"},
                    {"date": "2024 Q1", "text": "多智能体改写", "note": "ReAct 链路接管排版"},
                    {"date": "2025 Q2", "text": "呼吸型骨架补齐", "note": "金句与时间线卡型落地"},
                ]},
            ]},
        ],
    })
    report = audit_page(deck, deck.pages[1])
    assert report["pass"], report
    html = render_page(deck, deck.pages[1], 1)
    assert 'class="timeline"' in html
    assert "2021 Q1" in html and "第一个原型" in html and "脚本拼的静态页" in html
    assert html.count("<li>") == 4


@pytest.mark.asyncio
async def test_quote_renders_breathing_skeleton_with_three_anchors():
    """金句卡是 Easel 9 骨架里唯一允许较空的呼吸型骨架。

    必须补三锚点：顶 kicker / 底 author + 上下发丝线，否则空白读作「缺内容」。
    金句页的 LAYOUTS 只有 quote、不含 heading，标题由块内 kicker 承担。
    """
    deck = CardDeck.model_validate({
        "deck_id": "q", "title": "复盘",
        "pages": [
            {"id": "page_x0", "role": "cover", "layout_id": "cover_display",
             "blocks": [{"id": "h_x0", "type": "heading", "text": "复盘"}]},
            {"id": "page_q", "role": "body", "layout_id": "quote_callout", "blocks": [
                {"id": "q2", "type": "quote",
                 "text": "真正缺的不是版式数量，而是块的数据模型——把语义结构立住，画面才填得满。",
                 "author": "ENG TEAM", "kicker": "LESSON 03"},
            ]},
        ],
    })
    report = audit_page(deck, deck.pages[1])
    assert report["pass"], report
    html = render_page(deck, deck.pages[1], 1)
    assert 'class="quote"' in html
    assert "LESSON 03" in html and "ENG TEAM" in html and "真正缺的不是版式" in html
    # 金句页没有外部 heading，渲染出的 kicker 来自块内、不是页面级 kicker。
    assert 'class="kicker"' in html


def test_timeline_needs_at_least_three_anchors_and_quote_needs_text():
    """时间线最少 3 条锚点；金句正文不能为空——两者都在 schema 层就拦下。"""
    with pytest.raises(ValidationError):
        CardDeck.model_validate({"deck_id": "t", "title": "x", "pages": [
            {"id": "page_cover", "role": "cover", "layout_id": "cover_display",
             "blocks": [{"id": "h1", "type": "heading", "text": "x"}]},
            {"id": "page_tl", "role": "body", "layout_id": "timeline_flow", "blocks": [
                {"id": "h2", "type": "heading", "text": "x"},
                {"id": "tl", "type": "timeline", "items": [
                    {"date": "2021", "text": "a"}, {"date": "2022", "text": "b"}]},
            ]},
        ]})
    with pytest.raises(ValidationError):
        CardDeck.model_validate({"deck_id": "q", "title": "x", "pages": [
            {"id": "page_x0", "role": "cover", "layout_id": "cover_display",
             "blocks": [{"id": "h1", "type": "heading", "text": "x"}]},
            {"id": "page_q", "role": "body", "layout_id": "quote_callout", "blocks": [
                {"id": "q", "type": "quote", "text": ""}]},
        ]})


@pytest.mark.asyncio
async def test_timeline_and_quote_edits_merge_partial_fields():
    """set_timeline_item / add_timeline_item / remove_timeline_item / set_quote 复用既有字段语义。

    timeline 复用 value(日期)/note(标题)/tag(说明)；quote 复用 value(正文)/note(作者)/tag(日期)。
    任一字段给就改、不给保留——与 Item/CompareRow/Cell 的合并语义一致。
    """
    deck = CardDeck.model_validate({
        "deck_id": "edit2", "title": "t",
        "pages": [
            {"id": "page_e0", "role": "cover", "layout_id": "cover_display",
             "blocks": [{"id": "h_e0", "type": "heading", "text": "t"}]},
            {"id": "page_tl", "role": "body", "layout_id": "timeline_flow", "blocks": [
                {"id": "h_e", "type": "heading", "text": "t"},
                {"id": "tl_e", "type": "timeline", "items": [
                    {"date": "2021", "text": "原型", "note": "旧说明"},
                    {"date": "2022", "text": "结构化", "note": "n2"},
                    {"date": "2023", "text": "智能体", "note": "n3"}]},
            ]},
        ],
    })
    page = deck.pages[1]
    block = next(b for b in page.blocks if b.type == "timeline")
    # 只改时间线条目的 text（note 字段）应保留 date。
    edited = await _apply(deck, CardEdit(page_id=page.id, block_id=block.id,
                                         op="set_timeline_item", index=0, note="第一个可用版本"))
    items = _block_of(edited, page.id, "timeline")["items"]
    assert items[0]["date"] == "2021", "只改时间线条目的 text 时 date 必须保留"
    assert items[0]["text"] == "第一个可用版本"

    # 8 条为上限、3 条为下限。
    full = CardDeck.model_validate({
        "deck_id": "full", "title": "t",
        "pages": [{"id": "page_cover", "role": "cover", "layout_id": "cover_display",
                   "blocks": [{"id": "h1", "type": "heading", "text": "t"}]},
                  {"id": "page_tl", "role": "body", "layout_id": "timeline_flow", "blocks": [
                      {"id": "h2", "type": "heading", "text": "t"},
                      {"id": "tl_f", "type": "timeline", "items": [
                          {"date": f"D{i}", "text": f"t{i}"} for i in range(8)]},
                  ]}]},
    )
    fpage = full.pages[1]
    fblock = next(b for b in fpage.blocks if b.type == "timeline")
    with pytest.raises(ValueError, match="最多只能有 8"):
        await _apply(full, CardEdit(page_id=fpage.id, block_id=fblock.id,
                                    op="add_timeline_item", value="D9", note="t9", tag="n9"))
    with pytest.raises(ValueError, match="至少保留 3"):
        await _apply(deck, CardEdit(page_id=page.id, block_id=block.id,
                                    op="remove_timeline_item", index=0))

    # set_quote：value(正文)/note(作者)/tag(日期) 合并编辑。
    qdeck = CardDeck.model_validate({
        "deck_id": "qed", "title": "t",
        "pages": [{"id": "page_x0", "role": "cover", "layout_id": "cover_display",
                   "blocks": [{"id": "h_x0", "type": "heading", "text": "t"}]},
                  {"id": "page_q", "role": "body", "layout_id": "quote_callout", "blocks": [
                      {"id": "q_e", "type": "quote", "text": "原句", "author": "A", "kicker": "K"}]},
                  ]},
    )
    qpage = qdeck.pages[1]
    qblock = next(b for b in qpage.blocks if b.type == "quote")
    qedited = await _apply(qdeck, CardEdit(page_id=qpage.id, block_id=qblock.id,
                                           op="set_quote", value="新金句", note="新作者", tag="新日期"))
    q = _block_of(qedited, qpage.id, "quote")
    assert q["text"] == "新金句" and q["author"] == "新作者" and q["kicker"] == "新日期"


@pytest.mark.asyncio
async def test_composer_builds_timeline_and_quote_sections_from_plan():
    """planner 的 timeline / quote section 必须落到正确版式，且金句页不能漏出 Heading。

    这是 P2 两个集成 bug 的回归锁：composer 给每个 section 先 prepend Heading，
    进 quote 分支时必须清掉，否则 validate_layout 会报"含有不允许的组件"。
    """
    class PlanLLM:
        async def chat(self, **kwargs):
            return {"content": '{"subtitle":"复盘","sections":['
                    '{"kind":"timeline","title":"演化史","timeline_items":['
                    '{"date":"2021 Q1","text":"原型","note":"脚本拼的"},'
                    '{"date":"2022 Q3","text":"结构化","note":"Deck 事实源"},'
                    '{"date":"2024 Q1","text":"多智能体","note":"ReAct 接管"}]},'
                    '{"kind":"quote","title":"心得","quote_text":"真正缺的不是版式数量，而是块的数据模型。",'
                    '"quote_author":"ENG TEAM","quote_kicker":"LESSON 03"}],"closing":"收藏"}'}

    draft = await compose_deck(topic="产品演化史", content="内容", user_id="u1", llm=PlanLLM())
    deck = CardDeck.model_validate(draft["deck"])
    layouts = [page.layout_id for page in deck.pages]
    assert layouts == ["cover_display", "timeline_flow", "quote_callout", "end_cta"], layouts

    tl_page = next(p for p in deck.pages if p.layout_id == "timeline_flow")
    q_page = next(p for p in deck.pages if p.layout_id == "quote_callout")
    # 金句页绝不能含 Heading——LAYOUTS 只有 quote，漏出会触发 validate_layout 失败。
    assert not any(isinstance(b, Heading) for b in q_page.blocks)
    assert any(isinstance(b, Quote) for b in q_page.blocks)
    assert any(isinstance(b, Timeline) for b in tl_page.blocks)
    assert len([b for b in tl_page.blocks if isinstance(b, Timeline)][0].items) == 3

    # 走完整渲染 + 审计，确认真实链路可用。
    for page in (tl_page, q_page):
        html = render_page(deck, page, deck.pages.index(page))
        assert html.startswith("<!doctype html>")
        assert audit_page(deck, page)["pass"]


@pytest.mark.asyncio
async def test_repair_is_rejected_when_the_model_only_restates():
    """模型只是复述一遍（体量没变大）时必须拒绝采纳——否则只是"看起来改过"。

    拒绝后成稿应完全等同于第一轮，不能被补内容过程污染。
    """
    llm = ScriptedLLM(second=THIN_PLAN)
    draft = await compose_deck(topic="词根笔记", content="contest 和 contrast 总是记混。",
                               user_id="u1", llm=llm)
    deck = CardDeck.model_validate(draft["deck"])
    # 第二节原始只有 3 条；补内容被拒后，这一节必须仍是原始的 3 条，
    # 不能变成 RICH_PLAN 的 6 条，也不能被别的修正顶替。
    family = next((b.items for p in deck.pages for b in p.blocks
                   if getattr(b, "type", None) == "list"
                   and any("constant" in item.text for item in b.items)), None)
    assert family is not None and len(family) == 3, family
