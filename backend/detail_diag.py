"""测试能否通过 Spider 的 session 访问笔记详情页。"""
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
logger = logging.getLogger("detail_diag")

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

    test_note_ids = [
        "6aa73cde000000002601ee1b",
        "6aa66555000000002a0243d1",
    ]

    async with manager:
        for note_id in test_note_ids:
            detail_url = f"https://www.xiaohongshu.com/explore/{note_id}"
            logger.info(f"Fetching detail: {detail_url}")

            try:
                response = await manager.fetch(
                    Request(url=detail_url, selector_config={"adaptive": True})
                )
            except Exception as e:
                logger.error(f"Failed to fetch {detail_url}: {e}")
                continue

            is_login = spider._is_login_page(response)
            logger.info(f"  Is login page: {is_login}")

            state = spider._extract_initial_state(response)
            if not state:
                logger.warning(f"  No __INITIAL_STATE__ found")
                continue

            detail_data = spider._extract_note_detail_from_initial_state(response, note_id)
            if detail_data:
                logger.info(f"  Detail extracted successfully!")
                logger.info(f"  title: {detail_data.get('title', '')[:60]}")
                logger.info(f"  content_text: {detail_data.get('content_text', '')[:100]}")
                logger.info(f"  likes: {detail_data.get('likes')}")
                logger.info(f"  collects: {detail_data.get('collects')}")
                logger.info(f"  comments: {detail_data.get('comments')}")
                logger.info(f"  image_urls: {len(detail_data.get('image_urls', []))} images")
                logger.info(f"  tags: {detail_data.get('tags')}")
                logger.info(f"  video_url: {detail_data.get('video_url', '')[:80]}")
            else:
                logger.warning(f"  No detail data from __INITIAL_STATE__")

            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())