# -*- coding: utf-8 -*-
"""探测小红书搜索页 DOM 结构，确认 comments / fans 是否可提取。

直接用 HTTP 调 QR Worker：
1. 从 DB 拿最新登录的 cookies
2. 调 /session/create 创建 work session
3. 调 /search 导航到搜索页
4. 调 /debug_eval dump 笔记卡片 DOM
"""
import json
import os
import sys
import urllib.request
from urllib.parse import quote

# 加载环境变量
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
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def get_cookies_from_db() -> list[dict]:
    """从数据库拿最新的小红书登录 cookies"""
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
            # 拿最新的有效账号
            r = await c.execute(text(
                "SELECT cookies FROM xhs_accounts WHERE cookies IS NOT NULL AND cookies != '' "
                "ORDER BY updated_at DESC LIMIT 1"
            ))
            row = r.fetchone()
            if not row:
                return []
            cookies_str = row[0]
            try:
                cookies = json.loads(cookies_str)
                return cookies
            except Exception:
                return []
        await eng.dispose()

    return asyncio.run(fetch())


def main():
    # 1. 拿 cookies
    cookies = get_cookies_from_db()
    if not cookies:
        print("数据库里没有 cookies，无法创建 session")
        return
    print(f"拿到 {len(cookies)} 个 cookies")

    # 2. 创建 work session
    result = post("/session/create", {"cookies": cookies})
    if not result.get("success"):
        print(f"创建 session 失败: {result}")
        return
    session_id = result.get("data", {}).get("session_id", "")
    print(f"session_id: {session_id!r}")

    # 3. 调 /search 导航到搜索页（会等待加载）
    keyword = "AI对程序员的影响"
    print(f"\n搜索: {keyword!r}")
    result = post(f"/search/{session_id}", {"keyword": keyword, "limit": 3})
    if not result.get("success"):
        print(f"搜索失败: {result}")
        return
    search_results = result.get("data", [])
    print(f"搜索返回 {len(search_results)} 条结果")
    print(f"第一条字段: {list(search_results[0].keys()) if search_results else '无'}")

    # 4. 用 /debug_eval dump 第一条笔记卡片的完整 DOM
    print("\n=== 探测 DOM 结构 ===")
    dump_js = """
    () => {
        const items = document.querySelectorAll('[class*=note-item], [class*=search-result-item], section[class*=note]');
        if (items.length === 0) return {error: 'no items found', url: window.location.href};

        const el = items[0];
        // 收集所有子元素的 class + text
        const allChildren = [];
        el.querySelectorAll('*').forEach(child => {
            if (child.className) {
                allChildren.push({
                    tag: child.tagName,
                    class: typeof child.className === 'string' ? child.className : '',
                    text: (child.textContent || '').substring(0, 60)
                });
            }
        });

        return {
            childCount: el.children.length,
            allChildren: allChildren.slice(0, 40),
            outerHTML: el.outerHTML.substring(0, 2000)
        };
    }
    """
    result = post(f"/debug_eval/{session_id}", {"js": dump_js})
    data = result.get("data", {})

    if isinstance(data, dict) and data.get("error"):
        print(f"DOM 探测失败: {data}")
        return

    print(f"子元素数: {data.get('childCount')}")
    print(f"\n--- 所有子元素 class + text ---")
    for item in data.get("allChildren", []):
        print(f"  <{item['tag']} class={item['class']!r}> text={item['text']!r}")

    # 5. 专门找含"评论"/"粉丝"/"赞"/数字的元素
    print(f"\n=== 查找含 关键词的元素 ===")
    keyword_js = """
    () => {
        const items = document.querySelectorAll('[class*=note-item], [class*=search-result-item], section[class*=note]');
        if (items.length === 0) return {error: 'no items'};

        const el = items[0];
        const results = [];

        // 找所有文本含"赞"/"评论"/"粉丝"/"万"/"关注"的元素
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
        let node;
        while (node = walker.nextNode()) {
            const text = node.textContent.trim();
            if (text && (text.includes('赞') || text.includes('评论') || text.includes('粉丝') || text.includes('万') || text.includes('关注') || /^\\d+[kKmM]?$/.test(text))) {
                const parent = node.parentElement;
                results.push({
                    text: text.substring(0, 50),
                    tag: parent.tagName,
                    class: typeof parent.className === 'string' ? parent.className : '',
                    grandClass: parent.parentElement ? (typeof parent.parentElement.className === 'string' ? parent.parentElement.className : '') : ''
                });
            }
        }

        // 还要找所有数字类元素（可能是点赞数/评论数）
        const numEls = el.querySelectorAll('[class*=count], [class*=like], [class*=comment], [class*=num], [class*=interact], [class*=engagement]');
        for (const numEl of numEls) {
            results.push({
                text: (numEl.textContent || '').trim().substring(0, 50),
                tag: numEl.tagName,
                class: typeof numEl.className === 'string' ? numEl.className : '',
                note: 'matched_by_class'
            });
        }

        return {found: results, total: results.length};
    }
    """
    result = post(f"/debug_eval/{session_id}", {"js": keyword_js})
    data = result.get("data", {})

    print(f"找到 {data.get('total', 0)} 个候选元素:")
    for i, item in enumerate(data.get("found", []), 1):
        print(f"  [{i}] text={item.get('text')!r} tag={item.get('tag')} class={item.get('class')!r}")

    # 6. 探测作者区域：看作者名旁边有没有粉丝数
    print(f"\n=== 探测作者区域 ===")
    author_js = """
    () => {
        const items = document.querySelectorAll('[class*=note-item], [class*=search-result-item], section[class*=note]');
        if (items.length === 0) return {error: 'no items'};

        const el = items[0];
        // 找作者相关的元素
        const authorEls = el.querySelectorAll('[class*=author], [class*=name], [class*=user], [class*=nickname]');
        const authorInfo = [];
        for (const ae of authorEls) {
            authorInfo.push({
                tag: ae.tagName,
                class: typeof ae.className === 'string' ? ae.className : '',
                text: (ae.textContent || '').trim().substring(0, 80),
                html: ae.outerHTML.substring(0, 300)
            });
        }

        // 还要看整个卡片的 outerHTML 里有没有"粉丝"/"万粉"等字样
        const fullHTML = el.outerHTML;
        const hasFans = fullHTML.includes('粉丝') || fullHTML.includes('万粉') || fullHTML.includes('关注');

        return {
            authorEls: authorInfo,
            hasFansKeyword: hasFans,
            fullHTMLLength: fullHTML.length
        };
    }
    """
    result = post(f"/debug_eval/{session_id}", {"js": author_js})
    data = result.get("data", {})

    print(f"HTML 含'粉丝/万粉/关注'关键词: {data.get('hasFansKeyword')}")
    print(f"作者相关元素:")
    for i, item in enumerate(data.get("authorEls", []), 1):
        print(f"  [{i}] <{item['tag']} class={item['class']!r}>")
        print(f"       text={item['text']!r}")
        print(f"       html={item['html']!r}")

    # 关闭 session
    try:
        req = urllib.request.Request(f"{WORKER}/session/{session_id}", method="DELETE")
        urllib.request.urlopen(req, timeout=5)
        print(f"\n已关闭 session {session_id}")
    except Exception:
        pass


if __name__ == "__main__":
    main()
