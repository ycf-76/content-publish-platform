#!/usr/bin/env python3
"""离线生成卡片骨架（recipe）与主题（theme）的预览图。

澄清卡里的每个选项都要带预览图 —— 用户是看着图选的，不是读参数选的。
产物是**真实渲染**的示例卡，不是示意图：示意图会让用户选完发现货不对板。

用法：
    python scripts/gen_card_previews.py

产出（前端静态目录，URL 即 /static/recipe-preview/...）：
    frontend/public/static/recipe-preview/{recipe_id}.png    整套骨架的页序列拼图
    frontend/public/static/recipe-preview/theme/{theme}.png  单张主题示例卡
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "frontend" / "public" / "static" / "recipe-preview"

# 与 cards/export.py 一致：注意目录名带尾空格
CHROME = ROOT / "pw-browsers " / "chromium-1228" / "chrome-win64" / "chrome.exe"

CARD_W, CARD_H = 1080, 1440
THUMB_W = 216          # 拼图里单页宽度
GAP = 10


# ───────────────────────── 示例内容 ─────────────────────────
# 每个版式给一份「能过最小密度线」的示例，保证预览图看起来是成品而不是空骨架。

def _blocks_for(layout_id: str) -> list:
    from app.cards.schema import (
        BentoGrid, Cell, Compare, CompareRow, Cta, Heading, Item, ListBlock, Quote,
        Stat, Steps, Text, Timeline, TimelineItem,
    )

    if layout_id == "cover_display":
        return [Heading(id="heading_1", text="护肤避坑指南"),
                Text(id="text_1", text="五个成分党不会踩的坑")]
    if layout_id == "list_ledger":
        return [Heading(id="heading_1", text="最常见的五个坑"),
                ListBlock(id="list_1", items=[
                    Item(text="盲目叠加酸类", note="屏障受损后才想起来修护", tag="高危"),
                    Item(text="迷信高浓度", note="浓度不等于效果，刺激先到", tag="认知"),
                    Item(text="忽略防晒", note="白天用 A 醇不防晒等于白做", tag="必做"),
                    Item(text="频繁更换产品", note="皮肤适应周期至少 28 天", tag="耐心"),
                    Item(text="只看成分表", note="配方工艺和浓度同样关键", tag="进阶"),
                ])]
    if layout_id == "steps_flow":
        return [Heading(id="heading_1", text="正确护肤四步"),
                Steps(id="steps_1", items=[
                    Item(text="温和清洁", note="氨基酸表活，水温 32 度左右"),
                    Item(text="补水打底", note="角质层含水量先提上来"),
                    Item(text="功效成分", note="一次只上一个新成分"),
                    Item(text="封闭保湿", note="面霜锁住前面所有步骤"),
                ])]
    if layout_id == "compare_split":
        return [Heading(id="heading_1", text="两种思路对比"),
                Compare(id="compare_1", left_title="猛药路线", right_title="稳扎稳打", rows=[
                    CompareRow(label="见效速度", left="两周可见", right="六到八周"),
                    CompareRow(label="刺激风险", left="脱皮泛红常见", right="几乎为零"),
                    CompareRow(label="适合人群", left="耐受厚皮", right="敏感肌友好"),
                    CompareRow(label="失败成本", left="屏障修复数月", right="随时可调整"),
                    CompareRow(label="长期收益", left="容易反复", right="稳定可持续"),
                ])]
    if layout_id == "bento_grid":
        return [Heading(id="heading_1", text="关键数据一览"),
                BentoGrid(id="bento_1", cells=[
                    Cell(kicker="周期", big="28", unit="天", note="皮肤代谢一个完整周期", source="皮肤科共识"),
                    Cell(kicker="含水", big="30", unit="%", note="角质层健康含水量下限", source="皮肤屏障研究"),
                    Cell(kicker="防晒", big="30", unit="SPF+", note="日常通勤的最低要求", source="光防护指南"),
                    Cell(kicker="适应", big="2", unit="周", note="新成分观察期", source="耐受建立建议"),
                    Cell(kicker="清洁", big="32", unit="°C", note="洁面水温上限", source="温和清洁建议"),
                    Cell(kicker="步骤", big="4", unit="步", note="基础护肤不必要更多", source="精简护肤原则"),
                ])]
    if layout_id == "stat_card":
        return [Heading(id="heading_1", text="一个关键数字"),
                Stat(id="stat_1", cell=Cell(
                    kicker="屏障修复", big="90", unit="天",
                    note="受损屏障恢复到健康状态需要的完整时间", source="皮肤科临床观察"))]
    if layout_id == "timeline_flow":
        return [Heading(id="heading_1", text="护肤进阶时间线"),
                Timeline(id="timeline_1", items=[
                    TimelineItem(date="第 1-2 周", text="建立基础清洁保湿", note="不加任何功效成分"),
                    TimelineItem(date="第 3-4 周", text="引入防晒", note="白天必做，阴天也是"),
                    TimelineItem(date="第 5-8 周", text="上一个功效成分", note="从低浓度开始"),
                    TimelineItem(date="第 9 周起", text="评估并微调", note="拍照对比，别靠感觉"),
                ])]
    if layout_id == "quote_callout":
        return [Quote(id="quote_1", text="护肤的尽头不是更贵的精华，是更稳的屏障。",
                      author="成分党笔记", kicker="2026 · 护肤观")]
    if layout_id == "end_cta":
        return [Heading(id="heading_1", text="回顾一下"),
                ListBlock(id="list_1", items=[
                    Item(text="先修屏障", note="功效成分排在后面"),
                    Item(text="防晒优先", note="性价比最高的一步"),
                    Item(text="少即是多", note="精简比堆砌有效"),
                ]),
                Cta(id="cta_1", text="收藏备用，照着做就行")]
    raise ValueError(f"示例内容未覆盖版式: {layout_id}")


def build_sample_deck(sequence: tuple[str, ...], theme_id: str):
    from app.cards.schema import CardDeck, CardPage

    pages = []
    for i, layout_id in enumerate(sequence, 1):
        role = "cover" if i == 1 else ("ending" if layout_id == "end_cta" else "body")
        pages.append(CardPage(id=f"page_{i:02}", role=role, layout_id=layout_id,
                              blocks=_blocks_for(layout_id)))
    return CardDeck(deck_id="deck_preview", title="护肤避坑指南", kicker="护肤",
                    theme_id=theme_id, pages=pages)


# ───────────────────────── 渲染 ─────────────────────────

async def _shoot(browser, html: str, out: Path) -> None:
    page = await browser.new_page(viewport={"width": CARD_W, "height": CARD_H})
    try:
        await page.set_content(html, wait_until="load", timeout=20000)
        try:
            await page.evaluate("document.fonts && document.fonts.ready")
        except Exception:
            pass
        await page.locator("article").screenshot(path=str(out))
    finally:
        await page.close()


async def generate() -> int:
    from PIL import Image
    from playwright.async_api import async_playwright

    from app.cards.recipe import RECIPES
    from app.cards.renderer import render_page
    from app.cards.schema import THEMES

    (OUT_DIR / "theme").mkdir(parents=True, exist_ok=True)

    launch = {"headless": True}
    if CHROME.is_file():
        launch["executable_path"] = str(CHROME)
    else:
        print(f"WARN: 未找到内置 Chromium（{CHROME}），改用 playwright 默认浏览器")

    # 中间页截图放系统临时目录：落在输出目录会被「批量删除」安全策略拦下，
    # 而且中途失败会留一堆 _tmp_*.png 污染静态资源。
    tmpdir = Path(tempfile.mkdtemp(prefix="card_preview_"))

    async with async_playwright() as p:
        browser = await p.chromium.launch(**launch)
        try:
            # 骨架预览：整套页序列横向拼图，让用户一眼看出「这套几页、什么结构」
            for recipe in RECIPES.values():
                deck = build_sample_deck(recipe.sequence, "ink")
                shots = []
                for i, page in enumerate(deck.pages):
                    tmp = tmpdir / f"{recipe.id}_{i}.png"
                    await _shoot(browser, render_page(deck, page, i), tmp)
                    shots.append(tmp)
                thumb_h = round(THUMB_W * CARD_H / CARD_W)
                canvas = Image.new("RGB", (THUMB_W * len(shots) + GAP * (len(shots) - 1), thumb_h), "#ffffff")
                for i, s in enumerate(shots):
                    img = Image.open(s).convert("RGB").resize((THUMB_W, thumb_h), Image.LANCZOS)
                    canvas.paste(img, (i * (THUMB_W + GAP), 0))
                out = OUT_DIR / f"{recipe.id}.png"
                canvas.save(out)
                print(f"OK  {out.relative_to(ROOT)}  {recipe.label}（{len(shots)} 页）")

            # 主题预览：一张封面卡，看配色与字体气质
            cover_seq = ("cover_display", "list_ledger", "end_cta")
            for name, spec in THEMES.items():
                deck = build_sample_deck(cover_seq, name)
                tmp = tmpdir / f"theme_{name}.png"
                await _shoot(browser, render_page(deck, deck.pages[1], 1), tmp)
                thumb_h = round(THUMB_W * CARD_H / CARD_W)
                img = Image.open(tmp).convert("RGB").resize((THUMB_W, thumb_h), Image.LANCZOS)
                out = OUT_DIR / "theme" / f"{name}.png"
                img.save(out)
                print(f"OK  {out.relative_to(ROOT)}  {spec['label']}")
        finally:
            await browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(generate()))
