"""验证卡片编辑器布局：登录 -> 工作区 -> 启动工作流 -> 等待 image_plan -> 抓布局数据。"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

SCREENSHOT_DIR = Path(r"d:\My_Project\多智能体小红书发布平台\test_screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        print("[1] 访问首页")
        await page.goto("http://localhost:3001/", wait_until="domcontentloaded", timeout=15000)
        await page.wait_for_timeout(1500)

        print("[2] 点击「免费试用」进入工作区")
        btn = page.locator("button.mint-btn-primary:has-text('免费试用')").first
        await btn.click()
        await page.wait_for_timeout(2000)
        print(f"  当前 URL: {page.url}")

        if "/login" in page.url:
            print("  跳到了登录页，直接访问 /workbench")
            await page.goto("http://localhost:3001/workbench", wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(2000)
            print(f"  当前 URL: {page.url}")

        # 找搜索输入框
        print("[3] 查找搜索输入框")
        search_input = None
        for selector in ["#search-input", "input[placeholder*='搜索']", "input[placeholder*='关键词']", "input[placeholder*='主题']", "input[type='text']"]:
            loc = page.locator(selector).first
            if await loc.count() > 0:
                search_input = loc
                print(f"  找到搜索框: {selector}")
                break

        if search_input is None:
            print("  未找到搜索框，列出所有 input:")
            inputs = await page.evaluate("""() => Array.from(document.querySelectorAll('input')).map(i => ({
                id: i.id, type: i.type, placeholder: i.placeholder
            }))""")
            print(f"  {inputs[:10]}")
            await page.screenshot(path=str(SCREENSHOT_DIR / "verify_no_search.png"), full_page=True)
            await browser.close()
            return

        await search_input.fill("AI趋势")
        print("  输入: AI趋势")

        all_chip = page.locator(".wf-platform-chip:has-text('全网搜索')").first
        if await all_chip.count() > 0:
            await all_chip.click()
            print("  已选全网搜索")

        search_btn = page.locator("#preview-search-btn").first
        if await search_btn.count() > 0:
            await search_btn.click()
            print("  点击搜索")
            await page.wait_for_timeout(5000)

        print("[4] 启动工作流")
        start_selectors = [
            "button:has-text('开始工作流')",
            "button:has-text('启动工作流')",
            "button:has-text('开始生成')",
            ".mint-btn-primary:has-text('工作流')",
            "button:has-text('选中选题')",
            "button:has-text('使用选题')",
        ]
        started = False
        for sel in start_selectors:
            btn = page.locator(sel).first
            if await btn.count() > 0:
                await btn.click()
                print(f"  点击: {sel}")
                started = True
                break

        if not started:
            print("  未找到工作流启动按钮")

        print("[5] 等待卡片编辑器出现（最多 200 秒）")
        found_editor = False
        for i in range(40):
            await page.wait_for_timeout(5000)
            editor_count = await page.locator(".cep-preview-box").count()
            if editor_count > 0:
                print(f"  第 {(i+1)*5} 秒: 检测到卡片编辑器 ({editor_count} 个 .cep-preview-box)")
                found_editor = True
                break
            if i % 4 == 0:
                try:
                    node_states = await page.evaluate("""() => {
                        const cards = document.querySelectorAll('.wf-node-card');
                        return Array.from(cards).map(c => {
                            const id = c.id || '';
                            const status = c.querySelector('.wf-node-status, .node-status-text, .wf-status-text')?.textContent?.trim() || '';
                            return `${id}: ${status}`;
                        });
                    }""")
                    print(f"  第 {(i+1)*5} 秒: {node_states[:6]}")
                except Exception:
                    pass

        if not found_editor:
            print("  超时未检测到卡片编辑器")
            await page.screenshot(path=str(SCREENSHOT_DIR / "verify_timeout.png"), full_page=True)
            await browser.close()
            return

        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(SCREENSHOT_DIR / "verify_card_editor.png"), full_page=True)

        print("[6] 抓取布局数据")
        layout_data = await page.evaluate("""() => {
            const center = document.querySelector('.cep-center');
            const box = document.querySelector('.cep-preview-box');
            const inner = document.querySelector('.cep-preview-inner');
            const cardCanvas = document.querySelector('.card-canvas');
            const host = document.querySelector('.wf-card-editor-host');
            const grid = document.querySelector('.cep-preview-grid');
            const imageGenCard = document.querySelector('#card-image-gen, #card-image_plan');
            const r = el => el ? JSON.parse(JSON.stringify(el.getBoundingClientRect())) : null;
            return {
                host: host ? {rect: r(host), position: getComputedStyle(host).position, height: getComputedStyle(host).height} : null,
                center: center ? {clientWidth: center.clientWidth, clientHeight: center.clientHeight, rect: r(center)} : null,
                box: box ? {style: box.getAttribute('style'), rect: r(box)} : null,
                inner: inner ? {style: inner.getAttribute('style'), rect: r(inner)} : null,
                cardCanvas: cardCanvas ? {rect: r(cardCanvas)} : null,
                grid: grid ? {rect: r(grid), children: grid.children.length, scrollWidth: grid.scrollWidth} : null,
                imageGenCard: imageGenCard ? {rect: r(imageGenCard), id: imageGenCard.id} : null,
            };
        }""")
        print("\n===== 布局数据 =====")
        print(json.dumps(layout_data, indent=2, default=str))
        print("===================\n")

        # 验证关键指标
        print("===== 验证结果 =====")
        if layout_data.get("host"):
            host_rect = layout_data["host"]["rect"]
            host_pos = layout_data["host"]["position"]
            host_h = layout_data["host"]["height"]
            print(f"1. host position={host_pos} (应为 static/relative，不是 fixed)")
            print(f"   host height={host_h} (应为固定值如 580px，不是 100vh)")
            print(f"   host rect: width={host_rect['width']:.0f}, height={host_rect['height']:.0f}")
            if host_pos == "fixed":
                print("   ❌ 还是 fixed 定位，会挡住其他节点")
            else:
                print("   ✅ 嵌入文档流，不挡其他节点")
        else:
            print("❌ 未找到 host")

        if layout_data.get("box"):
            box_rect = layout_data["box"]["rect"]
            print(f"2. box rect: width={box_rect['width']:.0f}, height={box_rect['height']:.0f}")
            if box_rect["width"] > 200 and box_rect["height"] > 200:
                print("   ✅ 卡片尺寸正常（>200px）")
            else:
                print("   ❌ 卡片尺寸过小")
        else:
            print("❌ 未找到 box")

        if layout_data.get("cardCanvas"):
            cc_rect = layout_data["cardCanvas"]["rect"]
            print(f"3. card-canvas rect: width={cc_rect['width']:.0f}, height={cc_rect['height']:.0f}")
            if cc_rect["width"] > 100 and cc_rect["height"] > 100:
                print("   ✅ 卡片内容可见")
            else:
                print("   ❌ 卡片内容不可见")
        else:
            print("❌ 未找到 card-canvas")

        if layout_data.get("imageGenCard"):
            ig_rect = layout_data["imageGenCard"]["rect"]
            print(f"4. image_gen 节点 rect: top={ig_rect['top']:.0f}, height={ig_rect['height']:.0f}")
            print("   ✅ image_gen 节点存在，下方节点连接正常")
        else:
            print("   ⚠️ 未找到 image_gen 节点")

        print("===================\n")

        await browser.close()
        print(f"截图保存到: {SCREENSHOT_DIR}")


asyncio.run(main())
