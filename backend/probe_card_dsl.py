"""探针：验证 backend/app/cards 的 DSL 渲染链路能否真正出图。

不依赖 LLM —— 直接手搓一个合法 Deck，覆盖 7 个版式，
走 render_page -> Playwright 截图 -> audit 门禁，证明这套灵活架构是活的。
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.cards.audit import audit_page
from app.cards.renderer import render_page
from app.cards.schema import (
    BentoGrid, CardDeck, CardPage, Cell, Compare, CompareRow, Cta, Heading,
    Item, ListBlock, Quote, Stat, Steps, Text, Timeline, TimelineItem,
)

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "outputs" / "card_dsl_probe"
BROWSER = ROOT / "pw-browsers " / "chromium-1228" / "chrome-win64" / "chrome.exe"


def build_deck(theme_id: str = "ink") -> CardDeck:
    """手搓 Deck：封面 + 清单 + 步骤 + 矩阵 + 时间线 + 金句 + 收尾。"""
    return CardDeck(
        deck_id="dsl_probe_001",
        title="多智能体小红书发布平台 · DSL 链路验证",
        kicker="CARD DSL · PROBE",
        theme_id=theme_id,
        pages=[
            # 1. 封面（可挂"本期导读"清单填满下半画幅）
            CardPage(
                id="p_cover", role="cover", layout_id="cover_display",
                blocks=[
                    Heading(id="b_cover_h", text="卡片 DSL 渲染链路验证"),
                    Text(id="b_cover_t", text="不依赖 LLM，直接手搓 Deck 走通出图。"),
                    ListBlock(id="b_cover_p", items=[
                        Item(text="清单账本", note="主行 + 副行 + 右侧标签", tag="LEDGER"),
                        Item(text="步骤流程", note="有序步骤，强调先后顺序", tag="FLOW"),
                        Item(text="矩阵 Bento", note="多格数据点并置", tag="BENTO"),
                        Item(text="时间线", note="按时间序并列的锚点", tag="TIME"),
                    ]),
                ],
            ),
            # 2. 清单账本
            CardPage(
                id="p_ledger", role="body", layout_id="list_ledger",
                blocks=[
                    Heading(id="b_led_h", text="这套 DSL 提供了什么"),
                    ListBlock(id="b_led_l", items=[
                        Item(text="11 个 Block 组件", note="heading / text / list / steps / compare / image / cta / bento / stat / timeline / quote", tag="BLOCK"),
                        Item(text="13 个版式", note="每个版式声明必需与可选组件", tag="LAYOUT"),
                        Item(text="9 套主题", note="风格即决策：字体族 + 字重 + 配色 + 版式性格", tag="THEME"),
                        Item(text="像素审计门禁", note="4 带密度自检，欠填/溢出都能报出来", tag="AUDIT"),
                        Item(text="主题 token 化", note="配色编译为 CSS 变量，不再手写样式表", tag="TOKEN"),
                    ]),
                ],
            ),
            # 3. 步骤流程
            CardPage(
                id="p_steps", role="body", layout_id="steps_flow",
                blocks=[
                    Heading(id="b_stp_h", text="从 Deck 到 PNG 的四步"),
                    Steps(id="b_stp_s", items=[
                        Item(text="构造 Deck", note="按版式约束组装 Block"),
                        Item(text="编译 HTML", note="render_page 输出自包含 HTML"),
                        Item(text="Chromium 截图", note="Playwright 真实绘制 1080×1440"),
                        Item(text="审计门禁", note="填满率 / 溢出 / 密度逐页校验"),
                    ]),
                ],
            ),
            # 4. 矩阵 Bento
            CardPage(
                id="p_bento", role="body", layout_id="bento_grid",
                blocks=[
                    Heading(id="b_ben_h", text="关键数字一览"),
                    BentoGrid(id="b_ben_g", cells=[
                        Cell(kicker="组件", big="11", unit="个", note="可组合的 Block 类型", source="schema.py"),
                        Cell(kicker="版式", big="13", unit="套", note="声明式必需/可选约束", source="LAYOUTS"),
                        Cell(kicker="主题", big="9", unit="套", note="字体 + 配色 + 版式性格", source="THEMES"),
                        Cell(kicker="画幅", big="3:4", unit="", note="小红书竖版 1080×1440", source="CANVAS"),
                        Cell(kicker="审计", big="4", unit="带", note="纵向切 4 带查死空白", source="audit.py"),
                        Cell(kicker="上限", big="9", unit="页", note="单帖最多 9 张卡片", source="CardDeck"),
                    ]),
                ],
            ),
            # 5. 时间线
            CardPage(
                id="p_timeline", role="body", layout_id="timeline_flow",
                blocks=[
                    Heading(id="b_tl_h", text="这套架构的演进"),
                    Timeline(id="b_tl_t", items=[
                        TimelineItem(date="2026-08", text="前端 templates.ts", note="18 个 PageType 硬编码枚举"),
                        TimelineItem(date="2026-09", text="后端 DSL 立项", note="参考 Easel card-design 设计系统"),
                        TimelineItem(date="2026-10", text="schema / renderer / audit 落地", note="Block 联合 + 版式约束 + 门禁"),
                        TimelineItem(date="待办", text="前端接入", note="弃用枚举，消费 /cards 渲染结果"),
                    ]),
                ],
            ),
            # 6. 金句（必须补三锚点：kicker + author + 发丝线）
            CardPage(
                id="p_quote", role="body", layout_id="quote_callout",
                blocks=[
                    Quote(
                        id="b_q",
                        text="模板应该是指令，不是代码分支。",
                        author="— 从 Easel 抄来的最重要一条",
                        kicker="ARCHITECTURE",
                    ),
                ],
            ),
            # 7. 收尾 CTA（挂一组回顾要点避免只有一句"关注我"）
            CardPage(
                id="p_end", role="ending", layout_id="end_cta",
                blocks=[
                    Heading(id="b_end_h", text="下一步"),
                    Cta(id="b_end_c", text="把前端编辑器接到这套 DSL 上"),
                    ListBlock(id="b_end_l", items=[
                        Item(text="补齐缺失 Block", note="kicker / footer / qa / code / icon_grid", tag="TODO-1"),
                        Item(text="放开组合约束", note="LAYOUTS 改配置化 allowed blocks", tag="TODO-2"),
                        Item(text="恢复画布预览", note="ImageWorkspace 当前标着「已移除」", tag="TODO-3"),
                        Item(text="前端消费 HTML", note="/cards/preview 直出，弃用 templates.ts 枚举", tag="TODO-4"),
                        Item(text="接入真实出图", note="render_png_pages 走 Playwright 截 chromium", tag="TODO-5"),
                    ]),
                ],
            ),
        ],
    )


async def shoot(deck: CardDeck, out_dir: Path) -> None:
    from playwright.async_api import async_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=str(BROWSER) if BROWSER.is_file() else None,
            headless=True,
        )
        try:
            ctx = await browser.new_context(
                viewport={"width": deck.width, "height": deck.height},
                device_scale_factor=1,
            )
            page = await ctx.new_page()
            for i, card in enumerate(deck.pages):
                html = render_page(deck, card, i)
                await page.set_content(html, wait_until="load", timeout=15000)
                overflow = await page.locator("article").evaluate(
                    "el => el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2"
                )
                png = await page.locator("article").screenshot(type="png", timeout=15000)
                path = out_dir / f"{i + 1:02d}_{card.layout_id}.png"
                path.write_bytes(png)
                report = audit_page(deck, card)
                passed = report.get("pass")
                fill = report.get("fill", 0)
                bands = "".join("█" if b else "░" for b in report.get("bands", []))
                problems = report.get("problems") or []
                flag = "PASS" if passed else "FAIL"
                print(f"[{i + 1}/{len(deck.pages)}] {card.layout_id:<20} "
                      f"溢出={overflow!s:<5} {flag} 填充={fill:.0%} 4带={bands} "
                      f"{('问题:' + ';'.join(map(str, problems))) if problems else ''} "
                      f"-> {path.name}")
        finally:
            await browser.close()


def main() -> None:
    deck = build_deck()
    print(f"Deck 合法：{len(deck.pages)} 页，主题={deck.theme_id}")
    print(f"输出目录：{OUT_DIR}\n")
    asyncio.run(shoot(deck, OUT_DIR))
    print(f"\n完成，共 {len(deck.pages)} 张 -> {OUT_DIR}")


if __name__ == "__main__":
    main()
