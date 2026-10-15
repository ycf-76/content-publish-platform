"""Owner-scoped structured card edits and render preparation."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.cards.renderer import to_card_draft
from app.cards.schema import (
    DIRECTIONS, LAYOUTS, THEMES, VARIANT_OPTIONS, BentoGrid, CardDeck, Compare, CompareRow,
    _accessible_accents,
    Cta, Heading, ImageBlock, Item, ListBlock, Quote, Stat, Steps, Text, Timeline,
    TimelineItem, apply_direction, compatible_layouts,
)
from app.services.asset_library import list_assets
from app.services.chat_session import get_session, update_creative_state
from app.services.creative_artifact import (
    artifact_lock, build_storyboard, load_artifact, save_artifact,
)


EDIT_OPS: tuple[str, ...] = (
    "set_text", "set_image",
    "set_item", "add_item", "remove_item",
    "set_cell", "add_row", "remove_row", "set_title",
    "set_bento_cell", "set_stat_value",
    "set_timeline_item", "add_timeline_item", "remove_timeline_item",
    "set_quote", "set_layout", "set_direction", "set_theme", "set_variant", "set_accent",
)


class CardEdit(BaseModel):
    """块级编辑指令。一个操作只改一处，便于乐观并发与审计。"""

    page_id: str = Field(default="", max_length=32)
    block_id: str = Field(default="", max_length=32)
    op: Literal[
        "set_text", "set_image",
        "set_item", "add_item", "remove_item",
        "set_cell", "add_row", "remove_row", "set_title",
        "set_bento_cell", "set_stat_value",
        "set_timeline_item", "add_timeline_item", "remove_timeline_item",
        "set_quote", "set_layout", "set_direction", "set_theme", "set_variant", "set_accent",
    ]
    index: int | None = Field(default=None, ge=0, le=32)
    column: Literal["left", "right"] | None = None
    value: str | None = Field(default=None, max_length=600)
    value_pair: list[str] | None = Field(default=None, min_length=2, max_length=2)
    # 条目的副行与右侧标签。set_item/add_item 时给了才改，不给保留原值。
    note: str | None = Field(default=None, max_length=120)
    tag: str | None = Field(default=None, max_length=16)
    # 矩阵格子五层字段。set_bento_cell 时 index 指格子下标，可任选字段写入。
    kicker: str | None = Field(default=None, max_length=20)
    unit: str | None = Field(default=None, max_length=16)
    source: str | None = Field(default=None, max_length=40)


async def get_owned_artifact(artifact_id: str, user_id: str):
    artifact = load_artifact(artifact_id)
    if artifact is None or artifact.artifact_id != artifact_id:
        raise LookupError("创作作品不存在")
    if artifact.owner_user_id:
        if artifact.owner_user_id != user_id:
            raise PermissionError("无权访问该作品")
        return artifact
    # Backward compatibility for artifacts created before owner_user_id existed.
    if not artifact.source.session_id:
        raise PermissionError("作品缺少可验证的所有者")
    session = await get_session(artifact.source.session_id)
    if not session or session["user_id"] != user_id:
        raise PermissionError("无权访问该作品")
    return artifact


async def get_owned_card(artifact_id: str, user_id: str):
    artifact = await get_owned_artifact(artifact_id, user_id)
    if not artifact.card_deck:
        raise ValueError("该作品不是结构化卡片")
    deck = CardDeck.model_validate(artifact.card_deck)
    await verify_assets(deck, user_id)
    return artifact, deck


async def read_card(artifact_id: str, user_id: str) -> dict:
    artifact, deck = await get_owned_card(artifact_id, user_id)
    draft = to_card_draft(deck)
    draft["artifact_id"] = artifact_id
    draft["version"] = artifact.version
    return draft


async def verify_assets(deck: CardDeck, user_id: str) -> None:
    images = [block for page in deck.pages for block in page.blocks if isinstance(block, ImageBlock)]
    if not images:
        return
    assets = {asset["asset_id"]: asset for asset in await list_assets(user_id)}
    for image in images:
        asset = assets.get(image.media_id)
        if not asset or image.resolved_url != asset["original_url"]:
            raise ValueError("图片素材已删除、无访问权限或链接不匹配")


async def update_card(
    artifact_id: str, user_id: str, expected_version: int, page_id: str,
    block_id: str, new_text: str | None = None, new_asset_id: str | None = None,
) -> dict:
    """旧版接口：整块换文字或换图。保留以兼容已发出的调用。"""
    if new_text is not None and new_asset_id is not None:
        raise ValueError("一次只能修改文字或图片")
    if new_asset_id is not None:
        op, value = "set_image", new_asset_id
    elif new_text is not None:
        op, value = "set_text", new_text
    else:
        raise ValueError("必须提供文字或图片")
    return await apply_card_edit(artifact_id, user_id, expected_version, CardEdit(
        page_id=page_id, block_id=block_id, op=op, value=value,
    ))


async def apply_card_edit(artifact_id: str, user_id: str, expected_version: int, edit: CardEdit) -> dict:
    """整条读-改-写必须在锁内完成。

    否则两个并发编辑会各自读到同一 version，都通过乐观校验，
    后写的那次静默覆盖前一次的内容。
    """
    async with artifact_lock(artifact_id):
        return await _apply_edit_locked(artifact_id, user_id, expected_version, edit)


async def _apply_edit_locked(artifact_id: str, user_id: str, expected_version: int, edit: CardEdit) -> dict:
    artifact, deck = await get_owned_card(artifact_id, user_id)
    if expected_version != artifact.version:
        raise RuntimeError("卡片版本已更新，请刷新后重试")

    if edit.op == "set_theme":
        if edit.value not in THEMES:
            raise ValueError(f"未知主题: {edit.value}")
        deck.theme_id = edit.value
        # 切换主题后旧的强调色索引可能对新主题越界，钳制回默认，避免渲染出不存在的 class
        if deck.accent_index >= len(_accessible_accents(THEMES[deck.theme_id])):
            deck.accent_index = 0
        return await _commit(artifact, deck, artifact_id)

    if edit.op == "set_accent":
        # 强调色轴：index 指向 THEMES[theme].accents 的第 index 个（0 = 默认）。
        # 复用 edit.index 字段，避免给 CardEdit 再加一个几乎同义的字段。
        accents = _accessible_accents(THEMES[deck.theme_id])
        if edit.index is None or edit.index < 0 or edit.index >= len(accents):
            raise ValueError("无效的强调色索引")
        deck.accent_index = edit.index
        return await _commit(artifact, deck, artifact_id)

    if edit.op == "set_direction":
        if edit.value not in DIRECTIONS:
            raise ValueError(f"未知方向: {edit.value}")
        if not apply_direction(deck, edit.value):
            raise ValueError("该方向与当前版式一致，无需切换")
        return await _commit(artifact, deck, artifact_id)

    page = next((page for page in deck.pages if page.id == edit.page_id), None)
    if page is None:
        raise ValueError("页面不存在")

    if edit.op == "set_layout":
        if edit.value not in LAYOUTS:
            raise ValueError(f"未知版式: {edit.value}")
        if edit.value not in compatible_layouts(page):
            raise ValueError("当前页的组件不满足该版式，无法切换")
        page.layout_id = edit.value
        return await _commit(artifact, deck, artifact_id)

    block = next((block for block in page.blocks if block.id == edit.block_id), None)
    if block is None:
        raise ValueError("组件不存在")

    if edit.op == "set_text":
        if not isinstance(block, (Heading, Text, Cta)):
            raise ValueError("此组件不支持简单文字修改")
        replacement = type(block)(**{**block.model_dump(), "text": _text(edit.value)})
        page.blocks[page.blocks.index(block)] = replacement
    elif edit.op == "set_image":
        if not isinstance(block, ImageBlock):
            raise ValueError("此组件不是图片位")
        asset_id = (edit.value or "").strip()
        if not asset_id:
            raise ValueError("必须选择一张图片")
        asset = next((item for item in await list_assets(user_id) if item["asset_id"] == asset_id), None)
        if not asset:
            raise ValueError("图片不存在或不属于当前用户")
        page.blocks[page.blocks.index(block)] = ImageBlock(
            id=block.id, media_id=asset["asset_id"],
            source="ai" if asset.get("source") == "ai" else "upload",
            resolved_url=asset["original_url"], alt=asset["filename"][:80],
        )
    elif edit.op == "set_item":
        items = _items_of(block)
        position = _index(edit.index, len(items))
        current = items[position]
        items[position] = Item(
            text=_text(edit.value) if edit.value is not None else current.text,
            note=_optional_text(edit.note, 120) if edit.note is not None else current.note,
            tag=_optional_text(edit.tag, 16) if edit.tag is not None else current.tag,
        )
    elif edit.op == "add_item":
        items = _items_of(block)
        limit = 8 if isinstance(block, ListBlock) else 7
        if len(items) >= limit:
            raise ValueError(f"最多只能有 {limit} 项")
        items.append(Item(text=_text(edit.value),
                          note=_optional_text(edit.note, 120),
                          tag=_optional_text(edit.tag, 16)))
    elif edit.op == "remove_item":
        items = _items_of(block)
        minimum = 1 if isinstance(block, ListBlock) else 2
        if len(items) <= minimum:
            raise ValueError(f"至少保留 {minimum} 项")
        items.pop(_index(edit.index, len(items)))
    elif edit.op == "set_cell":
        compare = _compare_of(block)
        if edit.column is None:
            raise ValueError("必须指定左列或右列")
        position = _index(edit.index, len(compare.rows))
        row = compare.rows[position]
        if edit.column == "left":
            row.left = _text(edit.value, limit=60)
        else:
            row.right = _text(edit.value, limit=60)
    elif edit.op == "add_row":
        compare = _compare_of(block)
        if not edit.value_pair:
            raise ValueError("必须提供左右两列内容")
        if len(compare.rows) >= 6:
            raise ValueError("最多只能有 6 行")
        # value_pair 是左右两列；value 若同时给出则作为这一行的维度标签。
        compare.rows.append(CompareRow(
            label=_optional_text(edit.value, 30),
            left=_text(edit.value_pair[0], limit=60),
            right=_text(edit.value_pair[1], limit=60)))
    elif edit.op == "remove_row":
        compare = _compare_of(block)
        if len(compare.rows) <= 2:
            raise ValueError("至少保留 2 行")
        compare.rows.pop(_index(edit.index, len(compare.rows)))
    elif edit.op == "set_title":
        compare = _compare_of(block)
        if edit.column is None:
            raise ValueError("必须指定左列或右列")
        label = _text(edit.value, limit=30)
        if edit.column == "left":
            compare.left_title = label
        else:
            compare.right_title = label
    elif edit.op == "set_bento_cell":
        if not isinstance(block, BentoGrid):
            raise ValueError("此组件不是矩阵")
        position = _index(edit.index, len(block.cells))
        cell = block.cells[position]
        # 任一字段给了就改，不给的层保留原值——和 Item 的合并语义相同。
        if edit.value is not None:
            cell.big = _text(edit.value, limit=24)
        if edit.kicker is not None:
            cell.kicker = _text(edit.kicker, limit=20)
        if edit.note is not None:
            cell.note = _text(edit.note, limit=80)
        if edit.unit is not None:
            cell.unit = _text(edit.unit, limit=16)
        if edit.source is not None:
            cell.source = _text(edit.source, limit=40)
        if edit.tag is not None:
            # 不复用到 bento 上：tag 是账本专用语法，bento 用 kicker；显式拒绝。
            raise ValueError("矩阵格子请用 kicker，不要用 tag")
    elif edit.op == "set_stat_value":
        if not isinstance(block, Stat):
            raise ValueError("此组件不是单数据卡")
        cell = block.cell
        if edit.value is not None:
            cell.big = _text(edit.value, limit=24)
        if edit.kicker is not None:
            cell.kicker = _text(edit.kicker, limit=20)
        if edit.note is not None:
            cell.note = _text(edit.note, limit=80)
        if edit.unit is not None:
            cell.unit = _text(edit.unit, limit=16)
        if edit.source is not None:
            cell.source = _text(edit.source, limit=40)
    elif edit.op == "set_timeline_item":
        if not isinstance(block, Timeline):
            raise ValueError("此组件不是时间线")
        items = block.items
        position = _index(edit.index, len(items))
        current = items[position]
        items[position] = TimelineItem(
            date=_text(edit.value, limit=20) if edit.value is not None else current.date,
            text=_text(edit.note, limit=90) if edit.note is not None else current.text,
            note=_optional_text(edit.tag, 120) if edit.tag is not None else current.note,
        )
    elif edit.op == "add_timeline_item":
        if not isinstance(block, Timeline):
            raise ValueError("此组件不是时间线")
        items = block.items
        if len(items) >= 8:
            raise ValueError("最多只能有 8 条时间锚点")
        items.append(TimelineItem(
            date=_text(edit.value, limit=20),
            text=_text(edit.note, limit=90),
            note=_optional_text(edit.tag, 120),
        ))
    elif edit.op == "remove_timeline_item":
        if not isinstance(block, Timeline):
            raise ValueError("此组件不是时间线")
        items = block.items
        if len(items) <= 3:
            raise ValueError("至少保留 3 条时间锚点")
        items.pop(_index(edit.index, len(items)))
    elif edit.op == "set_quote":
        if not isinstance(block, Quote):
            raise ValueError("此组件不是金句卡")
        if edit.value is not None:
            block.text = _text(edit.value, limit=120)
        if edit.note is not None:
            block.author = _text(edit.note, limit=40)
        if edit.tag is not None:
            block.kicker = _text(edit.tag, limit=30)
    elif edit.op == "set_variant":
        if not isinstance(block, (ListBlock, Steps, Compare, BentoGrid, Stat, Timeline)):
            raise ValueError("此组件不支持切换视觉变体")
        variant = _optional_text(edit.value, 20)
        # 只接受 schema.VARIANT_OPTIONS 里声明过的变体，避免前端塞入任意 class。
        allowed = VARIANT_OPTIONS.get(block.type, [""])
        if variant not in allowed:
            raise ValueError(f"不支持的变体: {variant}")
        replacement = type(block)(**{**block.model_dump(), "variant": variant})
        page.blocks[page.blocks.index(block)] = replacement
    else:
        raise ValueError(f"不支持的编辑操作: {edit.op}")

    return await _commit(artifact, deck, artifact_id)


async def _commit(artifact, deck: CardDeck, artifact_id: str) -> dict:
    deck = CardDeck.model_validate(deck.model_dump())
    draft = to_card_draft(deck)
    artifact.card_deck = draft["deck"]
    artifact.storyboard = build_storyboard(draft["pages"], template_id="structured_cards")
    artifact.version += 1
    save_artifact(artifact)
    draft["artifact_id"] = artifact_id
    draft["version"] = artifact.version
    if artifact.source.session_id:
        await update_creative_state(artifact.source.session_id, {"_card_draft": draft})
    return draft


def _text(value: str | None, limit: int = 600) -> str:
    content = (value or "").strip()
    if not content:
        raise ValueError("内容不能为空")
    if len(content) > limit:
        raise ValueError(f"内容不能超过 {limit} 个字")
    return content


def _optional_text(value: str | None, limit: int) -> str:
    """副行 / 标签这类可选字段：允许留空（表示清空），只在有内容时校验长度。"""
    content = (value or "").strip()
    if len(content) > limit:
        raise ValueError(f"内容不能超过 {limit} 个字")
    return content


def _index(index: int | None, size: int) -> int:
    if index is None or index < 0 or index >= size:
        raise ValueError("位置不存在")
    return index


def _items_of(block) -> list[Item]:
    if not isinstance(block, (ListBlock, Steps)):
        raise ValueError("此组件没有可编辑的条目")
    return block.items


def _compare_of(block) -> Compare:
    if not isinstance(block, Compare):
        raise ValueError("此组件不是对比表")
    return block
