"""Compose a constrained card deck for the ReAct conversation, without any DAG dependency."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.cards.audit import audit_deck, audit_page, deck_density
from app.cards.recipe import RecipeId, get_recipe
from app.cards.renderer import to_card_draft
from app.cards.schema import (
    BentoGrid, CardDeck, CardPage, Cell, Compare, CompareRow, Cta, Heading, ImageBlock, Item,
    ListBlock, Quote, Stat, Steps, Text, ThemeId, Timeline, TimelineItem,
)
from app.services.asset_library import list_assets

logger = logging.getLogger(__name__)


class Section(BaseModel):
    kind: Literal["list", "steps", "compare", "text", "bento", "stat", "timeline", "quote"]
    title: str = Field(min_length=1, max_length=80)
    text: str = Field(default="", max_length=480)
    items: list[Item] = Field(default_factory=list, max_length=8)
    left_title: str = Field(default="之前", max_length=30)
    right_title: str = Field(default="之后", max_length=30)
    rows: list[CompareRow] = Field(default_factory=list, max_length=6)
    # P1：矩阵 / 单数据卡共享一组格子（bento 2-6 张，stat 只看第一张）
    cells: list[Cell] = Field(default_factory=list, max_length=6)
    # P2：时间线条目（date + text + note）
    timeline_items: list[TimelineItem] = Field(default_factory=list, max_length=8)
    # P2：金句（text + author + kicker）
    quote_text: str = Field(default="", max_length=120)
    quote_author: str = Field(default="", max_length=40)
    quote_kicker: str = Field(default="", max_length=30)


class Plan(BaseModel):
    subtitle: str = Field(default="", max_length=160)
    sections: list[Section] = Field(min_length=1, max_length=5)
    closing: str = Field(default="收藏备用", max_length=60)


async def _plan(topic: str, content: str, llm: Any, recipe_id: RecipeId | None = None) -> Plan:
    """把内容规划成 Plan。

    `recipe_id` 是用户选的整套骨架，它在这里**引导内容如何组织**，而不是事后把内容硬套进版式
    —— 硬套必然出现密度不够或溢出。无 LLM 时退化为按行拆分，此时 recipe 不生效（只能得到清单）。
    """
    recipe = get_recipe(recipe_id)
    if llm is not None:
        prompt = (
            "你是社媒图文信息架构师。仅输出 JSON 对象，不要 HTML/CSS/Markdown。\n"
            f"【用户选择的骨架】{recipe.label}（{recipe.hint}）。{recipe.guidance}\n"
            f"本骨架优先使用 kind：{'、'.join(recipe.preferred_kinds)}；"
            f"可用补充：{'、'.join(recipe.aux_kinds)}。\n"
            "将用户内容拆成 2-4 个有实质信息的页面，按语义选 kind: list、steps、compare、text、bento、stat、timeline、quote。\n"
            "对象形状: {\"subtitle\":\"封面副标题\",\"sections\":[{\"kind\":\"list\","
            "\"title\":\"标题\",\"text\":\"说明\","
            "\"items\":[{\"text\":\"主行\",\"note\":\"副行补充说明\",\"tag\":\"右侧短标签\"}],"
            "\"left_title\":\"之前\",\"right_title\":\"之后\","
            "\"rows\":[[\"维度标签\",\"前\",\"后\"]],"
            "\"cells\":[{\"kicker\":\"分类\",\"big\":\"数据\",\"unit\":\"单位\","
            "\"note\":\"解读\",\"source\":\"来源\"}],"
            "\"timeline_items\":[{\"date\":\"2024 Q1\",\"text\":\"标题\",\"note\":\"说明\"}],"
            "\"quote_text\":\"金句正文\",\"quote_author\":\"作者\",\"quote_kicker\":\"日期\"}],"
            "\"closing\":\"结尾句\"}。\n"
            "items 的元素可以只写一个字符串（等价 {\"text\":...}），但**强烈建议写对象**：\n"
            "note 是主行下面的灰色小字，用来补一句「为什么 / 怎么用 / 举个例子」；\n"
            "tag 是右侧的短标签（≤6 字，如词性、年份、难度），没有就省略。\n"
            "rows 的元素可以是 [\"前\",\"后\"]，也可以是 [\"这一行比什么\",\"前\",\"后\"]。\n"
            "cells（bento / stat 共用）每个格子有 kicker/big/unit/note/source 五层：\n"
            "- bento：4-6 格矩阵，每格一个数据点；少于 4 格会被审计判 FAIL；\n"
            "- stat：1 格数据强调，巨数字必须配 note（这数字在说什么）和 source（数据来源），\n"
            "  没有这两层看起来像孤立大数字。\n"
            "- timeline：3-5 条时间锚点，每条要有 date + text + note（背景说明）；\n"
            "- quote：1 句金句（60-80 字）+ author + kicker，允许较空但必须补三锚点。\n"
            "密度要求（卡片是 3:4 竖版，内容太少会出现大片空白，务必写足）：\n"
            "- list：5-6 条，每条都要有 note，不要只写两个字的词；\n"
            "- steps：4-5 步，每步写清「做什么 + 为什么」（为什么写进 note）；\n"
            "- compare：5 组对比行，两栏都要有内容，尽量给每行加维度标签；\n"
            "- bento：4-6 格，每格写满 kicker+big+unit+note，不要只给一个数字；\n"
            "- stat：1 格，写满 kicker+big+unit+note+source 五层；\n"
            "- text：写成 80 字以上的一段，包含原因、例子或类比，不要只写一句结论；\n"
            "- timeline：3-5 条时间锚点，每条 date + text + note；\n"
            "- quote：1 句金句（60-80 字）+ author + kicker，允许较空但必须补三锚点。\n"
            "尽量少用 text，优先用 list / steps / compare / bento / stat 这类信息密度高的结构。\n"
            "不要编造事实；超长文字请分段。"
            f"\n主题：{topic[:80]}\n原文：{content[:4500]}"
        )
        try:
            response = await llm.chat(messages=[
                {"role": "system", "content": "只输出满足要求的 JSON；保留用户提供的事实。"},
                {"role": "user", "content": prompt},
            ], max_tokens=2200)
            raw = response.get("content", "") if isinstance(response, dict) else ""
            match = re.search(r"\{[\s\S]*\}", raw)
            if match:
                return Plan.model_validate(json.loads(match.group(0)))
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("Structured card planning invalid: %s", exc)
        except Exception as exc:
            logger.warning("Structured card planning unavailable: %s", exc)
    if not content.strip():
        raise ValueError("缺少正文且无法完成内容规划，请先提供卡片文案")
    lines = [part.strip(" \t\n-•1234567890.、") for part in re.split(r"[\n。；]+", content) if part.strip()]
    items = [line[:75] for line in lines if line][:8]
    if len(items) >= 2:
        return Plan(subtitle=content[:80], sections=[Section(kind="list", title=topic[:80], items=items)])
    return Plan(subtitle=content[:80], sections=[Section(kind="text", title=topic[:80], text=content[:480])])


def _trim_item(item: Item) -> Item:
    """模型可能超长，截断后仍要保住副行——副行是密度的关键，不能因为超长就丢掉。"""
    return Item(text=item.text[:90], note=item.note[:120], tag=item.tag[:16])


def _trim_row(row: CompareRow) -> CompareRow:
    return CompareRow(label=row.label[:30], left=row.left[:85], right=row.right[:85])


def _main_texts(items) -> list[str]:
    """取条目的主行文本——副行只在账本版式里出现，退化成纯文字时只留主行。"""
    return [item.text for item in items if item.text]


def _trim_cell(cell: Cell) -> Cell:
    """截断单元字段时也保留 kicker/note——这些是密度与可信度的关键。"""
    return Cell(
        kicker=cell.kicker[:20], big=cell.big[:24], unit=cell.unit[:16],
        note=cell.note[:80], source=cell.source[:40],
    )


def _split_to_items(text: str, limit: int = 6) -> list[Item]:
    """把一段说明拆成清单条目——清单天然吃高度，是文字页欠填时的首选修正。

    只在能拆出足够多实质条目时才拆；拆不动就维持原样，绝不为了填满而灌水。
    """
    # 逗号也参与拆分：小红书清单本来就是短语，长句拆开后信息量不变、密度更高。
    parts = [part.strip(" \t\n-•，,、") for part in re.split(r"[\n；;。，,]+", text) if part.strip()]
    return [Item(text=part[:90]) for part in parts if len(part) >= 4][:limit]


def _fill_thin_pages(deck: CardDeck) -> CardDeck:
    """渲染前的欠填修正阶梯：不改文案语义，只换更能承载当前内容量的骨架。

    两条确定性修正：
    1. 文字页太空 → 拆成清单项，换 list_ledger（清单比整段文字吃高度）。
    2. 收尾页只有一句号召 → 补上前面各页的要点回顾。
    """
    for page in deck.pages:
        if page.layout_id != "content_text":
            continue
        text = next((b for b in page.blocks if isinstance(b, Text)), None)
        if text is None or audit_page(deck, page)["pass"]:
            continue
        items = _split_to_items(text.text)
        if len(items) < 3:
            continue
        page.blocks = [b for b in page.blocks if not isinstance(b, Text)]
        page.blocks.append(ListBlock(id=f"list_{page.id}", items=items))
        page.layout_id = "list_ledger"

    ending = next((p for p in deck.pages if p.layout_id == "end_cta"), None)
    if ending is not None and not audit_page(deck, ending)["pass"]:
        if not any(isinstance(b, ListBlock) for b in ending.blocks):
            review = [b.text for p in deck.pages[:-1]
                      for b in p.blocks if isinstance(b, Heading)][:5]
            if len(review) >= 3:
                ending.blocks.insert(1, ListBlock(id=f"list_{ending.id}", items=review))

    # 封面挂「本期导读」：把后续各页标题做成预告。
    # 这是带信息量的承载，不是用装饰图形把下半画幅糊满。
    cover = deck.pages[0]
    if cover.layout_id == "cover_display" and not audit_page(deck, cover)["pass"]:
        if not any(isinstance(b, ListBlock) for b in cover.blocks):
            preview = [b.text for p in deck.pages[1:]
                       for b in p.blocks if isinstance(b, Heading)][:4]
            if len(preview) >= 3:
                cover.blocks.append(ListBlock(id=f"list_{cover.id}", items=preview))
    return deck


def _volume(section: Section) -> int:
    """一节内容的体量（字符数），用来判断"补内容"到底补没补。"""
    return (len(section.text)
            + sum(len(item.text) + len(item.note) + len(item.tag) for item in section.items)
            + sum(len(row.label) + len(row.left) + len(row.right) for row in section.rows)
            + sum(len(c.kicker) + len(c.big) + len(c.unit) + len(c.note) + len(c.source)
                 for c in section.cells)
            + sum(len(t.date) + len(t.text) + len(t.note) for t in section.timeline_items)
            + len(section.quote_text) + len(section.quote_author) + len(section.quote_kicker))


async def _repair_plan(plan: Plan, deck: CardDeck, topic: str, content: str, llm: Any) -> Plan | None:
    """把密度审计的具体缺口回灌给模型，让它把欠填的章节补饱满。

    这是欠填修正阶梯的最后一阶：前两阶（换骨架、挂真实目录/回顾）都是确定性的、
    不新增内容；只有当它们仍撑不满时，才把「第几节、缺多少 px、缺在哪」交给模型扩写。

    三条约束，缺一不可：
    1. 只扩写欠填的章节，其余原样返回；
    2. 补完必须**真的变多**，否则视为模型只是把原话换个说法，沿用原稿；
    3. 明确禁止编造事实——密度不够的解法是把原文里已有的信息写足，不是注水。
    """
    if llm is None:
        return None
    failing = [r for r in audit_deck(deck) if not r["pass"]]
    if not failing:
        return None

    # 用页面标题把审计结果映射回 section 下标：正文页的 Heading 就是 section.title。
    by_id = {page.id: page for page in deck.pages}
    targets: list[tuple[int, dict]] = []
    for report in failing:
        page = by_id.get(report["page_id"])
        if page is None:
            continue
        heading = next((b.text for b in page.blocks if isinstance(b, Heading)), None)
        index = next((i for i, s in enumerate(plan.sections) if s.title == heading), None)
        if index is not None:
            targets.append((index, report))
    if not targets:
        return None

    brief = "\n".join(
        f'- 第 {index + 1} 节「{plan.sections[index].title}」（kind={plan.sections[index].kind}）：'
        f'当前填充率 {report["fill"]:.0%}。{report["hint"] or "内容不足以填满 3:4 画幅"}'
        for index, report in targets
    )
    prompt = (
        "下面是社媒图文卡片的内容规划。卡片是 3:4 竖版，有几节内容太少，"
        "渲染后会出现大片空白，看起来很廉价。\n"
        "请**只扩写**下列章节，其余章节一字不改地原样保留，整体仍返回一个完整 JSON 对象。\n"
        "扩写铁律：\n"
        "- 保留原有事实与观点，**严禁编造**原文里没有的信息；\n"
        "- 缺多少补多少：清单补足到 5-6 条、对比补足到 5 组、说明写到 80 字以上；\n"
        "- 宁可多写一条真实要点，也不要把原来的话换个说法凑数。\n"
        f"需要补内容的章节：\n{brief}\n\n"
        f"当前规划 JSON：\n{plan.model_dump_json()}\n\n"
        f"原文（从中提取更多真实信息来扩写）：\n{content[:3000]}"
    )
    try:
        response = await llm.chat(messages=[
            {"role": "system", "content": "只输出满足要求的 JSON；保留用户提供的事实。"},
            {"role": "user", "content": prompt},
        ], max_tokens=2600)
        raw = response.get("content", "") if isinstance(response, dict) else ""
        match = re.search(r"\{[\s\S]*\}", raw)
        if not match:
            return None
        candidate = Plan.model_validate(json.loads(match.group(0)))
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning("卡片密度补内容返回非法: %s", exc)
        return None
    except Exception as exc:
        logger.warning("卡片密度补内容不可用: %s", exc)
        return None

    if len(candidate.sections) != len(plan.sections):
        return None
    # 必须真的变多，否则说明模型只是在复述，沿用原稿比"看起来改过"更诚实。
    for index, _ in targets:
        if _volume(candidate.sections[index]) <= _volume(plan.sections[index]):
            return None
    return candidate


def _asset_block(asset: dict, block_id: str) -> ImageBlock:
    return ImageBlock(
        id=block_id,
        media_id=asset["asset_id"],
        source="ai" if asset.get("source") == "ai" else "upload",
        resolved_url=asset["original_url"],
        alt=asset.get("filename", "配图")[:80],
    )


def _build_deck(
    plan: Plan, topic: str, images: list[dict], image_layout: str, theme_id: str, deck_id: str,
) -> CardDeck:
    """把语义规划落成 Deck。抽出来是因为「补内容」后要用同一套规则重建一次。

    `images` 会被按版式消费（pop），剩下的由调用方作为未使用素材上报。
    """
    pages: list[CardPage] = []
    cover_blocks: list = [Heading(id="heading_1", text=topic)]
    if plan.subtitle:
        cover_blocks.append(Text(id="text_1", text=plan.subtitle))
    cover_layout = "cover_display"
    if images and image_layout == "top":
        cover_layout = "cover_top_image"
        cover_blocks.append(_asset_block(images.pop(0), "image_1"))
    pages.append(CardPage(id="page_01", role="cover", layout_id=cover_layout, blocks=cover_blocks))

    for i, section in enumerate(plan.sections[:5], 2):
        blocks: list = [Heading(id=f"heading_{i}", text=section.title)]
        if section.kind == "list" and section.items:
            layout = "list_ledger"
            blocks.append(ListBlock(id=f"list_{i}", items=[_trim_item(it) for it in section.items]))
            if images and image_layout == "side":
                layout = "image_right_ledger"
                blocks.append(_asset_block(images.pop(0), f"image_{i}"))
        elif section.kind == "steps" and len(section.items) >= 2:
            layout = "steps_flow"
            blocks.append(Steps(id=f"steps_{i}", items=[_trim_item(it) for it in section.items[:7]]))
        elif section.kind == "compare" and len(section.rows) >= 2:
            layout = "compare_split"
            blocks.append(Compare(id=f"compare_{i}", left_title=section.left_title,
                                  right_title=section.right_title,
                                  rows=[_trim_row(row) for row in section.rows]))
        elif section.kind == "bento" and len(section.cells) >= 2:
            # 矩阵：2-6 格自适应，≥4 格才过最小密度线。
            layout = "bento_grid"
            blocks.append(BentoGrid(id=f"bento_{i}",
                                    cells=[_trim_cell(c) for c in section.cells[:6]]))
        elif section.kind == "stat" and section.cells:
            layout = "stat_card"
            blocks.append(Stat(id=f"stat_{i}", cell=_trim_cell(section.cells[0])))
        elif section.kind == "timeline" and len(section.timeline_items) >= 3:
            layout = "timeline_flow"
            blocks.append(Timeline(id=f"timeline_{i}", items=section.timeline_items[:8]))
        elif section.kind == "quote" and section.quote_text.strip():
            layout = "quote_callout"
            # 金句页的 LAYOUTS 只含 quote、不含 heading（kicker 由块内承载），
            # 必须把前面 prepended 的 Heading 移除，否则 validate_layout 报"含有不允许的组件"。
            blocks = [b for b in blocks if not isinstance(b, Heading)]
            blocks.append(Quote(
                id=f"quote_{i}", text=section.quote_text.strip(),
                author=section.quote_author.strip(), kicker=section.quote_kicker.strip(),
            ))
        else:
            layout = "content_text"
            blocks.append(Text(id=f"text_{i}", text=(section.text or "；".join(_main_texts(section.items)) or section.title)[:480]))
        if images and image_layout == "overlay":
            layout = "image_bg_overlay"
            blocks = [Heading(id=f"heading_{i}", text=section.title)]
            summary = section.text or "；".join(_main_texts(section.items[:2])) or section.title
            blocks.append(Text(id=f"text_{i}", text=summary[:160]))
            blocks.append(_asset_block(images.pop(0), f"image_{i}"))
        elif images and image_layout == "top" and i == 2:
            # Additional uploaded images should be used, not silently discarded.
            layout = "image_bg_overlay"
            summary = section.text or "；".join(_main_texts(section.items[:2])) or section.title
            blocks = [Heading(id=f"heading_{i}", text=section.title),
                      Text(id=f"text_{i}", text=summary[:160]),
                      _asset_block(images.pop(0), f"image_{i}")]
        pages.append(CardPage(id=f"page_{i:02}", role="body", layout_id=layout, blocks=blocks))

    pages.append(CardPage(id=f"page_{len(pages) + 1:02}", role="ending", layout_id="end_cta", blocks=[
        Heading(id="heading_end", text="回顾一下"),
        Cta(id="cta_end", text=plan.closing or "收藏备用"),
    ]))
    return CardDeck(deck_id=deck_id, title=topic, theme_id=theme_id, pages=pages)


async def compose_deck(
    *, topic: str, content: str, user_id: str, llm: Any = None,
    asset_ids: list[str] | None = None,
    theme_id: ThemeId = "ink",
    image_layout: Literal["top", "side", "overlay"] = "top",
    recipe_id: RecipeId | None = None,
) -> dict:
    """Validate owner-scoped assets, plan semantics, then deterministically build HTML from a deck.

    `recipe_id` 是用户拍板的整套骨架，作用于内容规划阶段（见 `_plan`）。
    """
    topic = topic.strip()[:80]
    if not topic:
        raise ValueError("卡片主题不能为空")
    selected_ids = asset_ids or []
    if len(selected_ids) > 3 or len(set(selected_ids)) != len(selected_ids):
        raise ValueError("一次最多使用 3 张不重复的上传图片")
    available = {asset["asset_id"]: asset for asset in await list_assets(user_id)} if selected_ids else {}
    if any(asset_id not in available for asset_id in selected_ids):
        raise ValueError("图片不存在或不属于当前用户，请先通过素材库上传")
    images = [available[asset_id] for asset_id in selected_ids]
    plan = await _plan(topic, content, llm, recipe_id)
    deck_id = "deck_" + uuid.uuid4().hex[:12]

    pending = list(images)
    deck = _fill_thin_pages(_build_deck(plan, topic, pending, image_layout, theme_id, deck_id))

    # 欠填修正阶梯的最后一阶：确定性手段都用尽后仍有页撑不满，
    # 就把审计缺口回灌给模型补一轮内容，补完更密才采用。
    repaired = await _repair_plan(plan, deck, topic, content, llm)
    if repaired is not None:
        pending_repaired = list(images)
        candidate = _fill_thin_pages(
            _build_deck(repaired, topic, pending_repaired, image_layout, theme_id, deck_id))
        if deck_density(candidate)["min_fill"] > deck_density(deck)["min_fill"]:
            deck, pending = candidate, pending_repaired

    draft = to_card_draft(deck)
    if pending:
        draft["unused_asset_ids"] = [asset["asset_id"] for asset in pending]
    return draft
