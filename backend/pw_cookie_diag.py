"""测试通过 Playwright + context.add_cookies 方式访问小红书，获取笔记详情。"""
import asyncio
import json
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("pw_cookie_diag")

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))


async def main():
    from playwright.async_api import async_playwright

    storage_path = BACKEND_DIR / "app" / "storage_states" / "xiaohongshu.json"
    state = json.loads(storage_path.read_text("utf-8"))

    raw_cookies = state.get("cookies", [])
    cookie_list = []
    for c in raw_cookies:
        sc = {"name": c.get("name", ""), "value": c.get("value", "")}
        for key in ("domain", "path", "url", "expires", "httpOnly", "secure", "sameSite"):
            if c.get(key) is not None:
                sc[key] = c[key]
        if sc.get("expires", 0) < 0:
            del sc["expires"]
        if not sc.get("domain"):
            continue
        sc.pop("url", None)
        if not sc.get("path"):
            sc["path"] = "/"
        cookie_list.append(sc)

    logger.info(f"Loaded {len(cookie_list)} cookies")

    test_note_ids = [
        "6aa73cde000000002601ee1b",
        "6aa66555000000002a0243d1",
        "6aa4c581000000002603a0a4",
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        page = await context.new_page()

        logger.info("Step 1: 先访问小红书首页建立context...")
        await page.goto("https://www.xiaohongshu.com", wait_until="domcontentloaded", timeout=15000)

        logger.info("Step 2: 注入cookies...")
        await context.add_cookies(cookie_list)

        logger.info("Step 3: 访问用户主页...")
        await page.goto("https://www.xiaohongshu.com/user/profile/5b61cb9ee8ac2b6454ba7b71",
                       wait_until="networkidle", timeout=20000)
        await asyncio.sleep(2)

        logged_in = await page.evaluate("() => window.__INITIAL_STATE__?.user?.loggedIn")
        logger.info(f"  loggedIn: {logged_in}")

        if not logged_in:
            print("ERROR: 未登录，cookies可能已过期")
            await browser.close()
            return

        logger.info("\nStep 4: 测试 feed API 获取笔记详情...")
        for note_id in test_note_ids:
            logger.info(f"\n  Testing note: {note_id}")

            api_result = await page.evaluate("""
                async (noteId) => {
                    try {
                        const resp = await fetch('/api/sns/web/v1/feed', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                source_note_id: noteId,
                                image_formats: ['jpg', 'webp', 'avif'],
                                extra: { need_body_topic: 1 }
                            }),
                            credentials: 'include'
                        });
                        const data = await resp.json();
                        if (!data.success || !data.data || !data.data.items) {
                            return { error: 'API failed', success: data.success, code: data.code, msg: data.msg };
                        }
                        const item = data.data.items[0];
                        const card = item.note_card || {};
                        const interact = card.interact_info || {};
                        const images = card.image_list || [];
                        const tags = card.tag_list || [];
                        return {
                            title: card.title || card.display_title,
                            desc: card.desc ? card.desc.substring(0, 200) : '',
                            likes: interact.liked_count,
                            collects: interact.collected_count,
                            comments: interact.comment_count,
                            shares: interact.share_count,
                            imageCount: images.length,
                            tagNames: tags.map(t => t.name || t.id).filter(Boolean),
                            hasVideo: !!card.video,
                            type: card.type,
                        };
                    } catch (e) {
                        return { error: e.message };
                    }
                }
            """, note_id)
            logger.info(f"  API result: {json.dumps(api_result, ensure_ascii=False)[:500]}")

            await asyncio.sleep(2)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())