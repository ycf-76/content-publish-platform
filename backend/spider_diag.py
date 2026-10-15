"""诊断脚本：直接测试 XhsSpider 在线程中运行，检查数据提取结果。"""
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("spider_diag")

BACKEND_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))


async def get_account_info():
    """从数据库获取小红书账号信息。"""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    engine = create_async_engine(
        "mysql+aiomysql://ycf:ycf94946@127.0.0.1:3306/xhs_agent?charset=utf8mb4"
    )
    async with engine.connect() as conn:
        result = await conn.execute(text(
            "SELECT id, platform_uid, cookies_json FROM platform_accounts "
            "WHERE platform='xiaohongshu' LIMIT 1"
        ))
        row = result.fetchone()
    await engine.dispose()
    if not row:
        return None
    return {"id": row[0], "platform_uid": row[1], "cookies_json": row[2]}


def run_spider_directly(platform_uid: str, cookies: dict, user_id: str):
    """直接在线程中运行 Spider.start()，返回抓取结果。"""
    from app.platform_spider.xhs_spider import XhsSpider

    spider = XhsSpider(
        user_id=user_id,
        platform_uid=platform_uid,
        cookies=cookies,
    )

    async def _noop_on_scraped_item(item: dict) -> dict:
        return item

    async def _noop_on_close() -> None:
        pass

    spider.on_scraped_item = _noop_on_scraped_item
    spider.on_close = _noop_on_close

    logger.info(f"Starting XhsSpider.start() with uid={platform_uid}")
    start_time = time.time()

    try:
        result = spider.start()
        elapsed = time.time() - start_time
        logger.info(f"Spider.start() returned in {elapsed:.1f}s")
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"Spider.start() failed after {elapsed:.1f}s: {e}", exc_info=True)
        return []

    items = []
    if hasattr(result, "items"):
        items = list(result.items)
    elif hasattr(result, "__iter__"):
        try:
            items = list(result)
        except Exception as e:
            logger.error(f"Failed to iterate result: {e}")
            return []

    logger.info(f"Spider returned {len(items)} items")

    serializable = []
    for i, item in enumerate(items):
        d = {}
        for k, v in item.items():
            try:
                json.dumps(v)
                d[k] = v
            except Exception:
                d[k] = str(v)
        serializable.append(d)
        if i < 3:
            logger.info(f"  Item {i}: note_id={d.get('note_id')}, title={d.get('title', '')[:40]}, "
                       f"likes={d.get('likes')}, collects={d.get('collects')}, "
                       f"has_content={bool(d.get('content_text'))}, "
                       f"cover_img={bool(d.get('cover_img_url'))}, "
                       f"image_urls_count={len(d.get('image_urls', []))}")

    return serializable


async def main():
    print("=" * 60)
    print("Step 1: 获取账号信息")
    print("=" * 60)
    account = await get_account_info()
    if not account:
        print("ERROR: 未找到小红书账号，请先扫码登录")
        return

    platform_uid = account["platform_uid"]
    cookies = account["cookies_json"] or {}
    user_id = "test_diag"

    print(f"  platform_uid: {platform_uid}")
    print(f"  cookies keys: {list(cookies.keys())[:10] if isinstance(cookies, dict) else type(cookies)}")

    storage_path = BACKEND_DIR / "storage_states" / "xiaohongshu.json"
    print(f"  storage_state exists: {storage_path.exists()}")
    if storage_path.exists():
        try:
            state = json.loads(storage_path.read_text(encoding="utf-8"))
            cookie_count = len(state.get("cookies", []))
            print(f"  storage_state cookies: {cookie_count}")
        except Exception as e:
            print(f"  storage_state parse error: {e}")

    print()
    print("=" * 60)
    print("Step 2: 在线程中运行 Spider")
    print("=" * 60)

    try:
        items = await asyncio.wait_for(
            asyncio.get_event_loop().run_in_executor(
                None,
                run_spider_directly,
                platform_uid, cookies, user_id,
            ),
            timeout=180,
        )
    except asyncio.TimeoutError:
        print("ERROR: Spider 运行超时（180秒）")
        return
    except Exception as e:
        print(f"ERROR: Spider 运行失败: {e}")
        return

    print()
    print("=" * 60)
    print(f"Step 3: 分析结果（共 {len(items)} 条）")
    print("=" * 60)

    if not items:
        print("WARNING: Spider 未返回任何数据！")
        return

    has_title = sum(1 for i in items if i.get("title"))
    has_cover = sum(1 for i in items if i.get("cover_img_url"))
    has_content = sum(1 for i in items if i.get("content_text"))
    has_likes = sum(1 for i in items if i.get("likes", 0) > 0)
    has_collects = sum(1 for i in items if i.get("collects", 0) > 0)
    has_images = sum(1 for i in items if i.get("image_urls"))

    print(f"  有标题: {has_title}/{len(items)}")
    print(f"  有封面: {has_cover}/{len(items)}")
    print(f"  有正文: {has_content}/{len(items)}")
    print(f"  有点赞: {has_likes}/{len(items)}")
    print(f"  有收藏: {has_collects}/{len(items)}")
    print(f"  有图片列表: {has_images}/{len(items)}")

    print()
    print("前3条详细数据:")
    for i, item in enumerate(items[:3]):
        print(f"\n  --- Item {i} ---")
        print(f"  note_id: {item.get('note_id')}")
        print(f"  title: {item.get('title', '')[:60]}")
        print(f"  content_text: {item.get('content_text', '')[:100] if item.get('content_text') else '(empty)'}")
        print(f"  cover_img_url: {item.get('cover_img_url', '')[:80]}")
        print(f"  image_urls: {len(item.get('image_urls', []))} images")
        print(f"  likes: {item.get('likes')}")
        print(f"  collects: {item.get('collects')}")
        print(f"  comments: {item.get('comments')}")
        print(f"  tags: {item.get('tags')}")


if __name__ == "__main__":
    asyncio.run(main())