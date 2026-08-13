"""聚焦探测 XHS-PUBLISH-BTN 内部结构。

已知：mouse.click(中心) 没触发发布。怀疑它是底部操作栏容器，
真实"发布"按钮在 shadow DOM 内部右侧，点中心打偏了。

探测目标：
1. shadowRoot 是否存在、内部 HTML 结构
2. shadowRoot 内所有可点击元素的位置/文案/disabled
3. light DOM children
4. outerHTML（看标签属性）
5. elementsFromPoint(中心、右侧) 看命中堆叠
6. 点击真实内部按钮后 URL 是否变化
"""

import base64
import io
import json
import os
import time
import urllib.request
import urllib.error
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


def _eval(session_id: str, js: str, timeout: int = 30) -> dict:
    return _post(f"/debug_eval/{session_id}", {"js": js}, timeout=timeout)


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
    print(f"  session_id = {session_id}")

    # 生成测试图，调 publish 让页面进入编辑器（点击会失败但不影响探测）
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1024, 1024), color=(91, 76, 219))
    draw = ImageDraw.Draw(img)
    draw.text((100, 480), "PROBE INTERNAL 20260809", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

    print("\n调 publish 让页面进入编辑器（预期点击失败，但 XHS-PUBLISH-BTN 会渲染）...")
    resp = _post(
        f"/publish/{session_id}",
        {"title": "内部探测_请忽略", "content": "探测 shadow DOM 内部结构。",
         "images_b64": [img_b64]},
        timeout=180,
    )
    print(f"  publish 结果: {resp.get('data', {}).get('message', '')[:120]}")

    # === 探测 1: outerHTML + children + shadowRoot ===
    print("\n=== 探测 1: XHS-PUBLISH-BTN 外层结构 ===")
    js_struct = """(() => {
        const btn = document.querySelector('xhs-publish-btn');
        if (!btn) return {error: 'xhs-publish-btn not found'};
        const r = btn.getBoundingClientRect();
        // light DOM 子元素
        const childInfos = Array.from(btn.children).map(c => ({
            tag: c.tagName, text: (c.innerText||'').slice(0,40),
            cls: c.className,
        }));
        // shadowRoot 探测
        const sr = btn.shadowRoot;
        let shadowInfo = null;
        if (sr) {
            // shadowRoot 内所有元素
            const all = sr.querySelectorAll('*');
            const clickables = [];
            all.forEach(el => {
                const er = el.getBoundingClientRect();
                if (er.width <= 0 || er.height <= 0) return;
                const st = window.getComputedStyle(el);
                if (st.display === 'none' || st.visibility === 'hidden') return;
                const tag = el.tagName;
                const txt = (el.innerText||el.textContent||'').trim().slice(0,30);
                const cls = typeof el.className === 'string' ? el.className : '';
                const role = el.getAttribute('role') || '';
                const disabled = el.disabled === true || el.getAttribute('aria-disabled')==='true';
                const cursor = st.cursor;
                // 只记录可能可点击的：button/a/[role=button]/cursor:pointer/有文案
                if (tag==='BUTTON' || tag==='A' || role==='button' ||
                    cursor==='pointer' || txt) {
                    clickables.push({
                        tag, text: txt, cls: cls.slice(0,80), role,
                        x: Math.round(er.x), y: Math.round(er.y),
                        w: Math.round(er.width), h: Math.round(er.height),
                        disabled, cursor,
                    });
                }
            });
            shadowInfo = {
                exists: true,
                mode: sr.mode,
                childCount: all.length,
                innerHTML: sr.innerHTML.slice(0, 2000),
                clickables,
            };
        } else {
            shadowInfo = {exists: false};
        }
        return {
            outerHTML: btn.outerHTML.slice(0, 500),
            attrs: btn.getAttributeNames(),
            bbox: {x: Math.round(r.x), y: Math.round(r.y),
                   w: Math.round(r.width), h: Math.round(r.height)},
            lightChildren: childInfos,
            shadow: shadowInfo,
        };
    })()"""
    resp = _eval(session_id, js_struct)
    data = resp.get("data")
    print(f"  外层结构: {json.dumps(data, ensure_ascii=False, indent=2)[:2500]}")

    # === 探测 2: elementsFromPoint 在中心和右侧 ===
    print("\n=== 探测 2: elementsFromPoint 命中堆叠 ===")
    js_hit = """(() => {
        const btn = document.querySelector('xhs-publish-btn');
        if (!btn) return {error: 'not found'};
        const r = btn.getBoundingClientRect();
        const cx = r.x + r.width/2, cy = r.y + r.height/2;
        const rx = r.x + r.width - 60;  // 右侧
        const points = [
            {name: 'center', x: cx, y: cy},
            {name: 'right',  x: rx, y: cy},
            {name: 'left',   x: r.x + 60, y: cy},
        ];
        return points.map(p => {
            const stack = document.elementsFromPoint(p.x, p.y).map(el => {
                const er = el.getBoundingClientRect();
                return {
                    tag: el.tagName,
                    text: (el.innerText||'').slice(0,20),
                    cls: (typeof el.className==='string'?el.className:'').slice(0,40),
                    w: Math.round(er.width), h: Math.round(er.height),
                };
            });
            return {point: p.name, coord:[Math.round(p.x),Math.round(p.y)], stack};
        });
    })()"""
    resp = _eval(session_id, js_hit)
    print(f"  命中堆叠: {json.dumps(resp.get('data'), ensure_ascii=False, indent=2)}")

    # === 探测 3: 找到内部真实发布按钮并点击 ===
    print("\n=== 探测 3: 点击 shadow 内真实发布按钮 ===")
    js_click_inner = """(() => {
        const btn = document.querySelector('xhs-publish-btn');
        if (!btn) return {error: 'not found'};
        const sr = btn.shadowRoot;
        if (!sr) return {error: 'no shadowRoot'};
        // 找文案含"发布"的元素，或 button/role=button
        const candidates = sr.querySelectorAll('button, a, [role="button"], div, span');
        let target = null;
        for (const el of candidates) {
            const txt = (el.innerText||el.textContent||'').trim();
            if (txt === '发布' || txt === '发布笔记' || txt === '立即发布') {
                target = el;
                break;
            }
        }
        if (!target) {
            // fallback: 找 cursor:pointer 的元素
            for (const el of candidates) {
                if (window.getComputedStyle(el).cursor === 'pointer') {
                    target = el;
                    break;
                }
            }
        }
        if (!target) {
            // 列出所有有文案的元素帮助定位
            const texts = Array.from(sr.querySelectorAll('*')).map(el => ({
                tag: el.tagName, text: (el.innerText||'').slice(0,20)
            })).filter(t => t.text);
            return {error: 'no target found in shadow', texts: texts.slice(0,20)};
        }
        const tr = target.getBoundingClientRect();
        const info = {
            found: true,
            tag: target.tagName,
            text: (target.innerText||'').slice(0,30),
            cls: (typeof target.className==='string'?target.className:'').slice(0,60),
            bbox: {x: Math.round(tr.x), y: Math.round(tr.y),
                   w: Math.round(tr.width), h: Math.round(tr.height)},
        };
        const beforeUrl = location.href;
        target.click();
        return {info, beforeUrl, afterUrl: location.href};
    })()"""
    resp = _eval(session_id, js_click_inner)
    print(f"  内部点击结果: {json.dumps(resp.get('data'), ensure_ascii=False, indent=2)}")

    time.sleep(3)
    resp = _eval(session_id, "({url: location.href, hasSuccess: !!document.body.innerText.match(/发布成功|已发布/)})")
    print(f"  3s 后状态: {json.dumps(resp.get('data'), ensure_ascii=False)}")

    # 关闭
    print("\n关闭 session...")
    req = urllib.request.Request(f"{WORKER_URL}/session/{session_id}", method="DELETE")
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
