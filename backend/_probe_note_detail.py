# -*- coding: utf-8 -*-
"""探测 /note_detail 返回的字段结构。

通过 QR Worker 的 /search 拿 note_id，再调 /note_detail 看返回的完整字段。
"""
import json
import os
import sys
import urllib.request
import time
from dotenv import load_dotenv
load_dotenv()

WORKER = "http://127.0.0.1:9010"


def post(path: str, body: dict) -> dict:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{WORKER}{path}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def get_cookies_from_db() -> list[dict]:
    import asyncio
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text

    url = os.getenv("DATABASE_URL", "")
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+aiomysql://", 1)
    elif url.startswith("mysql+pymysql://"):
        url = url.replace("mysql+pymysql://", "mysql+aiomysql://", 1)

    async def fetch():
        eng = create_async_engine(url, pool_pre_ping=True)
        async with eng.connect() as c:
            r = await c.execute(text(
                "SELECT session_data_encrypted FROM xhs_accounts "
                "WHERE session_data_encrypted IS NOT NULL "
                "ORDER BY updated_at DESC LIMIT 1"
            ))
            row = r.fetchone()
            if not row:
                return []
            encrypted = row[0]
            # 解密：session_data_encrypted 存的是 {"cookies": [...]} 的 AES-GCM 密文
            from app.crypto.token_crypto import TokenCrypto
            try:
                session_data = TokenCrypto().decrypt_dict(encrypted)
                cookies = (
                    session_data.get("cookies", [])
                    if isinstance(session_data, dict)
                    else session_data
                )
                return cookies
            except Exception as e:
                print(f"解密失败: {e}")
                return []
        await eng.dispose()

    return asyncio.run(fetch())


def main():
    # 1. 拿 cookies
    cookies = get_cookies_from_db()
    if not cookies:
        print("数据库里没有 cookies")
        return
    print(f"拿到 {len(cookies)} 个 cookies")

    # 2. 创建 work session
    result = post("/session/create", {"cookies": cookies})
    if not result.get("success"):
        print(f"创建 session 失败: {result}")
        return
    session_id = result.get("data", {}).get("session_id", "")
    print(f"session_id: {session_id}")

    # 3. 搜索拿 note_id
    keyword = "AI对程序员的影响"
    print(f"\n搜索: {keyword!r}")
    result = post(f"/search/{session_id}", {"keyword": keyword, "limit": 10})
    if not result.get("success"):
        print(f"搜索失败: {result}")
        return
    search_results = result.get("data", [])
    print(f"搜索返回 {len(search_results)} 条")

    if not search_results:
        print("无搜索结果，无法测试 note_detail")
        return

    # 取所有 note_id（去重 + 过滤空）
    note_ids = [r.get("note_id") for r in search_results if r.get("note_id")]
    print(f"note_ids ({len(note_ids)}): {note_ids}")

    # 4. 依次调 /note_detail，跳过"暂时无法浏览"，找到第一个正常的 dump 完整字段
    valid_detail = None
    for i, note_id in enumerate(note_ids, 1):
        print(f"\n=== 笔记 {i}/{len(note_ids)}: {note_id} ===")
        result = post(f"/note_detail/{session_id}", {"note_id": note_id})
        if not result.get("success"):
            print(f"获取详情失败: {result}")
            continue

        detail = result.get("data", {})
        title = detail.get("title", "")
        debug = detail.get("_debug", {})
        print(f"  _debug.url: {debug.get('url', 'N/A')}")
        print(f"  _debug.title_tag: {debug.get('title_tag', 'N/A')!r}")
        print(f"  _debug.has_next_data: {debug.get('has_next_data', 'N/A')}")
        print(f"  _debug.next_data_len: {debug.get('next_data_len', 0)}")
        print(f"  _debug.body_text_head: {debug.get('body_text_head', '')[:120]!r}")
        print(f"  title: {title!r}")

        if "暂时无法浏览" in title or "无法浏览" in title:
            print(f"  -> 笔记被限流/删除，跳过")
        elif not title:
            print(f"  -> 标题为空，跳过")
        else:
            print(f"  -> 命中正常笔记！")
            valid_detail = detail
            break

        # 间隔 2 秒防风控
        if i < len(note_ids):
            time.sleep(2)

    # 5. 输出总结
    print("\n" + "=" * 60)
    if valid_detail:
        print(f"✓ 找到正常笔记详情，字段列表: {list(valid_detail.keys())}")
        print(f"\n完整 JSON (前 4000 字符):")
        print(json.dumps(valid_detail, ensure_ascii=False, indent=2)[:4000])

        print(f"\n--- 关键字段检查 ---")
        print(f"title: {valid_detail.get('title', 'N/A')!r}")
        print(f"desc: {valid_detail.get('desc', 'N/A')!r}")
        print(f"content: {str(valid_detail.get('content', 'N/A'))[:100]!r}")
        print(f"likes: {valid_detail.get('likes', 'N/A')}")
        print(f"comments: {valid_detail.get('comments', 'N/A')}")
        print(f"author_fans: {valid_detail.get('author_fans', 'N/A')}")
        print(f"interactions: {valid_detail.get('interactions', 'N/A')}")
        print(f"tags: {valid_detail.get('tags', 'N/A')}")
        print(f"images: {len(valid_detail.get('images', []))} 张")
        print(f"time/date: {valid_detail.get('time', valid_detail.get('date', 'N/A'))}")
    else:
        print(f"✗ 所有 {len(note_ids)} 个 note_id 都无法获取正常详情")
        print("  可能原因：1) cookies 失效 2) 风控拦截 3) 搜索结果全是限流笔记")

    # 关闭 session
    try:
        req = urllib.request.Request(f"{WORKER}/session/{session_id}", method="DELETE")
        urllib.request.urlopen(req, timeout=5)
        print(f"\n已关闭 session")
    except Exception:
        pass


if __name__ == "__main__":
    main()
