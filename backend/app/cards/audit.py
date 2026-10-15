"""Density audit for a card deck — computed before rendering, not after.

Easel audits the rendered PNG (pixel edge density). We can do better: because the
model never writes markup and the deck is a validated contract, every block has a
known height budget. That lets us predict dead space at compose time, while there
is still a chance to add content or swap the skeleton, instead of discovering it
after the image is rendered.

The numbers below mirror renderer.py's CSS. They are budgets, not exact layout —
the final PNG export is still the ground truth.
"""
from __future__ import annotations

import math

from app.cards.schema import (
    BentoGrid, CardDeck, CardPage, Code, Compare, Cta, Footer, Heading, IconGrid, ImageBlock,
    Kicker, ListBlock, Qa, Quote, Stat, Steps, Text, Timeline,
)

CANVAS_H = 1440
PAD_TOP = 88
PAD_BOTTOM = 190          # 给绝对定位的 footer 留位
CONTENT_H = CANVAS_H - PAD_TOP - PAD_BOTTOM
CONTENT_W = 1080 - 82 * 2

FILL_MIN = 0.75           # 内容需覆盖 ≥75% 可用画高
DEAD_BAND_MAX = 0.15      # 任何空白带 >15% 画高即判失败

# 最小密度线：低于此值，该骨架必然出现死空白（来自 Easel card-recipes 的实战阈值）
MIN_DENSITY: dict[str, tuple[str, int]] = {
    "list_ledger": ("清单项", 4),
    "image_right_ledger": ("清单项", 4),
    "steps_flow": ("步骤", 4),
    "compare_split": ("对比行", 5),
    # P1：矩阵少于 4 格（<2 行 3）信息量不足；stat 是单卡，1 张永远成立。
    "bento_grid": ("格子", 4),
    "stat_card": ("数据卡", 1),
    "timeline_flow": ("时间锚点", 3),
    "quote_callout": ("金句", 1),
}

LINE_H = {
    "cover_h1": 136,      # 116px * 1.17
    "body_h1": 80,        # 66px * 1.22
    "text": 58,           # 34px * 1.7
    "cta": 68,            # 50px * 1.35
}
CHARS_PER_LINE = {
    "cover_h1": 7,        # 116px 字号，880px 上限
    "body_h1": 13,
    "text": 26,
    "cta": 17,
}


def _ledger_row(item, wrap: int, base: int) -> int:
    """一条账本行的高度：base 已含一行主行，副行再吃 44px，每多折一行 58px。

    副行是密度杠杆——带副行的行更高，所以填满同一块画幅需要的主行数更少
    （清单从 6 条降到 5 条），而模型更愿意写 5 条带说明的要点。
    """
    lines = max(1, math.ceil(_cjk_len(item.text) / wrap))
    if item.note:
        # 副行字号更小，同样宽度能装更多字，按 0.62 折算
        lines += max(1, math.ceil(_cjk_len(item.note) * 0.62 / wrap))
        return base + 44 + 58 * max(0, lines - 2)
    return base + 58 * (lines - 1)


def _compare_row(row) -> int:
    """行标签不额外吃高度——它只占第一列，与左右单元格同高。"""
    longest = max(_cjk_len(row.left), _cjk_len(row.right))
    return 112 + (40 if longest > 18 else 0)


def _cjk_len(text: str) -> int:
    """按中文占 1 字宽、英文数字占 0.55 字宽估算视觉长度。"""
    return sum(1 if ord(ch) > 0x2E80 else 0.55 for ch in text)


def block_height(block, layout_id: str) -> int:
    """单个内容块的高度预算（px）。"""
    if isinstance(block, Heading):
        kind = "cover_h1" if layout_id.startswith("cover") or layout_id == "image_bg_overlay" else "body_h1"
        return _lines_of_text(block.text, kind) * LINE_H[kind]
    if isinstance(block, Text):
        return _lines_of_text(block.text, "text") * LINE_H["text"] + 20
    if isinstance(block, ListBlock):
        return sum(_ledger_row(item, 24, 123) for item in block.items)
    if isinstance(block, Steps):
        return sum(_ledger_row(item, 22, 155) for item in block.items)
    if isinstance(block, Compare):
        head = 34 + 32 + 28 * 2          # 列标题 + 内边距
        rows = sum(_compare_row(row) for row in block.rows)
        return head + rows
    if isinstance(block, ImageBlock):
        if layout_id == "cover_top_image":
            return 680 + 56
        if layout_id == "image_right_ledger":
            return 850
        return 0                          # 满版蒙层不占流内高度
    if isinstance(block, Cta):
        return _lines_of_text(block.text, "cta") * LINE_H["cta"] + 62 * 2
    if isinstance(block, BentoGrid):
        # 实测下 grid-auto-rows:1fr + flex:1 把 bento 网格撑到与 .content 等高，
        # 跟格数基本无关（2 / 4 / 6 格都在 938px 附近）——直接用 940 估值。
        # 这样 audit 不会误判「6 格还欠填」，让 model 比真实情况修更少。
        if len(block.cells) < 2:
            return 0                          # schema 已拒
        return 940
    if isinstance(block, Stat):
        # 单数据卡也是 flex:1 填满，巨数字 184px + note/source 撑出主体；
        # 实测 ~1100，与机芯高度 (CONTENT_H - heading - margin) 一致。
        return 1100
    if isinstance(block, Timeline):
        # timeline 是 flex:1，实测会把整段内容区（heading 以下）吃满，
        # 跟条数关系不大（3 条 space-around、8 条挤满都是同高）。直接给 ~1080。
        if len(block.items) < 3:
            return 0                          # schema 已拒，但留个底
        return 1080
    if isinstance(block, Quote):
        # 呼吸型骨架：quote_callout 的 LAYOUTS 只有 quote 一块，且 .quote 是 flex:1，
        # 会把整段内容区吃满（上下发丝线 + 内部 space-between 把三段推到顶/中/底），
        # 所以视觉上整版铺满，box 高度即 CONTENT_H。真正的「呼吸」在 box 内部留白，
        # 由 Easel 像素审计（max_gap ≤15%）把关，本层只报「是否铺满画幅」。
        return CONTENT_H
    # ---- 补齐的 5 个 Block 的高度预算 ----
    if isinstance(block, Kicker):
        # 26px 字号 + 30px 下边距
        return 61
    if isinstance(block, Footer):
        # 24px * 1.5 行高 + 22px 上内边距 + 发丝线
        return _lines_of_text(block.text, "text") * 36 + 22
    if isinstance(block, Qa):
        # 每条 = 上下内边距 48 + 问题行 44 + 回答块（14 间距 + 每行 40）
        total = 0
        for pair in block.pairs:
            q_lines = max(1, math.ceil(_cjk_len(pair.q) / 24))
            a_lines = max(1, math.ceil(_cjk_len(pair.a) / 30))
            total += 48 + 44 * q_lines + 14 + 40 * a_lines
        return total
    if isinstance(block, Code):
        # 等宽面板：上下内边距 60 + 每行 41（25px * 1.62）；等宽每字约 15px 宽
        per_line = max(1, math.ceil(len(block.content) / 52))
        return 60 + 41 * per_line
    if isinstance(block, IconGrid):
        # 两列网格：每格 56 内边距 + 42 图标行高，行间 22，外加 26 上边距
        rows = math.ceil(len(block.pairs) / 2)
        return 26 + rows * 98 + (rows - 1) * 22
    return 0


def _lines_of_text(text: str, kind: str) -> int:
    return max(1, math.ceil(_cjk_len(text) / CHARS_PER_LINE[kind]))


def page_bands(heights: list[int], content_h: int = CONTENT_H) -> list[bool]:
    """把内容块按顺序铺进内容区，判断 4 个等分带有没有被覆盖。"""
    band_h = content_h / 4
    bands = [False] * 4
    cursor = 0.0
    for h in heights:
        start, end = cursor, cursor + h
        for i in range(4):
            lo, hi = i * band_h, (i + 1) * band_h
            if start < hi and end > lo:
                bands[i] = True
        cursor = end
    return bands


def audit_page(deck: CardDeck, page: CardPage) -> dict:
    heights = [block_height(b, page.layout_id) for b in page.blocks]
    if page.layout_id not in ("cover_top_image", "image_bg_overlay", "quote_callout"):
        heights.insert(0, 71)              # kicker
    total = sum(heights)
    bands = page_bands(heights) if total else [False] * 4

    problems: list[str] = []
    hints: list[str] = []

    fill = min(1.0, total / CONTENT_H)
    # 呼吸型骨架（quote/stat）允许 ≤60% 覆盖，但必须有锚点（kicker/author/source）。
    fill_min = 0.40 if page.layout_id == "quote_callout" else FILL_MIN
    if fill < fill_min:
        gap = fill_min - fill
        problems.append(f"填充率 {fill * 100:.0f}% < {fill_min * 100:.0f}%（欠填 {gap * 100:.0f}%）")
        hints.append(_hint_for(page, gap))

    # 最大连续空白带：内容末行之后到内容区底部
    tail_gap = max(0.0, (CONTENT_H - total) / CONTENT_H)
    if tail_gap > DEAD_BAND_MAX and bands[-1] is False:
        problems.append(f"底部死空白 {tail_gap * 100:.0f}% > {DEAD_BAND_MAX * 100:.0f}%")
        hints.append("补一条收尾注解/来源行把底部锚住，或换更省高度的骨架")

    empty_mid = [i for i in (1, 2) if not bands[i] and bands[i - 1]]
    if empty_mid:
        problems.append("中段出现空白带（内容堆在顶部）")
        hints.append("用 space-between 让块均匀分布，或补一个结构化承载（对比表/步骤/注解）")

    if not bands[3] and bands[0]:
        problems.append("头重脚轻：顶部有内容、底部近空")

    requirement = MIN_DENSITY.get(page.layout_id)
    if requirement:
        label, minimum = requirement
        count = _count_of(page)
        if count is not None and count < minimum:
            problems.append(f"{label}仅 {count} 条，低于最小密度线 {minimum}")
            hints.append(f"把{label}补到 {minimum} 条以上，或换成能容纳当前内容量的骨架")

    return {
        "page_id": page.id,
        "layout_id": page.layout_id,
        "content_height": int(total),
        "fill": round(fill, 3),
        "bands": bands,
        "pass": not problems,
        "problems": problems,
        "hint": hints[0] if hints else "",
    }


def _count_of(page: CardPage) -> int | None:
    for block in page.blocks:
        if isinstance(block, (ListBlock, Steps)):
            return len(block.items)
        if isinstance(block, Compare):
            return len(block.rows)
        if isinstance(block, BentoGrid):
            return len(block.cells)
        if isinstance(block, Timeline):
            return len(block.items)
    return None


def _hint_for(page: CardPage, gap: float) -> str:
    missing = int(gap * CONTENT_H)
    if page.layout_id in ("content_text", "cover_display"):
        return (f"文字页缺少 {missing}px 内容：加一行「为什么」、一个例子/类比，"
                f"或把该页改成清单/对比表这类天然吃高度的骨架")
    if page.layout_id == "end_cta":
        return f"收尾页缺少 {missing}px：补 3-5 条要点回顾，别只放一句行动号召"
    if page.layout_id == "bento_grid":
        return f"矩阵缺 {missing}px：把格子补到 ≥4 个，或给现有格子加 note/source"
    if page.layout_id == "stat_card":
        return (f"单数据卡缺 {missing}px：note 是这段数字到底在说什么、"
                f"source 让数据可追溯——没有这两层会像孤立大数字")
    if page.layout_id == "timeline_flow":
        return f"时间线缺 {missing}px：把条目补到 ≥3 条，或给每条加 note 补充背景"
    if page.layout_id == "quote_callout":
        return (f"金句页缺 {missing}px：必须补三锚点——顶 kicker/日期、"
                f"底出处/作者、上下发丝线，否则呼吸会被读成欠填")
    return f"缺少约 {missing}px 内容：扩写要点或换高容量骨架"


def audit_deck(deck: CardDeck) -> list[dict]:
    return [audit_page(deck, page) for page in deck.pages]


def deck_density(deck: CardDeck) -> dict:
    """整副卡片的密度概览，供 API/前端提示使用。"""
    reports = audit_deck(deck)
    failed = [r for r in reports if not r["pass"]]
    return {
        "pass": not failed,
        "page_count": len(reports),
        "failed_page_ids": [r["page_id"] for r in failed],
        "min_fill": min((r["fill"] for r in reports), default=0.0),
        "pages": reports,
    }
