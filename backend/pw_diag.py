"""测试通过 Playwright 直接访问小红书，使用 page.evaluate 获取笔记详情。"""
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
logger = logging.getLogger("pw_diag")

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))


async def main():
    from playwright.async_api import async_playwright

    storage_path = BACKEND_DIR / "app" / "storage_states" / "xiaohongshu.json"
    if not storage_path.exists():
        print("ERROR: storageState file not found")
        return

    test_note_id = "6aa73cde000000002601ee1b"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=str(storage_path))
        page = await context.new_page()

        logger.info("Step 1: 先访问主页确保cookies生效...")
        await page.goto("https://www.xiaohongshu.com/user/profile/5b61cb9ee8ac2b6454ba7b71",
                       wait_until="networkidle", timeout=20000)
        await asyncio.sleep(2)

        logged_in = await page.evaluate("() => window.__INITIAL_STATE__?.user?.loggedIn")
        logger.info(f"  loggedIn: {logged_in}")

        if not logged_in:
            print("ERROR: 未登录，cookies已过期")
            await browser.close()
            return

        logger.info("\nStep 2: 测试 /api/sns/web/v1/feed API...")
        try:
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
                        return { status: resp.status, success: data.success, code: data.code, msg: data.msg };
                    } catch (e) {
                        return { error: e.message };
                    }
                }
            """, test_note_id)
            logger.info(f"  API result: {json.dumps(api_result, ensure_ascii=False)}")
        except Exception as e:
            logger.error(f"  API test failed: {e}")

        logger.info("\nStep 3: 通过 page.goto 访问详情页...")
        try:
            response = await page.goto(f"https://www.xiaohongshu.com/explore/{test_note_id}",
                                       wait_until="networkidle", timeout=20000)
            logger.info(f"  Response status: {response.status if response else 'none'}")
            logger.info(f"  Current URL: {page.url}")

            detail = await page.evaluate("""
                () => {
                    const state = window.__INITIAL_STATE__;
                    if (!state) return { error: 'no __INITIAL_STATE__' };
                    const detailMap = state.noteDetailMap || (state.note && state.note.noteDetailMap) || {};
                    const keys = Object.keys(detailMap);
                    if (keys.length === 0) return { error: 'no noteDetailMap', stateKeys: Object.keys(state) };
                    const key = keys[0];
                    const noteObj = detailMap[key];
                    const note = noteObj.note || noteObj;
                    return {
                        noteId: note.id,
                        title: note.title,
                        desc: note.desc ? note.desc.substring(0, 200) : '',
                        likes: note.interactInfo ? note.interactInfo.likedCount : 0,
                        collects: note.interactInfo ? note.interactInfo.collectedCount : 0,
                        comments: note.interactInfo ? note.interactInfo.commentCount : 0,
                        shares: note.interactInfo ? note.interactInfo.shareCount : 0,
                        imageCount: note.imageList ? note.imageList.length : 0,
                        tagCount: note.tagList ? note.tagList.length : 0,
                        hasVideo: !!note.video,
                    };
                }
            """)
            logger.info(f"  Detail: {json.dumps(detail, ensure_ascii=False)}")
        except Exception as e:
            logger.error(f"  Detail page navigation failed: {e}")

        logger.info("\nStep 4: 测试在主页上下文中通过 JS 获取笔记详情...")
        try:
            await page.goto("https://www.xiaohongshu.com/user/profile/5b61cb9ee8ac2b6454ba7b71",
                           wait_until="networkidle", timeout=20000)
            await asyncio.sleep(2)

            detail_via_xhr = await page.evaluate("""
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
                            return { error: 'API failed', code: data.code, msg: data.msg };
                        }
                        const item = data.data.items[0];
                        const card = item.note_card || {};
                        const interact = card.interact_info || {};
                        return {
                            title: card.title || card.display_title,
                            desc: card.desc ? card.desc.substring(0, 200) : '',
                            likes: interact.liked_count,
                            collects: interact.collected_count,
                            comments: interact.comment_count,
                            shares: interact.share_count,
                            imageCount: card.image_list ? card.image_list.length : 0,
                            tagCount: card.tag_list ? card.tag_list.length : 0,
                            hasVideo: !!card.video,
                            type: card.type,
                        };
                    } catch (e) {
                        return { error: e.message };
                    }
                }
            """, test_note_id)
            logger.info(f"  XHR Detail: {json.dumps(detail_via_xhr, ensure_ascii=False)}")
        except Exception as e:
            logger.error(f"  XHR test failed: {e}")

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())