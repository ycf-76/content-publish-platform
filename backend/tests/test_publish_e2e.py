"""端到端发布测试：DB cookies → worker session → publish。

直接调 worker HTTP 接口，不走完整工作流，专注验证 publish 按钮修复。
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error


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


WORKER_URL = "http://127.0.0.1:9010"


def _post(path: str, body: dict, timeout: int = 120) -> dict:
    """同步 POST（worker 是同步 HTTPServer，用 urllib 即可）。"""
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{WORKER_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get(path: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(f"{WORKER_URL}{path}", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def main() -> None:
    _load_env()

    # 1. 从 DB 加载账号 cookies
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import XhsAccount
    from app.crypto.token_crypto import TokenCrypto

    account_id = "sB_T5UWogJoQlezOpYAEiQ"  # 全栈魔术师
    print(f"加载账号 {account_id} 的 cookies...")
    async with AsyncSessionLocal() as db:
        stmt = select(XhsAccount).where(XhsAccount.id == account_id)
        account = await db.scalar(stmt)
        if not account:
            print(f"[ERROR] 账号 {account_id} 不存在")
            return
        if not account.session_data_encrypted:
            print(f"[ERROR] 账号 {account_id} 无 cookies")
            return
        crypto = TokenCrypto()
        session_data = crypto.decrypt_dict(account.session_data_encrypted)
        cookies = (
            session_data.get("cookies", [])
            if isinstance(session_data, dict)
            else session_data
        )
    print(f"cookies 加载成功（{len(cookies)} 项），nickname={account.xhs_nickname}")

    # 2. 创建 worker 工作会话
    print(f"\n创建 worker session...")
    t0 = time.time()
    try:
        resp = _post("/session/create", {"cookies": cookies}, timeout=60)
    except urllib.error.HTTPError as e:
        print(f"[ERROR] session/create HTTP {e.code}: {e.read().decode('utf-8', 'ignore')}")
        return
    elapsed = time.time() - t0
    print(f"耗时 {elapsed:.2f}s, resp={resp}")
    if not resp.get("success"):
        print(f"[ERROR] session 创建失败: {resp.get('message')}")
        return
    session_id = resp["data"]["session_id"]
    print(f"session_id = {session_id}")

    # 3. 验证登录态（调 /user_info_current）
    print(f"\n验证登录态...")
    try:
        resp = _get(f"/user_info_current/{session_id}", timeout=30)
        print(f"resp keys: {list(resp.keys())}")
        if resp.get("success"):
            info = resp.get("data", {})
            print(f"  nickname: {info.get('nickname')}")
            print(f"  red_id:   {info.get('red_id')}")
        else:
            print(f"  [WARN] {resp.get('message')}")
    except Exception as e:
        print(f"  [WARN] {e}")

    # 4. 发起发布测试（带 1 张测试图，真实发布后手动删除）
    #    生成 1024x1024 纯色 PNG + 文字标识，便于发布后识别和删除
    print(f"\n生成测试图片...")
    import base64
    import io
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("[ERROR] Pillow 未安装，无法生成测试图")
        return
    img = Image.new("RGB", (1024, 1024), color=(91, 76, 219))
    draw = ImageDraw.Draw(img)
    draw.text((100, 480), "TEST PUBLISH 20260809", fill=(255, 255, 255))
    draw.text((100, 540), "worker publish btn fix verify", fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    print(f"  图片生成完成: 1024x1024 PNG, {len(img_b64)} bytes base64")

    test_title = "测试发布_请忽略_20260809"
    test_content = (
        "这是 worker publish 按钮修复后的端到端测试。"
        "验证发布按钮能被找到并点击。"
        "如看到此笔记请忽略，会手动删除。"
    )
    print(f"\n发起发布测试...")
    print(f"  title:   {test_title}")
    print(f"  content: {test_content[:60]}...")
    print(f"  images:  1 张测试图")
    t0 = time.time()
    try:
        resp = _post(
            f"/publish/{session_id}",
            {"title": test_title, "content": test_content, "images_b64": [img_b64]},
            timeout=180,
        )
    except urllib.error.HTTPError as e:
        elapsed = time.time() - t0
        print(f"\n[ERROR] publish HTTP {e.code} after {elapsed:.2f}s")
        print(f"  body: {e.read().decode('utf-8', 'ignore')[:500]}")
        return
    except Exception as e:
        elapsed = time.time() - t0
        print(f"\n[ERROR] publish 异常 after {elapsed:.2f}s: {type(e).__name__}: {e}")
        return
    elapsed = time.time() - t0
    print(f"\n发布耗时: {elapsed:.2f}s")
    print(f"resp: {json.dumps(resp, ensure_ascii=False, indent=2)}")

    if resp.get("success"):
        data = resp.get("data", {})
        status = data.get("status")
        if status == "success":
            print(f"\n✅ 发布成功！post_id={data.get('post_id')}")
            print(f"   请手动到小红书删除测试笔记：{test_title}")
        else:
            print(f"\n⚠️ 发布未成功：status={status}")
            print(f"   message: {data.get('message')}")
            # 检查是否有诊断信息
            msg = data.get("message", "")
            if "publish_diag" in msg or "diag" in msg.lower():
                print(f"   >>> 诊断信息已保存，检查 buttons.json 看完整按钮列表")
    else:
        print(f"\n❌ worker 返回失败: {resp.get('message')}")

    # 5. 关闭 session
    print(f"\n关闭 session...")
    try:
        req = urllib.request.Request(
            f"{WORKER_URL}/session/{session_id}", method="DELETE"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"  close resp: {r.read().decode('utf-8')}")
    except Exception as e:
        print(f"  [WARN] close session: {e}")


if __name__ == "__main__":
    asyncio.run(main())
