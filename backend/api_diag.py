"""测试小红书 Web API 获取笔记详情。"""
import asyncio
import json
import logging
import sys
import re
import time
import hashlib
from pathlib import Path
from urllib.parse import urlencode

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("api_diag")

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))


async def main():
    from app.platform_spider.xhs_spider import XhsSpider
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    from scrapling.spiders.request import Request
    from scrapling.spiders.session import SessionManager

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

    test_note_id = "6aa73cde000000002601ee1b"

    async with manager:
        session = manager.get_default()
        page = await session._get_page()

        logger.info("Testing: page.evaluate to fetch note detail via XHR...")

        js_code = """
        async () => {
            const noteId = arguments[0];
            try {
                const resp = await fetch('/api/sns/web/v1/feed', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        source_note_id: noteId,
                        image_formats: ['jpg', 'webp', 'avif'],
                        extra: { need_body_topic: 1 }
                    }),
                    credentials: 'include'
                });
                const data = await resp.json();
                return { status: resp.status, data: data };
            } catch (e) {
                return { error: e.message };
            }
        }
        """

        try:
            result = await page.evaluate(js_code, test_note_id)
            logger.info(f"API response: {json.dumps(result, ensure_ascii=False)[:2000]}")

            if result.get("status") == 200 and result.get("data"):
                api_data = result["data"]
                items = api_data.get("data", {}).get("items", [])
                if items:
                    note_item = items[0]
                    note_card = note_item.get("note_card", {})
                    logger.info(f"  title: {note_card.get('title', '')[:60]}")
                    logger.info(f"  desc: {note_card.get('desc', '')[:100]}")
                    interact = note_card.get("interact_info", {})
                    logger.info(f"  likes: {interact.get('liked_count')}")
                    logger.info(f"  collects: {interact.get('collected_count')}")
                    logger.info(f"  comments: {interact.get('comment_count')}")
                    logger.info(f"  share_count: {interact.get('share_count')}")
                    image_list = note_card.get("image_list", [])
                    logger.info(f"  image_list: {len(image_list)} images")
                    tag_list = note_card.get("tag_list", [])
                    logger.info(f"  tags: {[t.get('name', '') for t in tag_list if isinstance(t, dict)]}")
                    video = note_card.get("video", {})
                    logger.info(f"  has_video: {bool(video)}")
        except Exception as e:
            logger.error(f"page.evaluate failed: {e}", exc_info=True)

        logger.info("\nTesting: page.evaluate to get note detail from page navigation...")

        try:
            await page.goto(f"https://www.xiaohongshu.com/explore/{test_note_id}", wait_until="networkidle", timeout=15000)
            await asyncio.sleep(2)

            current_url = page.url
            logger.info(f"Current URL: {current_url}")

            state_js = """
            () => {
                const state = window.__INITIAL_STATE__;
                if (!state) return null;
                const detailMap = state.noteDetailMap || (state.note && state.note.noteDetailMap) || {};
                const keys = Object.keys(detailMap);
                if (keys.length === 0) return { error: 'no noteDetailMap' };
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
            """

            detail = await page.evaluate(state_js)
            logger.info(f"Detail from __INITIAL_STATE__: {json.dumps(detail, ensure_ascii=False)}")
        except Exception as e:
            logger.error(f"Page navigation failed: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())