"""通用浏览器自动化管理 API + 对外 MCP Server（G4）。

三个职责：
1. 域名白名单管理（GET/POST /api/browser/domains）—— 临时放行任意网站
   （带 TTL，默认 60 分钟），是「任意网站可自动化」的运行时入口
2. 审计查询（GET /api/browser/audit）—— 浏览器动作审计日志
3. 对外 MCP Server（POST /api/mcp/browser）—— 轻量 JSON-RPC 2.0 实现
   （MCP Streamable HTTP 子集：initialize / tools/list / tools/call / ping），
   Claude Code / Cursor 等外部 MCP 客户端可直接连接，能力与内部
   chat_agent 的 browser_* Skill 同源（同一 BrowserClient + 白名单 + 审计）

安全：
- 域名/审计 API 走 get_current_user（登录用户）
- MCP 端点走 Bearer token（settings.mcp_browser_token；为空则启动时自动生成）
- 白名单在 BrowserClient 单点强制：无论 agent 还是 MCP 调用都过同一道门
"""

from __future__ import annotations

import asyncio
import base64
import contextvars
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.models import BrowserAuditLog
from app.db.session import get_db
from app.tools.browser.client import DomainNotAllowedError, get_browser_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/browser", tags=["browser"])

# ---------------------------------------------------------------------------
# 审计 sink：注入 BrowserClient（main.py startup 调用 install_audit_sink）
# ---------------------------------------------------------------------------

# 当前调用来源（agent / mcp）。MCP 端点内 set("mcp")；
# audit 的 fire-and-forget task 会继承该 context。
_current_source: contextvars.ContextVar[str] = contextvars.ContextVar(
    "browser_audit_source", default="agent"
)


async def _audit_sink(action: str, domain: str, url: str, ok: bool, detail: str) -> None:
    """BrowserClient 审计回调：写 DB（失败仅记日志，不影响主流程）。"""
    from app.db.session import AsyncSessionLocal

    try:
        async with AsyncSessionLocal() as session:
            session.add(
                BrowserAuditLog(
                    source=_current_source.get(),
                    action=action[:50],
                    domain=(domain or "")[:255],
                    url=url or "",
                    ok=ok,
                    detail=(detail or None) and str(detail)[:500],
                )
            )
            await session.commit()
    except Exception as e:
        logger.warning(f"browser audit write failed: {e}")


def install_audit_sink() -> None:
    """main.py startup 调用：把 DB 审计挂到 BrowserClient。"""
    get_browser_client().set_audit_sink(_audit_sink)
    logger.info("browser audit sink installed (-> browser_audit_logs)")


# ---------------------------------------------------------------------------
# 域名白名单管理
# ---------------------------------------------------------------------------

class DomainAllowRequest(BaseModel):
    domain: str = Field(..., description="要临时放行的域名，如 example.com（域后缀匹配）")
    ttl_minutes: int = Field(default=60, ge=1, le=24 * 60, description="放行时长（分钟），到期自动失效")


@router.get("/domains")
async def list_domains(user=Depends(get_current_user)):
    """列出静态白名单 + 当前生效的临时放行（含剩余时间）。"""
    return {"ok": True, **get_browser_client().list_domains()}


@router.post("/domains")
async def allow_domain(
    body: DomainAllowRequest,
    user=Depends(get_current_user),
):
    """临时放行一个域名（TTL 到期自动失效，进程内生效）。

    这是「任意网站浏览器自动化」的运行时入口：默认只放行白名单内的域名，
    访问新网站时由用户显式放行（智能体遇到 DOMAIN_NOT_ALLOWED 会提示用户）。
    """
    try:
        result = get_browser_client().allow_domain_temporary(body.domain, body.ttl_minutes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, **result}


# ---------------------------------------------------------------------------
# 反向代理：绕过 X-Frame-Options / CSP frame-ancestors 限制
# 让前端能用真正的 iframe 嵌入飞书等禁止嵌入的网站
# ---------------------------------------------------------------------------

import httpx

_proxy_client: httpx.AsyncClient | None = None


def _get_proxy_client() -> httpx.AsyncClient:
    global _proxy_client
    if _proxy_client is None or _proxy_client.is_closed:
        _proxy_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"},
        )
    return _proxy_client


@router.api_route("/proxy/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"])
async def proxy_request(request: Request, path: str):
    """反向代理：删除 X-Frame-Options / CSP frame-ancestors，允许前端 iframe 嵌入。

    用法：iframe src="/api/browser/proxy/https%3A%2F%2Ffeishu.cn%2Fmessenger%2Ftodo"
    后端会代理请求到 https://feishu.cn/messenger/todo，
    并在响应中删除禁止嵌入的安全头。
    对 HTML 响应注入 <base> 标签，使页面内相对 URL 资源能正确解析到原始域名。
    """
    from urllib.parse import unquote, urlparse

    target_url = unquote(path)
    if not target_url.startswith("http"):
        target_url = "https://" + target_url

    client = _get_proxy_client()

    try:
        resp = await client.get(target_url, params=request.query_params, timeout=15.0)

        headers_to_remove = {
            "x-frame-options",
            "content-security-policy",
            "x-content-type-options",
            "strict-transport-security",
            "content-encoding",
            "content-length",
            "transfer-encoding",
            "date",
            "server",
            "connection",
            "keep-alive",
            "alt-svc",
        }

        response_headers: list[tuple[str, str]] = []
        for k, v in resp.headers.multi_items():
            if k.lower() not in headers_to_remove:
                response_headers.append((k, v))

        response_headers.append(("X-Frame-Options", "SAMEORIGIN"))

        content = resp.content
        content_type = resp.headers.get("content-type", "")

        if "text/html" in content_type:
            parsed = urlparse(target_url)
            base_href = f"{parsed.scheme}://{parsed.netloc}"
            html_text = content.decode("utf-8", errors="replace")
            base_tag = f'<base href="{base_href}" target="_self">'
            if "<head" in html_text.lower():
                html_text = html_text.replace("<head", f"<head>{base_tag}", 1)
            elif "<html" in html_text.lower():
                html_text = html_text.replace("<html", f"<html><head>{base_tag}</head>", 1)
            else:
                html_text = base_tag + html_text
            content = html_text.encode("utf-8")

        from fastapi.responses import Response
        return Response(
            content=content,
            status_code=resp.status_code,
            headers=dict(response_headers),
            media_type=content_type,
        )

    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Proxy error: {e}")


# ---------------------------------------------------------------------------
# 远程浏览器交互 API（前端侧面板调用）
# ---------------------------------------------------------------------------

class InteractRequest(BaseModel):
    action: str = Field(..., description="操作类型: click / dblclick / scroll / type / refresh / back / forward")
    x: int | None = Field(default=None, description="点击/滚动 X 坐标（页面内坐标）")
    y: int | None = Field(default=None, description="点击/滚动 Y 坐标（页面内坐标）")
    deltaY: int | None = Field(default=None, description="滚动量")
    text: str | None = Field(default=None, description="输入的文字")


@router.post("/interact")
async def browser_interact(
    body: InteractRequest,
    user=Depends(get_current_user),
):
    """远程浏览器交互：前端侧面板调用，执行点击/滚动/输入等操作后返回新截图。

    操作流程：执行用户操作 → 等待页面响应 → 截图返回。
    这是「远程浏览器」体验的核心 API——用户在截图上点击，感觉就像在操作真实浏览器。
    """
    client = get_browser_client()
    action = body.action.lower()

    try:
        if action == "refresh":
            result = await client.screenshot(quality=60)

        elif action == "click" and body.x is not None and body.y is not None:
            await client.evaluate(f"() => {{ const e = new MouseEvent('click', {{ clientX: {body.x}, clientY: {body.y}, bubbles: true }}); document.elementFromPoint({body.x}, {body.y})?.dispatchEvent(e) }}")
            import asyncio
            await asyncio.sleep(0.3)
            result = await client.screenshot(quality=60)

        elif action == "dblclick" and body.x is not None and body.y is not None:
            await client.evaluate(f"() => {{ const el = document.elementFromPoint({body.x}, {body.y}); if(el) {{ el.dispatchEvent(new MouseEvent('dblclick', {{ clientX: {body.x}, clientY: {body.y}, bubbles: true }})) }} }}")
            import asyncio
            await asyncio.sleep(0.3)
            result = await client.screenshot(quality=60)

        elif action == "scroll" and body.x is not None and body.y is not None:
            delta_y = body.deltaY or 100
            await client.evaluate(f"() => {{ window.scrollBy({{ top: {delta_y}, left: 0, behavior: 'instant' }}) }}")
            import asyncio
            await asyncio.sleep(0.2)
            result = await client.screenshot(quality=60)

        elif action == "type" and body.text:
            js_text = body.text.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${}")
            await client.evaluate(f"() => {{ const el = document.activeElement; if(el && (el.tagName==='INPUT'||el.tagName=='TEXTAREA'||el.isContentEditable)) {{ const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set; nativeInputValueSetter.call(el, `{js_text}`); el.dispatchEvent(new Event('input', {{ bubbles: true }})); el.dispatchEvent(new Event('change', {{ bubbles: true }})) }} }}")
            import asyncio
            await asyncio.sleep(0.2)
            result = await client.screenshot(quality=60)

        elif action == "back":
            await client.evaluate("() => window.history.back()")
            import asyncio
            await asyncio.sleep(0.5)
            result = await client.screenshot(quality=60)

        elif action == "forward":
            await client.evaluate("() => window.history.forward()")
            import asyncio
            await asyncio.sleep(0.5)
            result = await client.screenshot(quality=60)

        else:
            return {"ok": False, "error": f"Unknown action: {action}"}

        if result.get("ok"):
            return {
                "ok": True,
                "url": result.get("url", ""),
                "screenshot_base64": result.get("screenshot_base64", ""),
            }
        else:
            return {"ok": False, "error": result.get("error", "Screenshot failed")}

    except Exception as e:
        logger.error(f"browser interact error: {e}")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 导航 + 截图 REST 端点（前端侧边栏浏览器面板调用）
# ---------------------------------------------------------------------------

class NavigateRequest(BaseModel):
    url: str = Field(..., description="目标 URL")


@router.post("/navigate")
async def browser_navigate(
    body: NavigateRequest,
    user=Depends(get_current_user),
):
    """导航到指定 URL，返回页面信息 + 截图。"""
    client = get_browser_client()
    try:
        nav_result = await client.navigate(body.url)
        if not nav_result.get("ok"):
            return nav_result
        await asyncio.sleep(0.5)
        shot = await client.screenshot(quality=60)
        return {
            "ok": True,
            "url": nav_result.get("url", ""),
            "title": nav_result.get("title", ""),
            "screenshot_base64": shot.get("screenshot_base64", "") if shot.get("ok") else "",
        }
    except DomainNotAllowedError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:
        logger.exception(f"browser navigate error: {e}")
        return {"ok": False, "error": str(e)}


@router.post("/screenshot")
async def browser_screenshot(
    user=Depends(get_current_user),
):
    """截取当前页面截图。"""
    client = get_browser_client()
    result = await client.screenshot(quality=60)
    if result.get("ok"):
        return {
            "ok": True,
            "url": result.get("url", ""),
            "title": result.get("title", ""),
            "screenshot_base64": result.get("screenshot_base64", ""),
        }
    return result


# ---------------------------------------------------------------------------
# 发布助手：打开平台创作者中心
# ---------------------------------------------------------------------------

PUBLISHER_URLS = {
    "xiaohongshu": "https://creator.xiaohongshu.com/publish/publish",
    "douyin": "https://creator.douyin.com/creator-micro/content/upload",
    "kuaishou": "https://creator.kuaishou.com/publish/video",
    "bilibili": "https://member.bilibili.com/platform/upload/video/frame",
    "zhihu": "https://www.zhihu.com/creator/writer",
    "wechat": "https://channels.weixin.qq.com/platform/post",
}

PUBLISHER_DOMAINS = {
    "creator.xiaohongshu.com",
    "creator.douyin.com",
    "creator.kuaishou.com",
    "member.bilibili.com",
    "www.zhihu.com",
    "channels.weixin.qq.com",
}


class PublishNavigateRequest(BaseModel):
    platform: str = Field(..., description="平台标识: xiaohongshu/douyin/kuaishou/bilibili/zhihu/wechat")


@router.post("/publish/navigate")
async def publish_navigate(
    body: PublishNavigateRequest,
    user=Depends(get_current_user),
):
    """打开平台创作者中心发布页（自动放行域名 + 导航 + 截图）。"""
    platform = body.platform.strip().lower()
    url = PUBLISHER_URLS.get(platform)
    if not url:
        raise HTTPException(400, f"不支持的平台: {platform}（支持: {', '.join(PUBLISHER_URLS)}）")

    client = get_browser_client()
    from urllib.parse import urlparse
    domain = urlparse(url).hostname or ""
    if domain and domain not in client._static_domains():
        try:
            client.check_domain(url)
        except DomainNotAllowedError:
            client.allow_domain_temporary(domain, ttl_minutes=120)

    try:
        nav_result = await client.navigate(url)
        if not nav_result.get("ok"):
            return nav_result
        await asyncio.sleep(1.0)
        shot = await client.screenshot(quality=60)
        return {
            "ok": True,
            "platform": platform,
            "url": nav_result.get("url", url),
            "title": nav_result.get("title", ""),
            "screenshot_base64": shot.get("screenshot_base64", "") if shot.get("ok") else "",
        }
    except Exception as e:
        logger.error(f"publish navigate error: {e}")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 发布提交：用 Scrapling StealthyFetcher 自动填写 + 提交
# ---------------------------------------------------------------------------

class PublishSubmitRequest(BaseModel):
    platform: str = Field(..., description="平台标识: xiaohongshu/douyin/kuaishou/bilibili/zhihu/wechat")
    title: str = Field(..., description="作品标题")
    content: str = Field(..., description="作品正文/描述")
    tags: list[str] = Field(default=[], description="标签列表")
    images_base64: list[str] = Field(default=[], description="图片 base64 列表（不含 data: 前缀）")
    images_urls: list[str] = Field(default=[], description="图片 URL 列表（后端自动下载转 base64）")
    page_htmls: list[str] = Field(default=[], description="卡片页面 HTML 列表（后端自动渲染为图片并上传）")
    auto_submit: bool = Field(default=False, description="是否自动点击发布按钮（默认半自动，只填写不提交）")


@router.post("/publish/submit")
async def publish_submit(
    body: PublishSubmitRequest,
    user=Depends(get_current_user),
):
    """使用 Scrapling StealthyFetcher 自动填写发布表单并提交。

    流程：
    1. 加载平台 storageState（扫码登录 cookies）
    2. 用反检测浏览器打开创作者中心发布页
    3. 自动填写标题/正文/标签 + 上传图片
    4. auto_submit=True 时自动点击发布按钮
    5. 返回填写结果 + 截图

    半自动模式（默认）：只填写内容，用户在浏览器中确认后手动点击发布
    全自动模式：填写 + 点击发布一步完成
    """
    from app.services.platform_publisher import publish_to_platform

    platform = body.platform.strip().lower()
    if platform not in PUBLISHER_URLS:
        raise HTTPException(400, f"不支持的平台: {platform}（支持: {', '.join(PUBLISHER_URLS)}）")

    all_images_base64 = list(body.images_base64)

    if body.images_urls:
        import httpx
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            for img_url in body.images_urls:
                if not img_url:
                    continue
                try:
                    resp = await client.get(img_url)
                    if resp.status_code == 200:
                        b64 = base64.b64encode(resp.content).decode("ascii")
                        all_images_base64.append(b64)
                except Exception as e:
                    logger.warning(f"failed to download image {img_url}: {e}")

    if body.page_htmls:
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
                ctx = await browser.new_context(viewport={"width": 1080, "height": 1440})
                for i, html_content in enumerate(body.page_htmls):
                    if not html_content:
                        continue
                    try:
                        page = await ctx.new_page()
                        await page.set_content(html_content, wait_until="load", timeout=10000)
                        await asyncio.sleep(0.3)
                        shot_bytes = await page.screenshot(type="jpeg", quality=90, full_page=False)
                        b64 = base64.b64encode(shot_bytes).decode("ascii")
                        all_images_base64.append(b64)
                        await page.close()
                    except Exception as e:
                        logger.warning(f"failed to render page_html {i}: {e}")
                await ctx.close()
                await browser.close()
        except ImportError:
            logger.warning("playwright not available for HTML rendering, skipping page_htmls")
        except Exception as e:
            logger.warning(f"page_htmls rendering failed: {e}")

    result = await publish_to_platform(
        platform=platform,
        title=body.title,
        content=body.content,
        tags=body.tags,
        images_base64=all_images_base64,
        auto_submit=body.auto_submit,
    )
    return result


# ---------------------------------------------------------------------------
# 发布状态查询：检查平台发布页是否已成功发布
# ---------------------------------------------------------------------------

class PublishCheckRequest(BaseModel):
    platform: str = Field(..., description="平台标识")
    work_id: str = Field(..., description="作品 ID（用于更新发布状态）")


@router.post("/publish/check")
async def publish_check(
    body: PublishCheckRequest,
    user=Depends(get_current_user),
):
    """检查发布页当前状态（是否发布成功），并更新作品发布平台记录。

    前端在用户手动点击发布后轮询此接口确认结果。
    """
    client = get_browser_client()
    platform = body.platform.strip().lower()

    try:
        shot = await client.screenshot(quality=60)
        url = shot.get("url", "") if shot.get("ok") else ""
        title = shot.get("title", "") if shot.get("ok") else ""

        success_indicators = ["发布成功", "已发布", "审核中", "投稿成功", "提交成功"]
        fail_indicators = ["发布失败", "上传失败", "请重试"]

        page_text = ""
        try:
            extract_result = await client.extract()
            if extract_result.get("ok"):
                page_text = extract_result.get("text", "")
        except Exception:
            pass

        published = any(ind in page_text or ind in title for ind in success_indicators)
        failed = any(ind in page_text or ind in title for ind in fail_indicators)

        if published:
            try:
                from app.db.models import PublishedContentPerformance
                from app.db.session import AsyncSessionLocal
                from sqlalchemy import select as sa_select

                async with AsyncSessionLocal() as db:
                    stmt = sa_select(PublishedContentPerformance).where(
                        PublishedContentPerformance.id == body.work_id,
                    )
                    row = (await db.execute(stmt)).scalar_one_or_none()
                    if row:
                        existing = row.platform or "xiaohongshu"
                        row.content_status = "published"
                        await db.commit()
            except Exception as e:
                logger.warning(f"publish_check: failed to update work status: {e}")

        return {
            "ok": True,
            "platform": platform,
            "published": published,
            "failed": failed,
            "url": url,
            "title": title,
            "screenshot_base64": shot.get("screenshot_base64", "") if shot.get("ok") else "",
        }
    except Exception as e:
        logger.error(f"publish check error: {e}")
        return {"ok": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 审计查询
# ---------------------------------------------------------------------------

@router.get("/audit")
async def query_audit(
    limit: int = 50,
    offset: int = 0,
    domain: str = "",
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询浏览器动作审计日志（按时间倒序，可按域名过滤）。"""
    limit = max(1, min(limit, 500))
    stmt = select(BrowserAuditLog).order_by(BrowserAuditLog.created_at.desc())
    if domain:
        stmt = stmt.where(BrowserAuditLog.domain == domain.strip().lower())
    rows = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    return {
        "ok": True,
        "total_returned": len(rows),
        "items": [
            {
                "id": r.id,
                "source": r.source,
                "action": r.action,
                "domain": r.domain,
                "url": r.url,
                "ok": r.ok,
                "detail": r.detail,
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ],
    }


# ===========================================================================
# 对外 MCP Server（JSON-RPC 2.0 over HTTP，Streamable HTTP 子集）
# ===========================================================================

mcp_router = APIRouter(prefix="/api/mcp/browser", tags=["mcp-browser"])

_MCP_PROTOCOL_VERSION = "2024-11-05"
_MCP_SERVER_INFO = {"name": "xhs-browser", "version": "1.0.0"}

# 自动生成的 token（settings.mcp_browser_token 为空时由 main.py startup 填充）
_generated_token: str = ""


def set_generated_mcp_token(token: str) -> None:
    global _generated_token
    _generated_token = token


def _mcp_token() -> str:
    from app.config import get_settings

    return get_settings().mcp_browser_token or _generated_token


def _rpc_ok(req_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_err(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


# 工具表：name -> (description, inputSchema, handler)
def _tool_specs() -> list[dict]:
    return [
        {
            "name": "browser_navigate",
            "description": "打开网页（需在白名单域名内，否则返回 DOMAIN_NOT_ALLOWED 及放行指引）。返回页面快照：URL、标题、可交互元素列表（带 ref 编号，后续用 ref 点击/输入）。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "目标网址（http/https）"},
                    "profile_id": {"type": "string", "description": "可选：持久化 Profile ID（跨会话保留登录态）"},
                },
                "required": ["url"],
            },
        },
        {
            "name": "browser_snapshot",
            "description": "获取当前页面快照：URL、标题、可交互元素（带 ref）与 aria 结构概览。",
            "inputSchema": {"type": "object", "properties": {}},
        },
        {
            "name": "browser_click",
            "description": "点击页面元素。ref 来自最近一次快照；返回新快照。STALE_SNAPSHOT 表示页面已变化，先 snapshot 再试。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "元素 ref（如 e3）"},
                    "nav_seq": {"type": "integer", "description": "快照 nav_seq（防陈旧点击）"},
                },
                "required": ["ref"],
            },
        },
        {
            "name": "browser_fill",
            "description": "在输入框填入文本（覆盖原内容），返回新快照。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "description": "输入框 ref"},
                    "text": {"type": "string", "description": "要输入的文本"},
                    "nav_seq": {"type": "integer", "description": "快照 nav_seq"},
                },
                "required": ["ref", "text"],
            },
        },
        {
            "name": "browser_press",
            "description": "在当前聚焦元素上按键（Enter / Tab / Escape ...），返回新快照。",
            "inputSchema": {
                "type": "object",
                "properties": {"key": {"type": "string", "description": "按键名"}},
                "required": ["key"],
            },
        },
        {
            "name": "browser_extract",
            "description": "在当前页面执行 JS 表达式提取数据（如取全文/表格/隐藏数据），返回求值结果。",
            "inputSchema": {
                "type": "object",
                "properties": {"js": {"type": "string", "description": "JS 表达式，如 () => document.title"}},
                "required": ["js"],
            },
        },
        {
            "name": "browser_screenshot",
            "description": "截取当前页面截图，返回 base64 PNG。",
            "inputSchema": {
                "type": "object",
                "properties": {"full_page": {"type": "boolean", "description": "是否整页截图"}},
            },
        },
        {
            "name": "browser_sessions",
            "description": "管理浏览器会话：list=列出会话 / close=关闭当前会话。",
            "inputSchema": {
                "type": "object",
                "properties": {"op": {"type": "string", "enum": ["list", "close"]}},
            },
        },
        {
            "name": "browser_allow_domain",
            "description": "临时放行一个域名到浏览器白名单（默认 60 分钟，到期自动收回）。仅在用户明确同意后调用：browser_navigate 返回 DOMAIN_NOT_ALLOWED 时，先向用户说明并征得同意，再调用本工具（user_confirmed=true），然后重试导航。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "domain": {"type": "string", "description": "要放行的域名，如 github.com"},
                    "ttl_minutes": {"type": "integer", "description": "放行时长（分钟），默认 60"},
                    "user_confirmed": {"type": "boolean", "description": "用户已明确同意放行才为 true"},
                },
                "required": ["domain", "user_confirmed"],
            },
        },
    ]


async def _tool_call(name: str, args: dict[str, Any]) -> dict:
    """执行一个 MCP 工具调用（复用 BrowserClient，白名单/审计同源）。"""
    client = get_browser_client()
    if name == "browser_navigate":
        return await client.navigate(args["url"], args.get("profile_id") or None)
    if name == "browser_snapshot":
        return await client.snapshot()
    if name == "browser_click":
        return await client.act("click", ref=args["ref"], nav_seq=args.get("nav_seq"))
    if name == "browser_fill":
        return await client.act("fill", ref=args["ref"], text=args["text"], nav_seq=args.get("nav_seq"))
    if name == "browser_press":
        return await client.act("press", key=args["key"])
    if name == "browser_extract":
        return await client.evaluate(args["js"])
    if name == "browser_screenshot":
        return await client.screenshot(bool(args.get("full_page")))
    if name == "browser_sessions":
        if args.get("op") == "close":
            return await client.close()
        return await client.list_sessions()
    if name == "browser_allow_domain":
        if not args.get("user_confirmed"):
            return {
                "ok": False,
                "error": (
                    "NEEDS_USER_CONFIRMATION: 放行域名前必须先征得用户同意"
                    "（用户同意后将 user_confirmed 设为 true 再调用）。"
                ),
            }
        try:
            result = client.allow_domain_temporary(args["domain"], int(args.get("ttl_minutes", 60)))
        except (ValueError, KeyError) as e:
            return {"ok": False, "error": f"INVALID_DOMAIN: {e}"}
        return {"ok": True, **result}
    raise KeyError(name)


@mcp_router.post("")
async def mcp_endpoint(request: Request):
    """MCP JSON-RPC 2.0 入口（Bearer token 认证）。

    支持：initialize / tools/list / tools/call / ping。
    GET（SSE 推送流）不支持，返回 405 —— 客户端按需降级为纯 POST 轮询。
    """
    # Bearer 认证（hmac.compare_digest 防时序侧信道）
    import hmac

    auth = request.headers.get("authorization", "")
    token = _mcp_token()
    if not token or not hmac.compare_digest(auth, f"Bearer {token}"):
        return _rpc_err(None, -32001, "UNAUTHORIZED: invalid or missing Bearer token")

    try:
        body = await request.json()
    except Exception:
        return _rpc_err(None, -32700, "Parse error")

    method = body.get("method")
    req_id = body.get("id")
    params = body.get("params") or {}

    if method == "initialize":
        return _rpc_ok(req_id, {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": _MCP_SERVER_INFO,
        })

    if method == "ping":
        return _rpc_ok(req_id, {})

    if method == "tools/list":
        return _rpc_ok(req_id, {"tools": _tool_specs()})

    if method == "tools/call":
        name = params.get("name") or ""
        args = params.get("arguments") or {}
        # 标记审计来源为 mcp（fire-and-forget 的 audit task 继承此 context）
        tok = _current_source.set("mcp")
        try:
            try:
                result = await _tool_call(name, args)
            except KeyError:
                return _rpc_err(req_id, -32602, f"Unknown tool: {name}")
            except DomainNotAllowedError as e:
                # 白名单拒绝：返回结构化错误（非 isError，客户端可读详情）
                return _rpc_ok(req_id, {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True,
                })
            # 截断超长字段（截图 base64 除外，单结果上限 512KB）
            text = json.dumps(result, ensure_ascii=False, default=str)
            if len(text) > 512 * 1024:
                text = text[: 512 * 1024] + "…(truncated)"
            return _rpc_ok(req_id, {
                "content": [{"type": "text", "text": text}],
                "isError": bool(result.get("ok") is False),
            })
        finally:
            _current_source.reset(tok)

    return _rpc_err(req_id, -32601, f"Method not found: {method}")