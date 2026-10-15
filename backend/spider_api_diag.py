"""测试在 Spider 的浏览器上下文中通过 page.evaluate 获取笔记详情。"""
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
logger = logging.getLogger("spider_api_diag")

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))


async def main():
    from app.platform_spider.xhs_spider import XhsSpider
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(
        "mysql+aiomysql://ycf:ycf94946@127.0.0.1:3306/xhs_agent?charset=utf8mb4"
    )
    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT platform_uid, cookies_json FROM platform_accounts "
            "WHERE platform='xiaohongshu' LIMIT 1"
        ))
        row = result.fetchone()
    await engine.dispose()
    if not row:
        print("ERROR: 未找到小红书账号")
        return

    platform_uid = row[0]
    cookies = row[1] or {}

    test_note_ids = [
        "6aa73cde000000002601ee1b",
        "6aa66555000000002a0243d1",
    ]

    from scrapling.spiders.request import Request
    from scrapling.spiders.session import SessionManager

    spider = XhsSpider(
        user_id="diag",
        platform_uid=platform_uid,
        cookies=cookies,
    )

    async def _noop_on_scraped_item(item: dict) -> dict:
        return item
    async def _noop_on_close() -> None:
        pass
    spider.on_scraped_item = _noop_on_scraped_item
    spider.on_close = _noop_on_close

    manager = SessionManager()
    spider.configure_sessions(manager)

    async with manager:
        logger.info("Step 1: 访问主页...")
        home_url = f"https://www.xiaohongshu.com/user/profile/{platform_uid}"
        response = await manager.fetch(Request(url=home_url, selector_config={"adaptive": True}))

        is_login = spider._is_login_page(response)
        logger.info(f"  Is login page: {is_login}")

        state = spider._extract_initial_state(response)
        if state:
            logged_in = state.get("user", {}).get("loggedIn")
            logger.info(f"  loggedIn: {logged_in}")

        logger.info("\nStep 2: 尝试通过 page.evaluate 调用 feed API...")

        try:
            stealthy_session = manager._sessions.get("stealthy")
            if stealthy_session and hasattr(stealthy_session, '_page') and stealthy_session._page:
                page = stealthy_session._page
            elif stealthy_session and hasattr(stealthy_session, '_browser_context'):
                page = await stealthy_session._browser_context.new_page()
                await page.goto(home_url, wait_until="networkidle", timeout=15000)
            else:
                logger.error("Cannot access page object from session")
                return

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

        except Exception as e:
            logger.error(f"page.evaluate failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())