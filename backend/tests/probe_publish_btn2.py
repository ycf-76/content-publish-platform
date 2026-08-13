"""完整发布流程探测：上传图片进入编辑模式后，在按钮位置找元素。

之前发现：
- 直接访问 URL 停在上传引导页，无发布按钮
- 完整发布流程 buttons.json 有编辑器元素但无发布按钮节点
- 截图显示底部有品牌红按钮 (x=344-758, y=706-775)

策略：走完整发布流程（上传图+填标题+填正文），然后在按钮位置
用 elementFromPoint 找元素 + 遍历 DOM 树找 publish/submit 相关节点
"""

import base64
import io
import json
import os
import time
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


def _post(path: str, body: dict, timeout: int = 180) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{WORKER_URL}{path}", data=data,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"success": False, "status": e.code,
                "body": e.read().decode("utf-8", "ignore")[:500]}


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

    # 用 publish 接口走完整流程（会上传图、填标题、填正文、找按钮）
    # 这次 publish 会失败（按钮找不到），但页面已切换到编辑模式
    # 我们在失败后立即用 debug_eval 探测
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1024, 1024), color=(91, 76, 219))
    draw = ImageDraw.Draw(img)
    draw.text((100, 480), "PROBE 20260809", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    print("\n发起 publish（预期失败，但页面会进入编辑模式）...")
    t0 = time.time()
    resp = _post(
        f"/publish/{session_id}",
        {"title": "探测发布按钮_请忽略", "content": "这是 DOM 探测测试，请忽略。",
         "images_b64": [img_b64]},
        timeout=180,
    )
    print(f"publish 耗时 {time.time()-t0:.2f}s, success={resp.get('success')}")
    print(f"message: {resp.get('data', {}).get('message', '')[:200]}")

    # 关键：publish 失败后 session 还在，页面还在编辑模式
    # 立即用 debug_eval 探测
    print("\n=== 探测 1: 当前页 URL ===")
    js_url = "({url: location.href, title: document.title})"
    resp = _post(f"/debug_eval/{session_id}", {"js": js_url}, timeout=30)
    print(f"  {resp.get('data')}")

    # === 探测 2: elementFromPoint 在品牌红位置找元素 ===
    print("\n=== 探测 2: elementFromPoint 在品牌红按钮位置找元素 ===")
    js_probe = """(() => {
        const points = [
            [550, 740], [400, 720], [700, 720],
            [550, 710], [550, 760], [450, 740], [650, 740],
            [350, 740], [750, 740],
        ];
        const out = [];
        for (const [x, y] of points) {
            const el = document.elementFromPoint(x, y);
            if (el) {
                const r = el.getBoundingClientRect();
                const path = [];
                let cur = el;
                for (let i = 0; i < 8 && cur; i++) {
                    const cls = (cur.className || '').toString().slice(0, 50);
                    path.push(cur.tagName + (cls ? '.' + cls : ''));
                    cur = cur.parentElement;
                }
                out.push({
                    point: [x, y],
                    tag: el.tagName,
                    class: (el.className || '').toString().slice(0, 120),
                    text: (el.innerText || el.textContent || '').slice(0, 60),
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

    # === 探测 3: 扫描所有底部可见元素，找红色背景 ===
    print("\n=== 探测 3: 找底部红色背景元素 ===")
    js_red = """(() => {
        const out = [];
        const all = document.querySelectorAll('*');
        for (const el of all) {
            const r = el.getBoundingClientRect();
            if (r.width < 50 || r.height < 20) continue;
            if (r.y < 600) continue;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            const bg = style.backgroundColor;
            const m = bg.match(/rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/);
            if (!m) continue;
            const r0 = parseInt(m[1]), g0 = parseInt(m[2]), b0 = parseInt(m[3]);
            if (r0 > 200 && g0 < 100 && b0 < 100) {
                out.push({
                    tag: el.tagName,
                    class: (el.className || '').toString().slice(0, 100),
                    text: (el.innerText || el.textContent || '').slice(0, 60),
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

    # === 探测 4: 全局搜索 class 含 publish/submit/post/commit/confirm 的元素 ===
    print("\n=== 探测 4: 全局搜索 publish/submit/post/commit 相关元素 ===")
    js_search = """(() => {
        const out = [];
        const sels = '[class*="publish"], [class*="submit"], [class*="post"], [class*="commit"], [class*="confirm"], [class*="footer"], [class*="bottom"]';
        document.querySelectorAll(sels).forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) return;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;
            const txt = (el.innerText || el.textContent || '').trim();
            // 只看底部区域或有文字的
            if (r.y < 600 && !txt) return;
            out.push({
                tag: el.tagName,
                class: (el.className || '').toString().slice(0, 120),
                text: txt.slice(0, 60),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                children: el.children.length,
            });
        });
        return out;
    })()"""
    resp = _post(f"/debug_eval/{session_id}", {"js": js_search}, timeout=30)
    candidates = resp.get("data", [])
    print(f"候选元素 ({len(candidates)} 个):")
    for c in candidates[:20]:
        print(f"  {c}")

    # === 探测 5: 找所有 button 和 [role=button] ===
    print("\n=== 探测 5: 所有 button + role=button ===")
    js_btns = """(() => {
        const out = [];
        document.querySelectorAll('button, [role="button"], [onclick]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width <= 0 || r.height <= 0) return;
            const style = window.getComputedStyle(el);
            if (style.display === 'none' || style.visibility === 'hidden') return;
            const txt = (el.innerText || el.textContent || '').trim();
            out.push({
                tag: el.tagName,
                class: (el.className || '').toString().slice(0, 100),
                text: txt.slice(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                bg: style.backgroundColor,
                has_onclick: el.hasAttribute('onclick'),
            });
        });
        return out;
    })()"""
    resp = _post(f"/debug_eval/{session_id}", {"js": js_btns}, timeout=30)
    btns = resp.get("data", [])
    print(f"button/role=button ({len(btns)} 个):")
    for b in btns[:25]:
        print(f"  {b}")

    # 关闭
    print("\n关闭 session...")
    req = urllib.request.Request(f"{WORKER_URL}/session/{session_id}", method="DELETE")
    urllib.request.urlopen(req, timeout=10)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
