"""BrowserClient：内置 Playwright 的浏览器自动化客户端（G3）。

职责（对齐 Playwright MCP 的 toolset 形态）：
- 域名白名单校验（单一事实源）：settings.browser_allowed_domains +
  运行时临时放行（TTL）。拒绝时返回 LLM 可读的结构化错误。
- 会话策略：支持多 profile 会话——profile_id 对应持久化 user_data_dir，
  保留登录态/cookies；无 profile_id 时用临时会话。
- 内置 Playwright：不再依赖外部 QR Worker 进程，同进程内直接调用。
- 审计：每个导航/操作动作回调 audit_sink（G4 注入 DB 落库；未注入则跳过）。

安全边界：白名单在「这一层」强制——Skill / MCP Server / 未来任何调用方
都经由此客户端。
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_PROFILE_BASE_DIR = Path(__file__).resolve().parents[2] / "data" / "browser_profiles"

_NEEDS_LOGIN_DOMAINS = {
    "feishu.cn", "open.feishu.cn",
    "accounts.feishu.cn",
    "docs.qq.com", "mail.qq.com",
    "slack.com", "notion.so",
}

# 审计回调签名：(action, domain, url, ok, detail) -> None
AuditSink = Callable[[str, str, str, bool, str], Awaitable[None]]


class DomainNotAllowedError(RuntimeError):
    """域名不在白名单。message 面向 LLM（含放行指引）。"""

    def __init__(self, domain: str, allowed: list[str]) -> None:
        self.domain = domain
        super().__init__(
            f"DOMAIN_NOT_ALLOWED: 域名 {domain} 不在浏览器白名单。"
            f"当前白名单: {allowed}。请询问用户是否放行该域名；"
            f"用户同意后调用 browser_allow_domain（user_confirmed=true）放行并重试，"
            f"或将其加入环境变量 BROWSER_ALLOWED_DOMAINS 后重启。"
        )


class BrowserClient:
    """内置 Playwright 的浏览器自动化客户端（单例，get_browser_client()）。

    G3 改造：移除 QR Worker 依赖，同进程内直接调用 Playwright。
    支持多 profile 会话：profile_id 对应持久化 user_data_dir，保留登录态。
    """

    def __init__(self) -> None:
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._playwright: Any = None
        self._current_url: str = ""
        self._current_profile_id: str | None = None
        self._temp_allowed: dict[str, float] = {}  # domain -> 过期时间（monotonic）
        self._audit_sink: AuditSink | None = None
        self._lock = asyncio.Lock()
        self._initialized = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    @staticmethod
    def _is_login_domain(url: str) -> bool:
        """判断 URL 是否属于需要登录才能使用的域名。"""
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError:
            return False
        for d in _NEEDS_LOGIN_DOMAINS:
            if host == d or host.endswith("." + d):
                return True
        return False

    @staticmethod
    def _profile_dir(profile_id: str) -> Path:
        """获取 profile 持久化目录。"""
        safe_name = profile_id.replace("/", "_").replace("\\", "_")
        return _PROFILE_BASE_DIR / safe_name

    async def _ensure_initialized(
        self,
        profile_id: str | None = None,
        headless: bool | None = None,
    ) -> bool:
        """延迟初始化 Playwright 浏览器实例。

        Args:
            profile_id: 持久化 Profile ID，非空时使用 launch_persistent_context
                        加载 data/browser_profiles/{profile_id}/ 保留登录态。
            headless: 是否无头模式。None 时自动判断：需要登录的域名用 False。
        """
        if self._initialized and self._browser:
            if profile_id != self._current_profile_id:
                await self._switch_profile(profile_id, headless)
            elif not self._browser.is_connected():
                await self._cleanup()
                return await self._ensure_initialized(profile_id, headless)
            return True

        if self._initialized:
            return True

        async with self._lock:
            if self._initialized:
                if profile_id != self._current_profile_id:
                    await self._switch_profile(profile_id, headless)
                return True
            try:
                from playwright.async_api import async_playwright

                self._playwright = await asyncio.wait_for(
                    async_playwright().start(), timeout=20.0
                )

                if profile_id:
                    user_data_dir = str(self._profile_dir(profile_id))
                    user_data_dir_path = Path(user_data_dir)
                    user_data_dir_path.mkdir(parents=True, exist_ok=True)
                    actual_headless = headless if headless is not None else False
                    self._context = await asyncio.wait_for(
                        self._playwright.chromium.launch_persistent_context(
                            user_data_dir=user_data_dir,
                            headless=actual_headless,
                            viewport={"width": 1280, "height": 800},
                            device_scale_factor=1,
                            ignore_https_errors=True,
                            args=[
                                "--no-sandbox",
                                "--disable-gpu",
                                "--disable-dev-shm-usage",
                                "--font-render-hinting=none",
                            ],
                            user_agent=(
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/130.0.0.0 Safari/537.36"
                            ),
                        ),
                        timeout=20.0,
                    )
                    self._browser = self._context
                    self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()
                    self._current_profile_id = profile_id
                    logger.info(
                        f"[BrowserClient] Playwright persistent context initialized "
                        f"(profile={profile_id}, headless={actual_headless}, "
                        f"user_data_dir={user_data_dir})"
                    )
                else:
                    actual_headless = headless if headless is not None else True
                    self._browser = await asyncio.wait_for(
                        self._playwright.chromium.launch(
                            headless=actual_headless,
                            args=[
                                "--no-sandbox",
                                "--disable-gpu",
                                "--disable-dev-shm-usage",
                                "--font-render-hinting=none",
                            ],
                        ),
                        timeout=20.0,
                    )
                    self._context = await self._browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        device_scale_factor=1,
                        ignore_https_errors=True,
                        user_agent=(
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/130.0.0.0 Safari/537.36"
                        ),
                    )
                    self._page = await self._context.new_page()
                    self._current_profile_id = None
                    logger.info(
                        f"[BrowserClient] Playwright browser initialized "
                        f"(headless={actual_headless})"
                    )

                self._initialized = True
                return True
            except asyncio.TimeoutError:
                logger.error("[BrowserClient] Initialization timed out (20s)")
                await self._cleanup()
                return False
            except Exception as e:
                logger.exception("[BrowserClient] Initialization failed")
                await self._cleanup()
                return False

    async def _switch_profile(
        self,
        profile_id: str | None,
        headless: bool | None = None,
    ) -> None:
        """切换到不同的 profile（关闭当前浏览器，重新初始化）。"""
        logger.info(
            f"[BrowserClient] Switching profile: "
            f"{self._current_profile_id!r} -> {profile_id!r}"
        )
        await self._cleanup()
        self._initialized = False
        await self._ensure_initialized(profile_id, headless)

    async def _cleanup(self) -> None:
        """清理资源。

        launch_persistent_context 模式下，_browser 就是 _context，
        关闭 _context 即可（不需要再单独关 _browser）。
        launch + new_context 模式下，需要分别关闭 page、context、browser。
        """
        try:
            if self._current_profile_id:
                if self._context:
                    await self._context.close()
            else:
                if self._page:
                    await self._page.close()
                if self._context:
                    await self._context.close()
                if self._browser:
                    await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception as e:
            logger.warning(f"[BrowserClient] Cleanup error: {e}")
        finally:
            self._browser = None
            self._context = None
            self._page = None
            self._playwright = None
            self._initialized = False
            self._current_profile_id = None

    async def shutdown(self) -> None:
        """关闭浏览器（应用退出时调用）。"""
        await self._cleanup()
        logger.info("[BrowserClient] Shutdown complete")

    # ------------------------------------------------------------------
    # 审计
    # ------------------------------------------------------------------

    def set_audit_sink(self, sink: AuditSink | None) -> None:
        """G4 注入审计回调（DB 落库）；未注入则不审计。"""
        self._audit_sink = sink

    async def _audit(self, action: str, url: str, ok: bool, detail: str = "") -> None:
        if not self._audit_sink:
            return
        try:
            domain = (urlparse(url).hostname or "") if url else ""
            await self._audit_sink(action, domain, url, ok, detail)
        except Exception as e:
            logger.warning(f"browser audit sink failed: {e}")

    def _audit_bg(self, action: str, url: str, ok: bool, detail: str = "") -> None:
        """fire-and-forget 审计（不阻塞主流程）。"""
        asyncio.create_task(self._audit(action, url, ok, detail))

    # ------------------------------------------------------------------
    # 域名白名单
    # ------------------------------------------------------------------

    def check_domain(self, url: str) -> None:
        """校验 URL 域名；不在白名单抛 DomainNotAllowedError。"""
        try:
            host = (urlparse(url).hostname or "").lower()
        except ValueError as e:
            raise DomainNotAllowedError(f"invalid-url:{url}", []) from e
        if not host:
            raise DomainNotAllowedError(url, self.list_domains()["allowed"])
        now = time.monotonic()
        expired = [d for d, exp in self._temp_allowed.items() if exp <= now]
        for d in expired:
            self._temp_allowed.pop(d, None)
        candidates = self._static_domains() + list(self._temp_allowed.keys())
        for dom in candidates:
            dom = dom.lower().strip()
            if host == dom or host.endswith("." + dom):
                return
        raise DomainNotAllowedError(host, self.list_domains()["allowed"])

    def _static_domains(self) -> list[str]:
        try:
            from app.config import get_settings
            return get_settings().browser_allowed_domain_list
        except Exception:
            return ["xiaohongshu.com"]

    def allow_domain_temporary(self, domain: str, ttl_minutes: int = 60) -> dict:
        """运行时临时放行域名（带 TTL，进程内生效）。"""
        domain = domain.strip().lower()
        if not domain or "/" in domain or " " in domain:
            raise ValueError(f"invalid domain: {domain!r}")
        ttl = max(1, min(int(ttl_minutes), 24 * 60))
        self._temp_allowed[domain] = time.monotonic() + ttl * 60
        logger.info(f"Browser domain temporarily allowed: {domain} (ttl={ttl}min)")
        return self.list_domains()

    def list_domains(self) -> dict:
        now = time.monotonic()
        temp = [
            {"domain": d, "expires_in_min": round((exp - now) / 60, 1)}
            for d, exp in sorted(self._temp_allowed.items(), key=lambda kv: kv[1])
            if exp > now
        ]
        return {"allowed": self._static_domains(), "temporary": temp}

    # ------------------------------------------------------------------
    # 高层操作（Skill / MCP 共用入口）
    # ------------------------------------------------------------------

    async def navigate(self, url: str, profile_id: str | None = None) -> dict:
        """导航到指定 URL。

        Args:
            url: 目标网址。
            profile_id: 持久化 Profile ID（如 "feishu_main"）。
                        非空时使用 launch_persistent_context 加载对应目录，
                        保留登录态/cookies。飞书等需要登录的站点应传此参数。
                        留空则使用临时会话（headless）。
        """
        url = (url or "").strip()
        try:
            self.check_domain(url)
        except DomainNotAllowedError:
            self._audit_bg("navigate", url, False, "DOMAIN_NOT_ALLOWED")
            raise

        needs_login = self._is_login_domain(url)

        if needs_login and not profile_id:
            host = urlparse(url).hostname or ""
            profile_id = host.replace(".", "_")
            logger.info(
                f"[BrowserClient] Auto-assigning profile_id={profile_id!r} "
                f"for login-required domain {host}"
            )

        headless = not needs_login

        if not await self._ensure_initialized(profile_id=profile_id, headless=headless):
            return {"ok": False, "error": "BROWSER_INIT_FAILED: 无法启动浏览器"}

        try:
            response = await self._page.goto(url, wait_until="domcontentloaded", timeout=30000)
            self._current_url = url
            result = {
                "ok": True,
                "url": self._page.url,
                "title": await self._page.title(),
                "status": response.status if response else 0,
                "profile_id": profile_id,
                "headless": headless,
            }
            if needs_login:
                result["hint"] = (
                    "此页面需要登录，浏览器以有头模式(headless=False)打开，"
                    "请在弹出的浏览器窗口中完成登录。登录后 cookies 会自动保存到 "
                    f"profile={profile_id}，下次访问无需重新登录。"
                )
            self._audit_bg("navigate", url, True, "")
            return result
        except Exception as e:
            self._audit_bg("navigate", url, False, str(e))
            return {"ok": False, "error": f"NAVIGATE_FAILED: {e}"}

    async def snapshot(self) -> dict:
        """获取页面快照（可访问性树 + DOM 结构）。"""
        if not await self._ensure_initialized():
            return {"ok": False, "error": "浏览器未初始化"}
        try:
            accessibility_snapshot = await self._page.accessibility.snapshot()
            url = self._page.url
            title = await self._page.title()
            return {
                "ok": True,
                "url": url,
                "title": title,
                "accessibility_tree": accessibility_snapshot,
            }
        except Exception as e:
            return {"ok": False, "error": f"SNAPSHOT_FAILED: {e}"}

    async def act(
        self,
        action: str,
        ref: str | None = None,
        text: str | None = None,
        key: str | None = None,
        nav_seq: int | None = None,
    ) -> dict:
        """执行页面操作（click/fill/press 等）。"""
        if not await self._ensure_initialized():
            return {"ok": False, "error": "浏览器未初始化"}

        url = self._page.url
        try:
            if action == "click":
                if ref:
                    locator = self._page.locator(ref)
                    await locator.click(timeout=10000)
                else:
                    return {"ok": False, "error": "CLICK 需要 ref 参数（CSS 选择器）"}
            elif action == "fill":
                if ref and text is not None:
                    locator = self._page.locator(ref)
                    await locator.fill(text, timeout=10000)
                else:
                    return {"ok": False, "error": "FILL 需要 ref 和 text 参数"}
            elif action == "press":
                if key:
                    await self._page.keyboard.press(key)
                else:
                    return {"ok": False, "error": "PRESS 需要 key 参数"}
            elif action == "select":
                if ref and text is not None:
                    locator = self._page.locator(ref)
                    await locator.select_option(text, timeout=10000)
                else:
                    return {"ok": False, "error": "SELECT 需要 ref 和 text 参数"}
            elif action == "scroll":
                if ref:
                    locator = self._page.locator(ref)
                    await locator.scroll_into_view_if_needed(timeout=5000)
                else:
                    await self._page.evaluate("window.scrollBy(0, window.innerHeight * 0.8)")
            elif action == "hover":
                if ref:
                    locator = self._page.locator(ref)
                    await locator.hover(timeout=5000)
                else:
                    return {"ok": False, "error": "HOVER 需要 ref 参数"}
            else:
                return {"ok": False, "error": f"未知操作: {action}"}

            self._audit_bg(f"act:{action}", url, True, "")
            return {"ok": True, "url": self._page.url}
        except Exception as e:
            self._audit_bg(f"act:{action}", url, False, str(e))
            return {"ok": False, "error": f"{action.upper()}_FAILED: {e}"}

    async def screenshot(self, full_page: bool = False, quality: int | None = None) -> dict:
        """截取当前页面截图，返回 base64 编码的图片。"""
        if not await self._ensure_initialized():
            return {"ok": False, "error": "浏览器未初始化"}

        try:
            screenshot_type = "jpeg" if quality else "png"
            screenshot_bytes = await self._page.screenshot(
                full_page=full_page,
                type=screenshot_type,
                quality=quality,
            )
            b64 = base64.b64encode(screenshot_bytes).decode("ascii")
            return {
                "ok": True,
                "screenshot_base64": b64,
                "url": self._page.url,
                "title": await self._page.title(),
            }
        except Exception as e:
            return {"ok": False, "error": f"SCREENSHOT_FAILED: {e}"}

    async def evaluate(self, js: str) -> dict:
        """执行 JavaScript 表达式。"""
        if not await self._ensure_initialized():
            return {"ok": False, "error": "浏览器未初始化"}
        try:
            result = await self._page.evaluate(js)
            return {"ok": True, "data": result}
        except Exception as e:
            return {"ok": False, "error": f"EVALUATE_FAILED: {e}"}

    async def extract(self, selector: str | None = None) -> dict:
        """提取页面文本内容。"""
        if not await self._ensure_initialized():
            return {"ok": False, "error": "浏览器未初始化"}
        try:
            if selector:
                elements = await self._page.query_selector_all(selector)
                texts = []
                for el in elements:
                    text = await el.inner_text()
                    texts.append(text.strip())
                content = "\n".join(texts)
            else:
                content = await self._page.inner_text("body")
            return {
                "ok": True,
                "text": content,
                "url": self._page.url,
                "title": await self._page.title(),
            }
        except Exception as e:
            return {"ok": False, "error": f"EXTRACT_FAILED: {e}"}

    async def tabs(self, op: str | None = None, index: int | None = None) -> dict:
        """标签页管理。"""
        if not await self._ensure_initialized():
            return {"ok": False, "error": "浏览器未初始化"}
        try:
            pages = self._context.pages
            tabs_info = []
            for i, p in enumerate(pages):
                tabs_info.append({
                    "index": i,
                    "url": p.url,
                    "title": await p.title(),
                    "active": p == self._page,
                })
            return {"ok": True, "tabs": tabs_info}
        except Exception as e:
            return {"ok": False, "error": f"TABS_FAILED: {e}"}

    async def list_sessions(self) -> dict:
        """列出会话（兼容接口，始终返回单个会话）。"""
        return {
            "ok": True,
            "sessions": [{
                "session_id": "default",
                "url": self._current_url if self._page else "",
                "created_at": time.time(),
            }] if self._initialized else []
        }

    async def close(self) -> dict:
        """关闭当前会话/页面。"""
        if self._page:
            try:
                await self._page.close()
            except Exception:
                pass
            self._page = None
        self._current_url = ""
        return {"ok": True, "message": "会话已关闭"}

    async def health_check(self) -> dict:
        """健康检查。"""
        if self._initialized and self._browser and self._browser.is_connected():
            return {"status": "ok", "engine": "playwright-builtin"}
        return {"status": "offline", "engine": "playwright-builtin"}


_client: BrowserClient | None = None


def get_browser_client() -> BrowserClient:
    """全局单例。"""
    global _client
    if _client is None:
        _client = BrowserClient()
    return _client