"""探测发布按钮真实 DOM 位置（用纯浏览器 JS）。

debug_eval 接口直接 page.evaluate(js)，js 必须是浏览器端纯 JS 表达式。
"""

import json
import os
import urllib.request
from pathlib import Path

WORKER_URL = "http://127.0.0.1:9010"


def _load_env() -> None:
    env = Path(".env")
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _post(path: str, body: dict, timeout: int = 60) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{WORKER_URL}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def main() -> None:
    _load_env()
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import XhsAccount
    from app.crypto.token_crypto import TokenCrypto

    account_id = "sB_T5UWogJoQlezOpYAEiQ"
    async with AsyncSessionLocal() as db:
        account = await db.scalar(select(XhsAccount).where(XhsAccount.id == account_id))
        crypto = TokenCrypto()
        session_data = crypto.decrypt_dict(account.session_data_encrypted)
        cookies = session_data.get("cookies", []) if isinstance(session_data, dict) else session_data

    print("创建 session...")
    resp = _post("/session/create", {"cookies": cookies}, timeout=60)
    session_id = resp["data"]["session_id"]
    print(f"session_id = {session_id}")

    # 用 debug_eval 让浏览器跳到发布页（纯 JS 不能用 page.goto）
    # 改用 publish 接口走到扫描阶段，但保留 session 用于后续探测
    # 直接在当前页执行 JS
    print("\n=== 探测 1: 当前页 URL + 标题 ===")
    js_url = "({url: location.href, title: document.title})"
    resp = _post(f"/debug_eval/{session_id}", {"js": js_url}, timeout=30)
    print(f"  {resp.get('data')}")

    # 直接导航到发布页（用 location.href，再等一下）
    print("\n导航到发布页...")
    js_nav = "location.href = 'https://creator.xiaohongshu.com/publish/publish?from=menu&target=image'; 'navigating'"
    _post(f"/debug_eval/{session_id}", {"js": js_nav}, timeout=30)
    import time
    time.sleep(5)

    resp = _post(f"/debug_eval/{session_id}", {"js": js_url}, timeout=30)
    print(f"  导航后: {resp.get('data')}")

    # 等页面加载完
    time.sleep(5)
    resp = _post(f"/debug_eval/{session_id}", {"js": js_url}, timeout=30)
    print(f"  5s 后: {resp.get('data')}")

    # === 探测 2: 在品牌红按钮位置 (x=344-758, y=706-775) 用 elementFromPoint 找元素 ===
    print("\n=== 探测 2: elementFromPoint 在品牌红位置找元素 ===")
    js_probe = """(() => {
        const points = [
            [550, 740], [400, 720], [700, 720],
            [550, 710], [550, 760], [450, 740], [650, 740],
        ];
        const out = [];
        for (const [x, y] of points) {
            const el = document.elementFromPoint(x, y);
            if (el) {
                const r = el.getBoundingClientRect();
                const path = [];
                let cur = el;
                for (let i = 0; i < 6 && cur; i++) {
                    path.push((cur.tagName + '.' + (cur.className || '').toString().slice(0, 40)).slice(0, 60));
                    cur = cur.parentElement;
                }
                out.push({
                    point: [x, y],
                    tag: el.tagName,
                    class: (el.className || '').toString().slice(0, 120),
                    text: (el.innerText || el.textContent || '').slice(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    path: path,
                });
            } else {
                out.push({point: [x, y], tag: 'NULL'});
            }
        }
        return out;
    })()"""
    resp = _post(f"/debug_eval/{session_id}", {"js": js_probe}, timeout=30)
    elements = resp.get("data", [])
    print(f"采样点元素 ({len(elements)} 个):")
    for e in elements:
        print(f"  point={e.get('point')} tag={e.get('tag')} class={e.get('class')!r}")
        print(f"    text={e.get('text')!r} box=({e.get('x')},{e.get('y')},{e.get('w')}x{e.get('h')})")
        print(f"    path: {' > '.join(e.get('path', []))}")

    # === 探测 3: 扫描所有可见元素，找红色背景的 ===
    print("\n=== 探测 3: 找红色背景元素（小红书品牌红 #ff2442）===")
    js_red = """(() => {
        const out = [];
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const r = el.getBoundingClientRect();
            if (r.width < 50 || r.height < 20) continue;
            if (r.y < 600) continue;  // 只看底部
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            const bg = style.backgroundColor;
            // 解析 rgb(r, g, b)
            const m = bg.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/);
            if (!m) continue;
            const [_, rs, gs, bs] = m;
            const r0 = parseInt(rs), g0 = parseInt(gs), b0 = parseInt(bs);
            // 红色：r > 200, g < 100, b < 100
            if (r0 > 200 && g0 < 100 && b0 < 100) {
                out.push({
                    tag: el.tagName,
                    class: (el.className || '').toString().slice(0, 100),
                    text: (el.innerText || el.textContent || '').slice(0, 40),
                    bg: bg,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        return out;
    })()"""
    resp = _post(f"/debug_eval/{session_id}", {"js": js_red}, timeout=30)
    reds = resp.get("data", [])
    print(f"底部红色元素 ({len(reds)} 个):")
    for r in reds[:10]:
        print(f"  {r}")

    # === 探测 4: 扫描 shadow DOM ===
    print("\n=== 探测 4: shadow DOM ===")
    js_shadow = """(() => {
        const out = [];
        const all = document.querySelectorAll('*');
        for (const el of all) {
            if (el.shadowRoot) {
                const r = el.getBoundingClientRect();
                out.push({
                    tag: el.tagName,
                    class: (el.className || '').toString().slice(0, 80),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    shadow_children: el.shadowRoot.querySelectorAll('*').length,
                });
            }
        }
        return out;
    })()"""
    resp = _post(f"/debug_eval/{session_id}", {"js": js_shadow}, timeout=30)
    shadows = resp.get("data", [])
    print(f"shadow DOM ({len(shadows)} 个):")
    for s in shadows[:10]:
        print(f"  {s}")

    # 关闭
    print("\n关闭 session...")
    req = urllib.request.Request(f"{WORKER_URL}/session/{session_id}", method="DELETE")
    urllib.request.urlopen(req, timeout=10)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
