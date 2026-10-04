"""多平台发布服务：基于 Scrapling StealthyFetcher 的反检测浏览器自动化发布。

核心流程：
1. 加载平台 storageState（扫码登录时保存的 cookies）
2. 用 StealthyFetcher 打开创作者中心发布页（page_setup 注入 cookies）
3. page_action 回调内自动填写标题/内容/标签、上传图片
4. 点击发布按钮
5. 返回发布结果（成功/失败 + 截图）

设计决策：
- 使用 Scrapling StealthyFetcher 而非裸 Playwright，因为：
  - 内置反检测（指纹伪装、stealth 注入）
  - 自动重试 + Cloudflare 绕过
  - 与 Spider 共享同一套 cookies/storageState 机制
- 使用 page_action 回调而非分步 API，因为：
  - 发布是原子操作，中间状态不需要暴露给前端
  - 减少网络往返，一次调用完成全部填写+提交
- 半自动模式（默认）：只填写内容不点击发布按钮，等用户确认后手动点
- 全自动模式：填写+点击发布一步完成
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from app.services.platform_adapter import adapt_tags, check_platform_limits, get_platform_spec

logger = logging.getLogger(__name__)

STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage_states"

PUBLISHER_URLS = {
    "xiaohongshu": "https://creator.xiaohongshu.com/publish/publish",
    "douyin": "https://creator.douyin.com/creator-micro/content/upload",
    "kuaishou": "https://creator.kuaishou.com/publish/video",
    "bilibili": "https://member.bilibili.com/platform/upload/video/frame",
    "zhihu": "https://www.zhihu.com/creator/writer",
    "wechat": "https://channels.weixin.qq.com/platform/post",
}


def _load_cookies_from_storage(platform: str) -> list[dict]:
    """从 storageState JSON 加载 cookies 列表。"""
    storage_path = STORAGE_DIR / f"{platform}.json"
    if not storage_path.exists():
        return []
    try:
        state = json.loads(storage_path.read_text(encoding="utf-8"))
        cookies = []
        for c in state.get("cookies", []):
            cookie: dict[str, Any] = {
                "name": c.get("name", ""),
                "value": c.get("value", ""),
            }
            for key in ("domain", "path", "url", "expires", "httpOnly", "secure", "sameSite"):
                if c.get(key) is not None:
                    cookie[key] = c[key]
            cookies.append(cookie)
        logger.info(f"[publisher] loaded {len(cookies)} cookies from {storage_path.name}")
        return cookies
    except Exception as e:
        logger.warning(f"[publisher] failed to load storageState for {platform}: {e}")
        return []


def _save_temp_images(images_base64: list[str]) -> list[str]:
    """将 base64 图片列表写入临时文件，返回文件路径列表。"""
    paths = []
    for i, b64 in enumerate(images_base64):
        try:
            data = base64.b64decode(b64)
            suffix = ".png"
            if data[:3] == b"\xff\xd8\xff":
                suffix = ".jpg"
            elif data[:4] == b"RIFF":
                suffix = ".webp"
            fd, path = tempfile.mkstemp(suffix=suffix, prefix=f"publish_img_{i}_")
            os.write(fd, data)
            os.close(fd)
            paths.append(path)
        except Exception as e:
            logger.warning(f"[publisher] failed to write temp image {i}: {e}")
    return paths


def _cleanup_temp_images(paths: list[str]) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 平台特定的 page_action 实现
# ---------------------------------------------------------------------------

def _xiaohongshu_page_action(
    title: str,
    content: str,
    tags: list[str],
    image_paths: list[str],
    auto_submit: bool,
) -> Any:
    """小红书发布页自动化：填写标题/正文/标签 + 上传图片 + 可选点击发布。"""
    def action(page: Any) -> None:
        import time as _t
        _t.sleep(2)

        try:
            title_input = page.locator("input[placeholder*='标题'], input[placeholder*='填写标题'], #title, [class*='title'] input").first
            title_input.wait_for(state="visible", timeout=8000)
            title_input.fill(title)
            _t.sleep(0.3)
        except Exception as e:
            logger.warning(f"[publisher:xhs] title fill failed: {e}")

        try:
            content_editor = page.locator("[contenteditable='true'], [class*='ql-editor'], [class*='content'] [contenteditable], textarea[placeholder*='正文']").first
            content_editor.wait_for(state="visible", timeout=8000)
            content_editor.click()
            _t.sleep(0.2)
            full_text = content
            if tags:
                tag_str = " ".join(f"#{t}" for t in tags)
                full_text = f"{content}\n\n{tag_str}"
            page.keyboard.type(full_text, delay=30)
            _t.sleep(0.5)
        except Exception as e:
            logger.warning(f"[publisher:xhs] content fill failed: {e}")

        if image_paths:
            try:
                upload_input = page.locator("input[type='file']").first
                upload_input.wait_for(state="attached", timeout=5000)
                upload_input.set_input_files(image_paths)
                _t.sleep(3)
            except Exception as e:
                logger.warning(f"[publisher:xhs] image upload failed: {e}")

        if auto_submit:
            try:
                _t.sleep(1)
                publish_btn = page.locator("button:has-text('发布'), button:has-text('发布笔记'), [class*='publish'] button").first
                publish_btn.wait_for(state="visible", timeout=5000)
                publish_btn.click()
                _t.sleep(3)
            except Exception as e:
                logger.warning(f"[publisher:xhs] publish click failed: {e}")

    return action


def _douyin_page_action(
    title: str,
    content: str,
    tags: list[str],
    image_paths: list[str],
    auto_submit: bool,
) -> Any:
    """抖音创作者中心发布自动化。"""
    def action(page: Any) -> None:
        import time as _t
        _t.sleep(2)

        if image_paths:
            try:
                upload_input = page.locator("input[type='file']").first
                upload_input.wait_for(state="attached", timeout=8000)
                upload_input.set_input_files(image_paths[:1])
                _t.sleep(5)
            except Exception as e:
                logger.warning(f"[publisher:dy] video upload failed: {e}")

        try:
            title_input = page.locator("input[placeholder*='标题'], input[placeholder*='作品描述'], [class*='title'] input, .editor-kit-title-input input").first
            title_input.wait_for(state="visible", timeout=8000)
            full_title = title
            if tags:
                tag_str = " ".join(f"#{t}" for t in tags)
                full_title = f"{title} {tag_str}"
            title_input.fill(full_title)
            _t.sleep(0.3)
        except Exception as e:
            logger.warning(f"[publisher:dy] title fill failed: {e}")

        try:
            desc_editor = page.locator("[contenteditable='true'], textarea[placeholder*='描述'], .editor-kit-textarea, [class*='desc'] textarea").first
            desc_editor.wait_for(state="visible", timeout=5000)
            desc_editor.click()
            _t.sleep(0.2)
            page.keyboard.type(content, delay=30)
            _t.sleep(0.5)
        except Exception as e:
            logger.warning(f"[publisher:dy] desc fill failed: {e}")

        if auto_submit:
            try:
                _t.sleep(1)
                publish_btn = page.locator("button:has-text('发布'), button:has-text('发布视频')").first
                publish_btn.wait_for(state="visible", timeout=5000)
                publish_btn.click()
                _t.sleep(3)
            except Exception as e:
                logger.warning(f"[publisher:dy] publish click failed: {e}")

    return action


def _bilibili_page_action(
    title: str,
    content: str,
    tags: list[str],
    image_paths: list[str],
    auto_submit: bool,
) -> Any:
    """B站创作者中心发布自动化。"""
    def action(page: Any) -> None:
        import time as _t
        _t.sleep(2)

        if image_paths:
            try:
                upload_input = page.locator("input[type='file']").first
                upload_input.wait_for(state="attached", timeout=8000)
                upload_input.set_input_files(image_paths[:1])
                _t.sleep(5)
            except Exception as e:
                logger.warning(f"[publisher:bili] video upload failed: {e}")

        try:
            title_input = page.locator("input[placeholder*='标题'], input[placeholder*='输入标题'], [class*='title'] input, #title").first
            title_input.wait_for(state="visible", timeout=8000)
            title_input.fill(title)
            _t.sleep(0.3)
        except Exception as e:
            logger.warning(f"[publisher:bili] title fill failed: {e}")

        try:
            desc_editor = page.locator("[contenteditable='true'], textarea[placeholder*='简介'], [class*='desc'] textarea, .desc-input textarea").first
            desc_editor.wait_for(state="visible", timeout=5000)
            desc_editor.click()
            _t.sleep(0.2)
            full_desc = content
            if tags:
                tag_str = " ".join(tags)
                full_desc = f"{content}\n\n{tag_str}"
            page.keyboard.type(full_desc, delay=30)
            _t.sleep(0.5)
        except Exception as e:
            logger.warning(f"[publisher:bili] desc fill failed: {e}")

        try:
            tag_input = page.locator("input[placeholder*='标签'], input[placeholder*='tag'], [class*='tag'] input").first
            tag_input.wait_for(state="visible", timeout=3000)
            for tag in tags[:10]:
                tag_input.fill(tag)
                _t.sleep(0.3)
                page.keyboard.press("Enter")
                _t.sleep(0.3)
        except Exception as e:
            logger.warning(f"[publisher:bili] tag fill failed: {e}")

        if auto_submit:
            try:
                _t.sleep(1)
                publish_btn = page.locator("button:has-text('发布'), button:has-text('投稿')").first
                publish_btn.wait_for(state="visible", timeout=5000)
                publish_btn.click()
                _t.sleep(3)
            except Exception as e:
                logger.warning(f"[publisher:bili] publish click failed: {e}")

    return action


def _zhihu_page_action(
    title: str,
    content: str,
    tags: list[str],
    image_paths: list[str],
    auto_submit: bool,
) -> Any:
    """知乎创作中心发布自动化。"""
    def action(page: Any) -> None:
        import time as _t
        _t.sleep(2)

        try:
            title_input = page.locator("input[placeholder*='标题'], [class*='title'] input, textarea[placeholder*='标题']").first
            title_input.wait_for(state="visible", timeout=8000)
            title_input.fill(title)
            _t.sleep(0.3)
        except Exception as e:
            logger.warning(f"[publisher:zhihu] title fill failed: {e}")

        try:
            content_editor = page.locator("[contenteditable='true'], .ProseMirror, [class*='editor'] [contenteditable]").first
            content_editor.wait_for(state="visible", timeout=8000)
            content_editor.click()
            _t.sleep(0.2)
            page.keyboard.type(content, delay=30)
            _t.sleep(0.5)
        except Exception as e:
            logger.warning(f"[publisher:zhihu] content fill failed: {e}")

        if image_paths:
            try:
                upload_input = page.locator("input[type='file'][accept*='image']").first
                upload_input.wait_for(state="attached", timeout=5000)
                upload_input.set_input_files(image_paths)
                _t.sleep(3)
            except Exception as e:
                logger.warning(f"[publisher:zhihu] image upload failed: {e}")

        try:
            topic_input = page.locator("input[placeholder*='话题'], input[placeholder*='主题'], [class*='topic'] input").first
            topic_input.wait_for(state="visible", timeout=3000)
            for tag in tags[:5]:
                topic_input.fill(tag)
                _t.sleep(0.5)
                suggestion = page.locator("[class*='suggestion'] li, [class*='topic-item'], [class*='dropdown'] li").first
                suggestion.click()
                _t.sleep(0.3)
        except Exception as e:
            logger.warning(f"[publisher:zhihu] topic fill failed: {e}")

        if auto_submit:
            try:
                _t.sleep(1)
                publish_btn = page.locator("button:has-text('发布'), button:has-text('发表')").first
                publish_btn.wait_for(state="visible", timeout=5000)
                publish_btn.click()
                _t.sleep(3)
            except Exception as e:
                logger.warning(f"[publisher:zhihu] publish click failed: {e}")

    return action


def _kuaishou_page_action(
    title: str,
    content: str,
    tags: list[str],
    image_paths: list[str],
    auto_submit: bool,
) -> Any:
    """快手创作者中心发布自动化。"""
    def action(page: Any) -> None:
        import time as _t
        _t.sleep(2)

        if image_paths:
            try:
                upload_input = page.locator("input[type='file']").first
                upload_input.wait_for(state="attached", timeout=8000)
                upload_input.set_input_files(image_paths[:1])
                _t.sleep(5)
            except Exception as e:
                logger.warning(f"[publisher:ks] video upload failed: {e}")

        try:
            title_input = page.locator("input[placeholder*='标题'], input[placeholder*='描述'], [class*='title'] input").first
            title_input.wait_for(state="visible", timeout=8000)
            full_title = title
            if tags:
                tag_str = " ".join(f"#{t}" for t in tags)
                full_title = f"{title} {tag_str}"
            title_input.fill(full_title)
            _t.sleep(0.3)
        except Exception as e:
            logger.warning(f"[publisher:ks] title fill failed: {e}")

        try:
            desc_editor = page.locator("[contenteditable='true'], textarea[placeholder*='描述'], [class*='desc'] textarea").first
            desc_editor.wait_for(state="visible", timeout=5000)
            desc_editor.click()
            _t.sleep(0.2)
            page.keyboard.type(content, delay=30)
            _t.sleep(0.5)
        except Exception as e:
            logger.warning(f"[publisher:ks] desc fill failed: {e}")

        if auto_submit:
            try:
                _t.sleep(1)
                publish_btn = page.locator("button:has-text('发布'), button:has-text('发布作品')").first
                publish_btn.wait_for(state="visible", timeout=5000)
                publish_btn.click()
                _t.sleep(3)
            except Exception as e:
                logger.warning(f"[publisher:ks] publish click failed: {e}")

    return action


def _wechat_page_action(
    title: str,
    content: str,
    tags: list[str],
    image_paths: list[str],
    auto_submit: bool,
) -> Any:
    """微信视频号创作者中心发布自动化。"""
    def action(page: Any) -> None:
        import time as _t
        _t.sleep(2)

        if image_paths:
            try:
                upload_input = page.locator("input[type='file']").first
                upload_input.wait_for(state="attached", timeout=8000)
                upload_input.set_input_files(image_paths[:1])
                _t.sleep(5)
            except Exception as e:
                logger.warning(f"[publisher:wx] video upload failed: {e}")

        try:
            title_input = page.locator("input[placeholder*='标题'], input[placeholder*='描述'], [class*='title'] input").first
            title_input.wait_for(state="visible", timeout=8000)
            title_input.fill(title)
            _t.sleep(0.3)
        except Exception as e:
            logger.warning(f"[publisher:wx] title fill failed: {e}")

        try:
            desc_editor = page.locator("[contenteditable='true'], textarea[placeholder*='描述'], [class*='desc'] textarea").first
            desc_editor.wait_for(state="visible", timeout=5000)
            desc_editor.click()
            _t.sleep(0.2)
            full_desc = content
            if tags:
                tag_str = " ".join(f"#{t}" for t in tags)
                full_desc = f"{content}\n\n{tag_str}"
            page.keyboard.type(full_desc, delay=30)
            _t.sleep(0.5)
        except Exception as e:
            logger.warning(f"[publisher:wx] desc fill failed: {e}")

        if auto_submit:
            try:
                _t.sleep(1)
                publish_btn = page.locator("button:has-text('发布'), button:has-text('发表')").first
                publish_btn.wait_for(state="visible", timeout=5000)
                publish_btn.click()
                _t.sleep(3)
            except Exception as e:
                logger.warning(f"[publisher:wx] publish click failed: {e}")

    return action


PLATFORM_ACTIONS = {
    "xiaohongshu": _xiaohongshu_page_action,
    "douyin": _douyin_page_action,
    "kuaishou": _kuaishou_page_action,
    "bilibili": _bilibili_page_action,
    "zhihu": _zhihu_page_action,
    "wechat": _wechat_page_action,
}


async def publish_to_platform(
    platform: str,
    title: str,
    content: str,
    tags: list[str],
    images_base64: list[str] | None = None,
    auto_submit: bool = False,
) -> dict:
    """使用 Scrapling StealthyFetcher 执行平台发布。

    返回:
        {
            "ok": bool,
            "platform": str,
            "status": "awaiting_manual" | "submitted" | "failed",
            "message": str,
            "screenshot_base64": str,
            "url": str,
        }
    """
    try:
        from scrapling.fetchers import StealthyFetcher
    except ImportError:
        return {
            "ok": False,
            "platform": platform,
            "status": "failed",
            "message": "Scrapling 未安装，请运行 pip install scrapling",
            "screenshot_base64": "",
            "url": "",
        }

    url = PUBLISHER_URLS.get(platform)
    if not url:
        return {
            "ok": False,
            "platform": platform,
            "status": "failed",
            "message": f"不支持的平台: {platform}",
            "screenshot_base64": "",
            "url": "",
        }

    action_fn = PLATFORM_ACTIONS.get(platform)
    if not action_fn:
        return {
            "ok": False,
            "platform": platform,
            "status": "failed",
            "message": f"平台 {platform} 的发布自动化尚未实现",
            "screenshot_base64": "",
            "url": "",
        }

    spec = get_platform_spec(platform)
    adapted_tags = adapt_tags(tags, platform)

    limit_check = check_platform_limits(title, content, platform)
    if not limit_check["ok"]:
        logger.warning(f"[publisher:{platform}] platform limits exceeded: {limit_check['issues']}")

    if spec.title_max > 0 and len(title) > spec.title_max:
        title = title[:spec.title_max]
    if len(content) > spec.content_max:
        content = content[:spec.content_max]

    cookies = _load_cookies_from_storage(platform)
    if not cookies:
        logger.warning(f"[publisher:{platform}] no cookies found, publishing may fail (need login first)")

    image_paths: list[str] = []
    if images_base64:
        image_paths = _save_temp_images(images_base64)

    page_action_fn = action_fn(title, content, adapted_tags, image_paths, auto_submit)

    screenshot_b64 = ""
    final_url = ""
    status = "failed"
    message = ""
    _captured_screenshot: list[str] = [""]

    try:
        def _run_publish() -> Any:
            kwargs: dict[str, Any] = {
                "headless": True,
                "network_idle": True,
                "timeout": 60000,
                "wait": 3000,
                "google_search": False,
                "page_action": page_action_fn,
            }
            if cookies:
                _cookies = cookies

                def _inject_cookies(page: Any) -> None:
                    try:
                        page.context.add_cookies(_cookies)
                    except Exception as e:
                        logger.warning(f"[publisher] page_setup add_cookies failed: {e}")

                kwargs["page_setup"] = _inject_cookies
                kwargs["cookies"] = cookies

            response = StealthyFetcher.fetch(url, **kwargs)

            try:
                page = response.page if hasattr(response, 'page') else None
                if page:
                    shot_bytes = page.screenshot(type="jpeg", quality=60)
                    _captured_screenshot[0] = base64.b64encode(shot_bytes).decode("ascii")
            except Exception as e:
                logger.warning(f"[publisher] in-page screenshot failed: {e}")

            return response

        response = await asyncio.get_event_loop().run_in_executor(None, _run_publish)

        final_url = response.url if hasattr(response, "url") else url
        status = "awaiting_manual" if not auto_submit else "submitted"
        message = (
            "内容已填写完成，请在浏览器中确认并点击发布按钮"
            if not auto_submit
            else "已提交发布，请到平台确认"
        )

        screenshot_b64 = _captured_screenshot[0]
        if not screenshot_b64:
            try:
                from playwright.sync_api import sync_playwright
                pw = sync_playwright().start()
                browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                ctx = browser.new_context(viewport={"width": 1280, "height": 800})
                if cookies:
                    ctx.add_cookies(cookies)
                pg = ctx.new_page()
                pg.goto(final_url, wait_until="domcontentloaded", timeout=15000)
                time.sleep(1)
                shot_bytes = pg.screenshot(type="jpeg", quality=60)
                screenshot_b64 = base64.b64encode(shot_bytes).decode("ascii")
                pg.close()
                ctx.close()
                browser.close()
                pw.stop()
            except Exception as e:
                logger.warning(f"[publisher] fallback screenshot failed: {e}")

    except Exception as e:
        logger.error(f"[publisher:{platform}] publish failed: {e}", exc_info=True)
        status = "failed"
        message = f"发布失败: {e}"
    finally:
        _cleanup_temp_images(image_paths)

    return {
        "ok": status != "failed",
        "platform": platform,
        "status": status,
        "message": message,
        "screenshot_base64": screenshot_b64,
        "url": final_url,
    }