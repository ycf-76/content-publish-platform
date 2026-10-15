"""诊断脚本：使用 Spider 的 configure_sessions 方式获取页面，打印 __INITIAL_STATE__ 结构。"""
import asyncio
import json
import logging
import sys
import re
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("state_diag2")

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

    from scrapling.spiders.request import Request
    from scrapling.spiders.session import SessionManager

    manager = SessionManager()
    spider.configure_sessions(manager)

    url = f"https://www.xiaohongshu.com/user/profile/{platform_uid}"
    logger.info(f"Fetching: {url}")

    async with manager:
        response = await manager.fetch(Request(url=url, selector_config={"adaptive": True}))

    logger.info(f"Response fetched")

    is_login = spider._is_login_page(response)
    logger.info(f"Is login page: {is_login}")

    if is_login:
        print("ERROR: 页面被重定向到登录页，cookies已过期！")
        return

    state = spider._extract_initial_state(response)
    if not state:
        print("ERROR: 无法提取 __INITIAL_STATE__")
        return

    user_data = state.get("user", {})
    raw_notes = user_data.get("notes", [])

    print("\n" + "=" * 60)
    print("__INITIAL_STATE__.user 顶级 keys:")
    print("=" * 60)
    for k in sorted(user_data.keys()):
        v = user_data[k]
        if isinstance(v, (list, dict)):
            print(f"  {k}: {type(v).__name__} len={len(v)}")
        else:
            print(f"  {k}: {type(v).__name__} = {str(v)[:80]}")

    print(f"\n  loggedIn: {user_data.get('loggedIn')}")

    flat_notes = []
    if isinstance(raw_notes, list):
        if raw_notes and isinstance(raw_notes[0], list):
            for sub in raw_notes:
                if isinstance(sub, list):
                    flat_notes.extend(sub)
        else:
            flat_notes = raw_notes

    print(f"\n  notes total after flatten: {len(flat_notes)}")

    if flat_notes:
        first = flat_notes[0]
        print(f"\n{'=' * 60}")
        print(f"第1条笔记的所有 keys:")
        print(f"{'=' * 60}")
        if isinstance(first, dict):
            for k in sorted(first.keys()):
                v = first[k]
                if k == "noteCard":
                    print(f"  {k}: dict with keys={sorted(v.keys()) if isinstance(v, dict) else type(v)}")
                    if isinstance(v, dict):
                        for nk in sorted(v.keys()):
                            nv = v[nk]
                            if isinstance(nv, (list, dict)):
                                print(f"    {nk}: {type(nv).__name__} len={len(nv)}")
                            else:
                                val_str = str(nv)[:120]
                                print(f"    {nk}: {val_str}")
                elif isinstance(v, (list, dict)):
                    print(f"  {k}: {type(v).__name__} len={len(v)}")
                else:
                    print(f"  {k}: {str(v)[:120]}")

            print(f"\n{'=' * 60}")
            print(f"第1条笔记完整JSON:")
            print(f"{'=' * 60}")
            print(json.dumps(first, ensure_ascii=False, indent=2)[:3000])

        if len(flat_notes) > 1:
            second = flat_notes[1]
            if isinstance(second, dict):
                card = second.get("noteCard", {})
                interact = card.get("interactInfo", {}) if card else second.get("interactInfo", {})
                print(f"\n{'=' * 60}")
                print(f"第2条笔记 interactInfo:")
                print(f"{'=' * 60}")
                print(json.dumps(interact, ensure_ascii=False, indent=2)[:1000])
                print(f"\n  desc: {card.get('desc', '(none)')[:200] if card else second.get('desc', '(none)')[:200]}")

    note_queries = user_data.get("noteQueries", [])
    print(f"\n{'=' * 60}")
    print(f"noteQueries 结构:")
    print(f"{'=' * 60}")
    print(f"  len: {len(note_queries)}")
    if note_queries:
        for i, nq in enumerate(note_queries):
            if isinstance(nq, dict):
                print(f"  [{i}] keys: {sorted(nq.keys())}")
                cursor = nq.get("cursor", "")
                print(f"      cursor: {cursor}")
            elif isinstance(nq, list):
                print(f"  [{i}] list len={len(nq)}")


if __name__ == "__main__":
    asyncio.run(main())