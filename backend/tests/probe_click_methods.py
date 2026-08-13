"""尝试多种方式触发 xhs-publish-btn 的点击事件。

之前发现：
- <xhs-publish-btn> 没有 shadow DOM，没有子元素
- mouse.click() 无反应
- elementFromPoint 返回元素本身

尝试：
1. JS btn.click() 直接调用
2. 派发 MouseEvent
3. 检查元素的事件监听器
4. 检查 Vue 组件实例
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

    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1024, 1024), color=(91, 76, 219))
    draw = ImageDraw.Draw(img)
    draw.text((100, 480), "CLICK PROBE 20260809", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    print("\n发起 publish（让页面进入编辑模式）...")
    resp = _post(
        f"/publish/{session_id}",
        {"title": "点击探测_请忽略", "content": "探测点击事件。",
         "images_b64": [img_b64]},
        timeout=180,
    )
    print(f"publish 结果: {resp.get('data', {}).get('message', '')[:100]}")

    # === 探测 1: 检查 Vue 组件实例和数据 ===
    print("\n=== 探测 1: 检查 Vue 组件实例 ===")
    js_vue = """(() => {
        const btn = document.querySelector('xhs-publish-btn');
        if (!btn) return {error: 'not found'};
        // Vue 3 组件实例在 __vueParentComponent
        // Vue 2 在 __vue__
        const info = {
            hasVue3: !!btn.__vueParentComponent,
            hasVue2: !!btn.__vue__,
            hasInternalInstance: !!btn._internalInstance,
            attrs: {},
        };
        // 尝试读取 Vue 3 组件 props/data
        if (btn.__vueParentComponent) {
            const inst = btn.__vueParentComponent;
            info.props = Object.keys(inst.props || {});
            info.data = Object.keys(inst.data || {});
            info.setupState = Object.keys(inst.setupState || {});
        }
        // 检查所有自定义属性
        const ownProps = Object.getOwnPropertyNames(btn).filter(p => !p.startsWith('__') && !['style','className','children','classList','attributes','dataset','innerHTML','outerHTML','innerText','textContent'].includes(p));
        info.ownProps = ownProps.slice(0, 20);
        // 检查 data-* 属性
        info.dataAttrs = btn.getAttributeNames().filter(n => n.startsWith('data-'));
        info.allAttrs = btn.getAttributeNames();
        return info;
    })()"""
    resp = _post(f"/debug_eval/{session_id}", {"js": js_vue}, timeout=30)
    print(f"  Vue 组件信息: {resp.get('data')}")

    # === 探测 2: 检查事件监听器（通过 getEventListeners，仅 Chrome）===
    print("\n=== 探测 2: 检查 computed style 找伪元素 ===")
    js_pseudo = """(() => {
        const btn = document.querySelector('xhs-publish-btn');
        if (!btn) return {error: 'not found'};
        const style = window.getComputedStyle(btn);
        const before = window.getComputedStyle(btn, '::before');
        const after = window.getComputedStyle(btn, '::after');
        return {
            bg: style.backgroundColor,
            bgImage: style.backgroundImage.slice(0, 100),
            cursor: style.cursor,
            pointerEvents: style.pointerEvents,
            display: style.display,
            position: style.position,
            before: {
                content: before.content,
                bg: before.backgroundColor,
                w: before.width, h: before.height,
                display: before.display,
            },
            after: {
                content: after.content,
                bg: after.backgroundColor,
                w: after.width, h: after.height,
                display: after.display,
            },
        };
    })()"""
    resp = _post(f"/debug_eval/{session_id}", {"js": js_pseudo}, timeout=30)
    print(f"  computed style: {resp.get('data')}")

    # === 探测 3: 直接调用 .click() 方法 ===
    print("\n=== 探测 3: 直接 JS 调用 btn.click() ===")
    js_click = """(() => {
        const btn = document.querySelector('xhs-publish-btn');
        if (!btn) return {error: 'not found'};
        const beforeUrl = location.href;
        btn.click();
        return {beforeUrl: beforeUrl, afterUrl: location.href, clicked: true};
    })()"""
    resp = _post(f"/debug_eval/{session_id}", {"js": js_click}, timeout=30)
    print(f"  click 结果: {resp.get('data')}")

    # 等一下看 URL 是否变化
    time.sleep(3)
    resp = _post(f"/debug_eval/{session_id}", {"js": "({url: location.href})"}, timeout=30)
    print(f"  3s 后 URL: {resp.get('data')}")

    # === 探测 4: 派发真实 MouseEvent ===
    print("\n=== 探测 4: 派发 MouseEvent ===")
    js_mouse = """(() => {
        const btn = document.querySelector('xhs-publish-btn');
        if (!btn) return {error: 'not found'};
        const r = btn.getBoundingClientRect();
        const cx = r.x + r.width / 2;
        const cy = r.y + r.height / 2;
        // 派发完整的鼠标事件序列
        const opts = {bubbles: true, cancelable: true, clientX: cx, clientY: cy, view: window};
        const mousedown = new MouseEvent('mousedown', opts);
        const mouseup = new MouseEvent('mouseup', opts);
        const click = new MouseEvent('click', opts);
        btn.dispatchEvent(mousedown);
        btn.dispatchEvent(mouseup);
        btn.dispatchEvent(click);
        return {dispatched: true, at: [cx, cy]};
    })()"""
    resp = _post(f"/debug_eval/{session_id}", {"js": js_mouse}, timeout=30)
    print(f"  dispatch 结果: {resp.get('data')}")

    time.sleep(3)
    resp = _post(f"/debug_eval/{session_id}", {"js": "({url: location.href})"}, timeout=30)
    print(f"  3s 后 URL: {resp.get('data')}")

    # 关闭
    print("\n关闭 session...")
    req = urllib.request.Request(f"{WORKER_URL}/session/{session_id}", method="DELETE")
    urllib.request.urlopen(req, timeout=10)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
