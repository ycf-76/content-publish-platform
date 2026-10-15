"""常驻持久化发布浏览器会话（替代 Scrapling StealthyFetcher 的一次性会话）。

## 为什么要替换 StealthyFetcher

原实现（app/services/platform_publisher.py 旧版）用
`StealthyFetcher.fetch(url, headless=True, page_action=...)` 做发布，实测有四个硬伤：

1. **一次性上下文**：`fetch()` 内部是 `with StealthySession() as engine:`，
   `page_action` 返回后浏览器立刻关闭。而业务默认走「半自动」模式
   （填完内容等用户手动点发布按钮）——页面都已经销毁了，用户去哪儿点？
   前端还会提示"请在浏览器窗口手动点击发布"，实际根本没有窗口（headless=True）。
2. **冷启动极慢**：实测一次 `fetch()` 从 import 到返回耗时 **71 秒**
   （patchright chromium 启动 + 指纹脚本注入），而代码里 `timeout=60000`，
   page_action 里还有约 10 秒的固定 sleep，超时是常态。每次发布都重新冷启动。
3. **截图永远拿不到**：scrapling 的 `Response` **没有 `.page` 属性**
   （已用 `hasattr(response, 'page') == False` 实测确认），于是代码走到
   fallback——另起一个裸 playwright chromium 重新打开 URL 截图。
   那是另一个全新的、未登录的会话，既没有刚填的内容，也大概率被风控，
   前端拿到的截图永远是登录页/空白页，看起来就像"发布失败了"。
4. **依赖缺失**：后端实际用 `.venv/Scripts/python.exe` 启动，
   而 `.venv` 里**没有安装 scrapling**（也没有 camoufox），
   所以 `from scrapling.fetchers import StealthyFetcher` 必然 ImportError，
   直接返回 "Scrapling 未安装"。

## 本模块的方案

- 用 **Playwright persistent context**（`launch_persistent_context`）代替一次性 fetch，
  登录态/cookies 落盘到 `backend/data/browser_profiles/publish_{platform}`，
  扫码登录一次，之后长期复用，不再每次冷启动。
- 反检测用 `.venv` 里**已经有**的 `playwright_stealth`（2.0.3），
  不需要引入 scrapling / camoufox 等新依赖。
- **默认有头模式**（`PUBLISHER_HEADED=1`）：弹出真实 Chrome 窗口，
  这样"填完 → 人工确认 → 点发布"的半自动流程才真正成立，
  用户也能在窗口里直接扫码登录。
- 与内置浏览器（BrowserClient）共用同一份 profile 目录，
  内置浏览器面板里看到的就是发布会话的同一个页面。
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_PROFILE_BASE = Path(__file__).resolve().parents[1] / "data" / "browser_profiles"
# 平台扫码登录（qr_worker）写到这里；发布会话启动时从这里迁移一次
STORAGE_DIR = Path(__file__).resolve().parents[1] / "storage_states"

# 平台发布页（权威定义：platform_publisher / browser router 都从这里引用）
PUBLISHER_URLS: dict[str, str] = {
    # 小红书 /publish/publish 默认停在「上传视频」tab；图文发布必须带 target=image。
    # 实测：非激活 tab 的内容被站点挪到负坐标（rect.x≈-9726），
    # Playwright 的 actionability 检查永远过不了，打开后再点 tab 切换必然超时，
    # 所以只能靠 URL 参数直接进图文模式。
    "xiaohongshu": "https://creator.xiaohongshu.com/publish/publish?target=image",
    "douyin": "https://creator.douyin.com/creator-micro/content/upload",
    "kuaishou": "https://creator.kuaishou.com/publish/video",
    "bilibili": "https://member.bilibili.com/platform/upload/video/frame",
    "zhihu": "https://www.zhihu.com/creator/writer",
    "wechat": "https://channels.weixin.qq.com/platform/post",
}

# 创作者域名 -> 平台（BrowserClient 判定"需要登录"时用）
PUBLISHER_HOSTS: dict[str, str] = {
    "creator.xiaohongshu.com": "xiaohongshu",
    "www.xiaohongshu.com": "xiaohongshu",
    "creator.douyin.com": "douyin",
    "creator.kuaishou.com": "kuaishou",
    "member.bilibili.com": "bilibili",
    "www.zhihu.com": "zhihu",
    "channels.weixin.qq.com": "wechat",
}

# 登录后不应出现的路径片段（出现即视为未登录/掉登录）
_LOGIN_PATH_HINTS = ("/login", "/signin", "/passport", "redirectReason=401")

_SUCCESS_HINTS = ("发布成功", "已发布", "审核中", "投稿成功", "提交成功", "发布完成")
_FAIL_HINTS = ("发布失败", "上传失败", "请重试", "登录已失效")


def load_storage_cookies(platform: str) -> list[dict]:
    """从 storage_states/{platform}.json 读 cookies（迁移扫码登录态用）。

    平台扫码登录（qr_worker）目前仍写到 `app/storage_states/*.json`，
    而发布会话用的是持久化 profile——两者不是同一个浏览器实例，
    所以会话首次启动时要迁移一次，用户不用再登录第二遍。
    """
    path = STORAGE_DIR / f"{platform}.json"
    if not path.exists():
        return []
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        now = time.time()
        cookies: list[dict] = []
        for c in state.get("cookies", []):
            cookie: dict[str, Any] = {"name": c.get("name", ""), "value": c.get("value", "")}
            for key in ("domain", "path", "url", "expires", "httpOnly", "secure", "sameSite"):
                if c.get(key) is not None:
                    cookie[key] = c[key]
            # 过期 cookie 会被 playwright 拒绝，直接丢掉
            exp = cookie.get("expires")
            if isinstance(exp, (int, float)) and 0 < exp < now:
                continue
            cookies.append(cookie)
        return cookies
    except Exception as e:
        logger.warning(f"[publisher-session] read storageState failed: {e}")
        return []


def publisher_headed() -> bool:
    """是否有头模式（默认 True——半自动发布必须有可见窗口）。

    设环境变量 PUBLISHER_HEADED=0 可切回无头（仅全自动 auto_submit 时可用）。
    """
    return os.getenv("PUBLISHER_HEADED", "1").strip().lower() not in ("0", "false", "no", "off")


def profile_id_for(platform: str) -> str:
    """发布会话的 profile id（与内置浏览器共用同一目录）。"""
    return f"publish_{platform}"


class PublisherSession:
    """单个平台的常驻发布浏览器会话。

    生命周期：进程内常驻，首次调用时启动，异常断开时自动重建。
    不主动关闭——用户可能正在窗口里操作。
    """

    def __init__(self, platform: str) -> None:
        self.platform = platform
        self._pw: Any = None
        self._context: Any = None
        self._page: Any = None
        self._lock = asyncio.Lock()
        self._last_error = ""
        self._started_at = 0.0

    # ------------------------------------------------------------------
    # 启动 / 复用
    # ------------------------------------------------------------------

    @property
    def alive(self) -> bool:
        return bool(self._context and self._page) and not self._page.is_closed()

    @property
    def context(self) -> Any:
        """底层 BrowserContext（注入 cookies 等场景用；未启动则为 None）。"""
        return self._context

    @property
    def headed(self) -> bool:
        """是否有头（有真实可见窗口）。"""
        return publisher_headed()

    async def _launch(self) -> None:
        from playwright.async_api import async_playwright

        user_data_dir = _PROFILE_BASE / profile_id_for(self.platform)
        user_data_dir.mkdir(parents=True, exist_ok=True)

        self._pw = await async_playwright().start()
        self._context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=not publisher_headed(),
            viewport={"width": 1440, "height": 900},
            ignore_https_errors=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--start-maximized",
            ],
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
        )

        # 反检测：venv 里已装 playwright_stealth，无需 scrapling/camoufox
        try:
            from playwright_stealth import Stealth

            await Stealth().apply_stealth_async(self._context)
            logger.info(f"[publisher-session:{self.platform}] stealth applied")
        except Exception as e:
            logger.warning(f"[publisher-session:{self.platform}] stealth not applied: {e}")

        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
        self._started_at = time.time()
        logger.info(
            f"[publisher-session:{self.platform}] launched "
            f"(headed={publisher_headed()}, profile={user_data_dir})"
        )

        # 首次启动：把扫码登录态从 storage_states 迁进持久化 profile
        await self._migrate_storage_cookies()

    async def _migrate_storage_cookies(self) -> None:
        """把 storage_states 里已有的登录态迁进本会话（profile 里已有时跳过）。

        实测有效：2026-10-07 用户扫码后，迁移 18 个 cookie（含 web_session）
        即可直接进入 creator.xiaohongshu.com/publish/publish（此前是 401 跳登录）。
        """
        try:
            if self._context is None:
                return
            have = await self._context.cookies()
            if any(c.get("name") == "web_session" for c in have):
                return
            cookies = load_storage_cookies(self.platform)
            if not cookies:
                return
            await self._context.add_cookies(cookies)
            logger.info(
                f"[publisher-session:{self.platform}] migrated {len(cookies)} cookies "
                f"from storage_states/{self.platform}.json"
            )
        except Exception as e:
            logger.warning(f"[publisher-session:{self.platform}] cookie migration skipped: {e}")

    async def page(self) -> Any:
        """拿到可用的 page（首次调用会启动浏览器）。"""
        async with self._lock:
            if not self.alive:
                await self._safe_close()
                await self._launch()
            return self._page

    async def open(self, url: str, timeout_ms: int = 45000) -> Any:
        """导航到 url 并返回 page。已在同页面则跳过重复加载。"""
        page = await self.page()
        try:
            if page.url.rstrip("/") == url.rstrip("/"):
                return page
        except Exception:
            pass
        await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass  # 创作者中心常有长轮询，等不到就拉倒
        return page

    # ------------------------------------------------------------------
    # 状态判定
    # ------------------------------------------------------------------

    async def current_url(self) -> str:
        if not self.alive:
            return ""
        try:
            return self._page.url or ""
        except Exception:
            return ""

    async def is_logged_in(self) -> bool:
        """粗判登录态：页面 URL 落在登录路径上即视为未登录。"""
        url = await self.current_url()
        if not url:
            return False
        lowered = url.lower()
        return not any(hint in lowered for hint in _LOGIN_PATH_HINTS)

    async def check_publish_state(self) -> dict:
        """回查发布结果（半自动模式前端轮询用）。

        返回 status:
          - pending: 仍在编辑页，等用户点发布
          - published: 已发布（页面已跳转/出现成功提示）
          - failed: 页面出现失败提示
          - session_invalid: 会话不在了（浏览器被关/掉登录）
          - not_applicable: 没有进行中的发布会话
        """
        if not self.alive:
            return {"status": "not_applicable", "message": "没有进行中的发布会话"}

        url = await self.current_url()
        if any(hint in url.lower() for hint in _LOGIN_PATH_HINTS):
            return {"status": "session_invalid", "message": "登录态已失效，请重新登录", "url": url}

        text = ""
        try:
            text = await self._page.inner_text("body", timeout=5000)
        except Exception:
            pass
        title = ""
        try:
            title = await self._page.title()
        except Exception:
            pass

        blob = f"{title}\n{text}"
        if any(h in blob for h in _SUCCESS_HINTS):
            return {"status": "published", "message": "已发布", "url": url}
        if any(h in blob for h in _FAIL_HINTS):
            return {"status": "failed", "message": "页面出现发布失败提示", "url": url}

        # URL 离开发布编辑页通常意味着提交成功（小红书会跳到作品管理页）
        publish_url = PUBLISHER_URLS.get(self.platform, "")
        if publish_url and url and publish_url.rstrip("/") not in url.rstrip("/"):
            if "/publish" not in url and "/upload" not in url and "/post" not in url:
                return {"status": "published", "message": "已离开发布页，视为发布成功", "url": url}

        return {"status": "pending", "message": "仍在发布页，等待确认", "url": url}

    async def screenshot(self, quality: int = 60) -> str:
        """真实截图（同一会话、同一页面）。"""
        if not self.alive:
            return ""
        try:
            shot = await self._page.screenshot(type="jpeg", quality=quality)
            return base64.b64encode(shot).decode("ascii")
        except Exception as e:
            logger.warning(f"[publisher-session:{self.platform}] screenshot failed: {e}")
            return ""

    # ------------------------------------------------------------------
    # 关闭
    # ------------------------------------------------------------------

    async def _safe_close(self) -> None:
        try:
            if self._context:
                await self._context.close()
        except Exception as e:
            logger.debug(f"[publisher-session:{self.platform}] close context: {e}")
        try:
            if self._pw:
                await self._pw.stop()
        except Exception as e:
            logger.debug(f"[publisher-session:{self.platform}] stop playwright: {e}")
        self._context = None
        self._page = None
        self._pw = None

    async def close(self) -> None:
        async with self._lock:
            await self._safe_close()


_sessions: dict[str, PublisherSession] = {}


def get_publisher_session(platform: str) -> PublisherSession:
    """平台维度的进程内单例。"""
    if platform not in _sessions:
        _sessions[platform] = PublisherSession(platform)
    return _sessions[platform]


def host_to_platform(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    return PUBLISHER_HOSTS.get(host, "")


async def close_all_sessions() -> None:
    """应用退出时关闭所有发布会话（否则会残留 chromium 进程）。"""
    for platform, session in list(_sessions.items()):
        try:
            await session.close()
            logger.info(f"[publisher-session:{platform}] closed")
        except Exception as e:
            logger.warning(f"[publisher-session:{platform}] close failed: {e}")
    _sessions.clear()


async def check_publish_result(platform: str = "xiaohongshu") -> dict:
    """供 /api/workflows/{id}/publish/check 使用（不再依赖已移除的 MCP 模块）。"""
    session = _sessions.get(platform)
    if session is None:
        return {"status": "not_applicable", "message": "当前没有进行中的发布会话"}
    return await session.check_publish_state()
