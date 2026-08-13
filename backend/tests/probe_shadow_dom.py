"""探测 xhs-publish-btn 的 shadow DOM 内部结构。

之前发现：
- <xhs-publish-btn> 是 680x90 的容器
- mouse.click(628, 755) 点击后无反应
- elementFromPoint 返回的是 <xhs-publish-btn> 本身

推测：实际可点击按钮在 shadow DOM 内部
验证：检查 el.shadowRoot，如果有，找内部的可点击元素
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

    # 走完整发布流程（会上传图+填标题+填正文+点击按钮）
    # publish 会失败，但页面已进入编辑模式且 xhs-publish-btn 已渲染
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1024, 1024), color=(91, 76, 219))
    draw = ImageDraw.Draw(img)
    draw.text((100, 480), "SHADOW PROBE 20260809", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    print("\n发起 publish（预期失败，但 xhs-publish-btn 已渲染）...")
    resp = _post(
        f"/publish/{session_id}",
        {"title": "shadow探测_请忽略", "content": "探测 shadow DOM。",
         "images_b64": [img_b64]},
        timeout=180,
    )
    print(f"publish 结果: {resp.get('data', {}).get('message', '')[:100]}")

    # === 关键探测：xhs-publish-btn 的 shadow DOM ===
    print("\n=== 探测 xhs-publish-btn 的 shadow DOM 内部结构 ===")
    js_shadow = """(() => {
        const btn = document.querySelector('xhs-publish-btn');
        if (!btn) return {error: 'xhs-publish-btn not found'};
        const r = btn.getBoundingClientRect();
        const info = {
            tag: btn.tagName,
            box: {x: r.x, y: r.y, w: r.width, h: r.height},
            hasShadow: !!btn.shadowRoot,
            children: btn.children.length,
            childTags: Array.from(btn.children).map(c => c.tagName + '.' + (c.className||'').slice(0,40)),
        };
        if (btn.shadowRoot) {
            info.shadowChildren = btn.shadowRoot.querySelectorAll('*').length;
            info.shadowChildTags = Array.from(btn.shadowRoot.querySelectorAll('*')).map(el => {
                const cr = el.getBoundingClientRect();
                return {
                    tag: el.tagName,
                    class: (el.className || '').toString().slice(0, 60),
                    text: (el.innerText || el.textContent || '').slice(0, 30),
                    x: Math.round(cr.x), y: Math.round(cr.y),
                    w: Math.round(cr.width), h: Math.round(cr.height),
                    hasOnClick: el.onclick !== null,
                    hasListeners: el.getAttributeNames().filter(n => n.startsWith('on')),
                };
            });
        }
        return info;
    })()"""
    resp = _post(f"/debug_eval/{session_id}", {"js": js_shadow}, timeout=30)
    info = resp.get("data", {})
    print(f"\nxhs-publish-btn 信息:")
    print(f"  box: {info.get('box')}")
    print(f"  hasShadow: {info.get('hasShadow')}")
    print(f"  children: {info.get('children')}")
    print(f"  childTags: {info.get('childTags')}")
    if info.get('hasShadow'):
        print(f"  shadow children: {info.get('shadowChildren')}")
        print(f"  shadow child tags:")
        for sc in info.get('shadowChildTags', [])[:15]:
            print(f"    {sc}")

    # === 探测：用 elementFromPoint 但在 shadow DOM 内部 ===
    print("\n=== deepElementFromPoint：穿透 shadow DOM ===")
    js_deep = """(() => {
        // deepElementFromPoint: 穿透 shadow DOM 找最深层元素
        function deepElementFromPoint(x, y) {
            let el = document.elementFromPoint(x, y);
            if (!el) return null;
            // 穿透 shadow DOM
            while (el.shadowRoot) {
                const inner = el.shadowRoot.elementFromPoint(x, y);
                if (!inner || inner === el) break;
                el = inner;
            }
            return el;
        }
        const points = [[628, 755], [550, 740], [450, 740], [700, 740]];
        return points.map(([x, y]) => {
            const el = deepElementFromPoint(x, y);
            if (!el) return {point: [x, y], tag: 'NULL'};
            const r = el.getBoundingClientRect();
            return {
                point: [x, y],
                tag: el.tagName,
                class: (el.className || '').toString().slice(0, 80),
                text: (el.innerText || el.textContent || '').slice(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                inShadow: el.getRootNode() !== document,
            };
        });
    })()"""
    resp = _post(f"/debug_eval/{session_id}", {"js": js_deep}, timeout=30)
    deeps = resp.get("data", [])
    print(f"穿透 shadow DOM 后的元素:")
    for d in deeps:
        print(f"  {d}")

    # 关闭
    print("\n关闭 session...")
    req = urllib.request.Request(f"{WORKER_URL}/session/{session_id}", method="DELETE")
    urllib.request.urlopen(req, timeout=10)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
