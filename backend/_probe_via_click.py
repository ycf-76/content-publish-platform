# -*- coding: utf-8 -*-
"""探测"点击进入详情"方案是否可行。

思路：
1. 从 DB 拿 cookies
2. 用 sync_playwright 创建 context，注入 cookies
3. 访问搜索页，搜索关键词
4. 等待搜索结果加载
5. 点击第一个笔记卡片（模拟用户行为）
6. 等待详情页加载
7. 提取详情字段（__NEXT_DATA__ / likes / comments / fans 等）

验证点：
- 点击进入能否绕过 300031 风控
- 详情页 __NEXT_DATA__ 里有没有 likes/comments/author_fans 等字段
"""
import asyncio
import json
import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

load_dotenv()


def get_cookies_from_db() -> list[dict]:
    """从数据库拿解密后的 cookies（Playwright 格式）。"""
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


def cookies_to_playwright_format(cookies: list[dict]) -> list[dict]:
    """把存储格式的 cookies 转成 playwright.add_cookies 需要的格式。"""
    out = []
    for c in cookies:
        # 兼容两种存储格式：{name, value, domain, path} 或 {name, value, domain, path, ...}
        item = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ".xiaohongshu.com"),
            "path": c.get("path", "/"),
        }
        if c.get("expires"):
            item["expires"] = c["expires"]
        if c.get("httpOnly"):
            item["httpOnly"] = True
        if c.get("secure"):
            item["secure"] = True
        if c.get("sameSite"):
            ss = c["sameSite"]
            # playwright 只接受 "Strict" / "Lax" / "None"
            if ss in ("Strict", "Lax", "None"):
                item["sameSite"] = ss
        out.append(item)
    return out


def main():
    cookies = get_cookies_from_db()
    if not cookies:
        print("数据库里没有 cookies")
        return
    print(f"拿到 {len(cookies)} 个 cookies")
    pw_cookies = cookies_to_playwright_format(cookies)
    print(f"转换后 {len(pw_cookies)} 个 playwright cookies")

    keyword = "AI对程序员的影响"
    print(f"\n关键词: {keyword!r}")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--window-size=1280,800",
            ],
        )
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            "Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});"
            "Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en']});"
            "window.chrome = {runtime: {}};"
        )
        # 注入 cookies
        ctx.add_cookies(pw_cookies)
        print("已注入 cookies")

        page = ctx.new_page()

        # 【新增】拦截 XHR 响应，捕获详情页数据接口的返回
        captured_responses = []

        def on_response(response):
            url = response.url
            # 小红书详情页数据接口候选
            if any(k in url for k in ["/api/sns/web/v1/feed", "/api/sns/web/v1/note", "/api/sns/web/v2/note", "note_detail"]):
                try:
                    # 优先用 response.json() 直接解析，避免截断导致 JSON 不完整
                    data = response.json()
                    captured_responses.append({
                        "url": url,
                        "status": response.status,
                        "data": data,
                    })
                except Exception:
                    # fallback：存 text（截断）
                    try:
                        body = response.text()
                        captured_responses.append({
                            "url": url,
                            "status": response.status,
                            "body": body[:8000],
                        })
                    except Exception:
                        pass

        page.on("response", on_response)

        # 1. 访问搜索页
        search_url = f"https://www.xiaohongshu.com/search_result?keyword={keyword}&source=web_explore_feed"
        print(f"\n[1] 访问搜索页: {search_url}")
        page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        print(f"  当前 URL: {page.url}")
        print(f"  page.title: {page.title()!r}")

        # 2. 找到搜索结果卡片
        print("\n[2] 查找搜索结果卡片...")
        card_selector = '[class*=note-item], [class*=search-result-item], section[class*=note]'
        try:
            page.wait_for_selector(card_selector, timeout=10000, state="visible")
        except Exception:
            print(f"  未找到卡片元素，dump body 文本前 300 字:")
            print(f"  {page.inner_text('body')[:300]!r}")
            ctx.close()
            browser.close()
            return

        cards = page.query_selector_all(card_selector)
        print(f"  找到 {len(cards)} 个卡片")

        if not cards:
            print("  无卡片，退出")
            ctx.close()
            browser.close()
            return

        # 3. 点击第一个卡片
        print("\n[3] 点击第一个卡片...")
        first_card = cards[0]
        # 先拿卡片的 href（如果有）
        link = first_card.query_selector("a")
        href = link.get_attribute("href") if link else ""
        print(f"  卡片 href: {href!r}")

        # 滚动到可视区域
        try:
            first_card.scroll_into_view_if_needed()
        except Exception:
            pass
        page.wait_for_timeout(500)

        # 记录点击前的 URL
        url_before = page.url
        print(f"  点击前 URL: {url_before}")

        # 清空搜索阶段捕获的响应，只保留点击后的
        captured_responses.clear()

        # 点击
        try:
            first_card.click(timeout=5000)
        except Exception as e:
            print(f"  点击卡片失败: {e}，尝试点 link")
            if link:
                link.click(timeout=5000)

        # 4. 等待详情页加载
        print("\n[4] 等待详情页加载...")
        # 详情页 URL 通常变为 /explore/{note_id}
        try:
            page.wait_for_url("**/explore/**", timeout=10000)
        except Exception:
            print(f"  URL 未变为 /explore/，当前 URL: {page.url}")
        page.wait_for_timeout(3000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        url_after = page.url
        print(f"  点击后 URL: {url_after}")
        print(f"  page.title: {page.title()!r}")

        # 5. 检查是否被风控（404 / 暂时无法浏览）
        print("\n[5] 检查页面状态...")
        page_state = page.evaluate(
            """() => {
                const bodyText = (document.body?.innerText || '').substring(0, 500);
                const is404 = location.href.includes('/404');
                const isBlocked = bodyText.includes('暂时无法浏览') || bodyText.includes('页面不见了');
                return {
                    url: location.href,
                    is404: is404,
                    isBlocked: isBlocked,
                    body_text_head: bodyText,
                };
            }"""
        )
        print(f"  is404: {page_state['is404']}")
        print(f"  isBlocked: {page_state['isBlocked']}")
        print(f"  body_text_head: {page_state['body_text_head'][:200]!r}")

        if page_state["is404"] or page_state["isBlocked"]:
            print("\n✗ 点击进入也被风控拦截")
            ctx.close()
            browser.close()
            return

        # 6. 提取 __NEXT_DATA__
        print("\n[6] 提取 __NEXT_DATA__...")
        next_data = page.evaluate(
            """() => {
                const nd = document.getElementById('__NEXT_DATA__');
                if (!nd) return null;
                try {
                    return JSON.parse(nd.textContent || '{}');
                } catch(e) {
                    return {error: e.message};
                }
            }"""
        )
        if not next_data:
            print("  __NEXT_DATA__ 不存在")
        else:
            print(f"  __NEXT_DATA__ 解析成功，顶层 keys: {list(next_data.keys())}")
            # 深度查找 note 数据
            note_data = page.evaluate(
                """() => {
                    const nd = document.getElementById('__NEXT_DATA__');
                    if (!nd) return null;
                    const d = JSON.parse(nd.textContent || '{}');
                    const walk = (o, dp, path) => {
                        if (!o || typeof o !== 'object' || dp > 8) return null;
                        if (o.note_id || (o.note && o.note.note_id)) return {data: o, path: path};
                        for (const k of Object.keys(o)) {
                            const r = walk(o[k], dp+1, path + '.' + k);
                            if (r) return r;
                        }
                        return null;
                    };
                    return walk(d, 0, '');
                }"""
            )
            if note_data:
                print(f"\n  ✓ 找到 note 数据，path: {note_data['path']}")
                data = note_data["data"]
                print(f"  note 数据 keys: {list(data.keys())}")
                # 如果有 note 子对象
                if "note" in data and isinstance(data["note"], dict):
                    print(f"  data.note keys: {list(data['note'].keys())}")
                    print(f"\n  data.note 完整 JSON (前 5000 字符):")
                    print(json.dumps(data["note"], ensure_ascii=False, indent=2)[:5000])
                else:
                    print(f"\n  note 数据完整 JSON (前 5000 字符):")
                    print(json.dumps(data, ensure_ascii=False, indent=2)[:5000])

                # 重点字段检查
                note_obj = data.get("note", data)
                print(f"\n  --- 关键字段检查 ---")
                print(f"  note_id: {note_obj.get('note_id', 'N/A')}")
                print(f"  title: {note_obj.get('title', 'N/A')!r}")
                print(f"  desc: {str(note_obj.get('desc', 'N/A'))[:100]!r}")
                print(f"  type: {note_obj.get('type', 'N/A')}")
                print(f"  user keys: {list(note_obj.get('user', {}).keys()) if isinstance(note_obj.get('user'), dict) else 'N/A'}")
                if isinstance(note_obj.get("user"), dict):
                    print(f"  user.fans: {note_obj['user'].get('fans', 'N/A')}")
                    print(f"  user.nickname: {note_obj['user'].get('nickname', 'N/A')}")
                print(f"  interactInfo keys: {list(note_obj.get('interactInfo', {}).keys()) if isinstance(note_obj.get('interactInfo'), dict) else 'N/A'}")
                if isinstance(note_obj.get("interactInfo"), dict):
                    ii = note_obj["interactInfo"]
                    print(f"  interactInfo.liked_count: {ii.get('liked_count', 'N/A')}")
                    print(f"  interactInfo.comment_count: {ii.get('comment_count', 'N/A')}")
                    print(f"  interactInfo.collected_count: {ii.get('collected_count', 'N/A')}")
                    print(f"  interactInfo.share_count: {ii.get('share_count', 'N/A')}")
                    print(f"  interactInfo.view_count: {ii.get('view_count', 'N/A')}")
                print(f"  tags: {note_obj.get('tag_list', note_obj.get('tags', 'N/A'))}")
            else:
                print("  ✗ 未在 __NEXT_DATA__ 中找到 note 数据")

        # 7. DOM 提取（兜底）
        print("\n[7] DOM 提取（兜底）...")
        dom_detail = page.evaluate(
            """() => {
                const titleEl = document.querySelector('h1, [class*=title]');
                const contentEl = document.querySelector('[class*=content], article, [class*=desc]');
                const likeEl = document.querySelector('[class*=like] [class*=count], [class*=like] span');
                const commentEl = document.querySelector('[class*=comment] [class*=count], [class*=chat] span');
                const collectEl = document.querySelector('[class*=collect] [class*=count], [class*=collect] span');
                const authorEl = document.querySelector('[class*=author] [class*=name], [class*=user] [class*=name]');
                const imgs = Array.from(document.querySelectorAll('.carousel img, [class*=image] img, .swiper img'))
                    .map(i => i.getAttribute('src') || '').filter(s => s.startsWith('http'));
                return {
                    title: titleEl ? titleEl.textContent.trim() : '',
                    content: contentEl ? contentEl.textContent.trim().substring(0, 200) : '',
                    likes_text: likeEl ? likeEl.textContent.trim() : '',
                    comments_text: commentEl ? commentEl.textContent.trim() : '',
                    collects_text: collectEl ? collectEl.textContent.trim() : '',
                    author: authorEl ? authorEl.textContent.trim() : '',
                    images: imgs,
                };
            }"""
        )
        print(f"  title: {dom_detail['title']!r}")
        print(f"  content: {dom_detail['content']!r}")
        print(f"  likes_text: {dom_detail['likes_text']!r}")
        print(f"  comments_text: {dom_detail['comments_text']!r}")
        print(f"  collects_text: {dom_detail['collects_text']!r}")
        print(f"  author: {dom_detail['author']!r}")
        print(f"  images: {len(dom_detail['images'])} 张")

        # 【新增】dump 互动栏区域的 HTML 结构，找 likes/comments/fans 的正确 selector
        print("\n[8] dump 详情页互动栏 DOM 结构...")
        interact_html = page.evaluate(
            """() => {
                // 候选：互动栏容器
                const candidates = [
                    ...document.querySelectorAll('[class*=interact], [class*=engage], [class*=bottom]'),
                    ...document.querySelectorAll('[class*=like], [class*=collect], [class*=comment], [class*=chat]'),
                ];
                // 去重
                const seen = new Set();
                const htmls = [];
                for (const el of candidates) {
                    // 找到包含数字的祖先元素（互动按钮的容器）
                    let container = el;
                    for (let i = 0; i < 3; i++) {
                        if (container.parentElement && container.parentElement.querySelectorAll('[class*=like], [class*=count]').length > 0) {
                            container = container.parentElement;
                        } else break;
                    }
                    const key = container.outerHTML.substring(0, 100);
                    if (seen.has(key)) continue;
                    seen.add(key);
                    htmls.push({
                        className: container.className,
                        outerHTML: container.outerHTML.substring(0, 800),
                    });
                    if (htmls.length >= 5) break;
                }
                return htmls;
            }"""
        )
        for i, h in enumerate(interact_html[:5], 1):
            print(f"\n  --- 互动栏候选 {i} ---")
            print(f"  className: {h['className']!r}")
            print(f"  outerHTML:\n{h['outerHTML']}")

        # 【新增】dump 作者信息区域的 HTML，找 fans 的位置
        print("\n[9] dump 作者信息 DOM 结构...")
        author_html = page.evaluate(
            """() => {
                const candidates = document.querySelectorAll('[class*=author], [class*=user-info], [class*=user] [class*=info]');
                const htmls = [];
                for (const el of candidates) {
                    htmls.push({
                        className: el.className,
                        outerHTML: el.outerHTML.substring(0, 800),
                    });
                    if (htmls.length >= 3) break;
                }
                return htmls;
            }"""
        )
        for i, h in enumerate(author_html[:3], 1):
            print(f"\n  --- 作者候选 {i} ---")
            print(f"  className: {h['className']!r}")
            print(f"  outerHTML:\n{h['outerHTML']}")

        # 【新增】dump 详情页所有含数字的文本节点（前 30 个）
        print("\n[10] dump 详情页含数字的文本节点...")
        num_texts = page.evaluate(
            """() => {
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                const out = [];
                let node;
                while (node = walker.nextNode()) {
                    const t = node.textContent.trim();
                    if (t && /\\d/.test(t) && t.length < 30) {
                        const parent = node.parentElement;
                        out.push({
                            text: t,
                            parentClass: parent ? parent.className : '',
                            parentTag: parent ? parent.tagName.toLowerCase() : '',
                        });
                        if (out.length >= 40) break;
                    }
                }
                return out;
            }"""
        )
        for i, t in enumerate(num_texts, 1):
            print(f"  {i:2d}. text={t['text']!r:30s} parent={t['parentTag']}.{t['parentClass'][:50]!r}")

        # 【新增】输出捕获的 XHR 响应（详情页数据接口）
        print(f"\n[11] 捕获的 XHR 响应 ({len(captured_responses)} 个)...")
        for i, r in enumerate(captured_responses, 1):
            print(f"\n  === 响应 {i} ===")
            print(f"  URL: {r['url'][:200]}")
            print(f"  status: {r['status']}")
            data = r.get("data")
            if data is None:
                # fallback：text 版本
                body = r.get("body", "")
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    print(f"  非 JSON，body 前 500 字符:")
                    print(f"  {body[:500]}")
                    continue

            print(f"  顶层 keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")

            # 深度查找 note_card / note 数据
            def find_note_obj(o, path="", depth=0):
                if depth > 8 or not isinstance(o, (dict, list)):
                    return []
                results = []
                if isinstance(o, dict):
                    # note_card 是小红书 feed 接口的 note 数据容器
                    if "note_card" in o or "interactInfo" in o or "note_id" in o:
                        results.append((path, o))
                    for k, v in o.items():
                        results.extend(find_note_obj(v, f"{path}.{k}", depth + 1))
                elif isinstance(o, list):
                    for idx, item in enumerate(o[:5]):
                        results.extend(find_note_obj(item, f"{path}[{idx}]", depth + 1))
                return results

            note_objs = find_note_obj(data)
            if note_objs:
                for path, obj in note_objs[:2]:
                    print(f"\n  ✓ 找到 note 对象 @ {path}")
                    print(f"    keys: {list(obj.keys())}")
                    # note_card 在 items[].note_card 路径下
                    note = obj.get("note_card", obj.get("note", obj))
                    if isinstance(note, dict):
                        print(f"    note_id: {note.get('note_id', 'N/A')}")
                        print(f"    title: {note.get('title', 'N/A')!r}")
                        print(f"    desc: {str(note.get('desc', 'N/A'))[:80]!r}")
                        print(f"    type: {note.get('type', 'N/A')}")
                        user = note.get("user", {})
                        if isinstance(user, dict):
                            print(f"    user keys: {list(user.keys())}")
                            print(f"    user.nickname: {user.get('nickname', 'N/A')}")
                            print(f"    user.fans: {user.get('fans', 'N/A')}")
                            print(f"    user.userid: {user.get('userid', user.get('user_id', 'N/A'))}")
                        ii = note.get("interactInfo", {})
                        if isinstance(ii, dict):
                            print(f"    interactInfo keys: {list(ii.keys())}")
                            print(f"    interactInfo.liked_count: {ii.get('liked_count', 'N/A')}")
                            print(f"    interactInfo.comment_count: {ii.get('comment_count', 'N/A')}")
                            print(f"    interactInfo.collected_count: {ii.get('collected_count', 'N/A')}")
                            print(f"    interactInfo.share_count: {ii.get('share_count', 'N/A')}")
                            print(f"    interactInfo.view_count: {ii.get('view_count', 'N/A')}")
                        print(f"\n    note 完整 JSON (前 4000 字符):")
                        print(f"    {json.dumps(note, ensure_ascii=False, indent=2)[:4000]}")
            else:
                print(f"  未找到 note 对象，data 前 2000 字符:")
                print(f"  {json.dumps(data, ensure_ascii=False)[:2000]}")

        ctx.close()
        browser.close()
        print("\n✓ 探测完成")


if __name__ == "__main__":
    main()
