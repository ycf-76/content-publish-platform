"""检查前端 workflow store 状态，定位 final_review 审核界面不显示的问题。"""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import jwt
from playwright.async_api import async_playwright

SCREENSHOT_DIR = Path(r"d:\My_Project\多智能体小红书发布平台\test_screenshots")
SCREENSHOT_DIR.mkdir(exist_ok=True)

JWT_SECRET = "oUQUph4WcTCyIwkWFPs2g93uYHhmJY2knA44kB17w4fRebd4ILwNdgzafTIU0W79"
JWT_ALGO = "HS256"

def make_token():
    payload = {
        "sub": "test_user_01",
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "iat": datetime.now(timezone.utc),
        "xhs_user_id": "test_xhs_001",
        "nickname": "测试用户",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

CHECK_JS = """
() => {
  try {
    const appEl = document.querySelector('#app');
    if (!appEl || !appEl.__vue_app__) return {error: 'Vue app not found'};
    const app = appEl.__vue_app__;
    const store = app.config.globalProperties.$pinia._s.get('workflow');
    if (!store) return {error: 'workflow store not found'};
    // Pinia setup store: ref 通过 store.xxx 直接访问（已解包），不用 .value
    const cw = store.currentWorkflow ?? null;
    const ns = store.nodes ?? [];
    const iss = store.isStreaming ?? null;
    const err = store.error ?? null;
    return {
      currentWorkflow: cw,
      nodes: Array.from(ns).map(n => ({
        node_id: n.node_id || n.node_type,
        status: n.status,
        has_output: !!(n.output || n.result),
      })),
      isStreaming: iss,
      error: err,
      activeWfId: localStorage.getItem('mint_active_workflow_id'),
      token: localStorage.getItem('token') ? 'EXISTS' : 'MISSING',
    };
  } catch(e) {
    return {error: e.toString()};
  }
}
"""

async def main():
    token = make_token()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        # 先设置有效 JWT token
        await page.goto("http://localhost:3001/login", wait_until="domcontentloaded")
        await page.evaluate(f"""() => {{
            localStorage.setItem('token', '{token}');
            localStorage.setItem('mint_has_logged_in', '1');
        }}""")

        # 访问工作台
        await page.goto("http://localhost:3001/workbench", wait_until="domcontentloaded")
        await page.wait_for_timeout(4000)

        print(f"当前 URL: {page.url}")
        print(f"页面标题: {await page.title()}")

        has_app = await page.evaluate("() => !!document.querySelector('#app')")
        print(f"#app 存在: {has_app}")

        result = await page.evaluate(CHECK_JS)
        print("=" * 60)
        print("前端 Workflow Store 状态")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))

        # 截图
        ss = SCREENSHOT_DIR / "workbench_store_check.png"
        await page.screenshot(path=str(ss), full_page=True)
        print(f"\n截图: {ss}")

        await browser.close()

asyncio.run(main())
