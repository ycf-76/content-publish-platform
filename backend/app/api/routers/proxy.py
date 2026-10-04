"""图片代理路由。

解决两个问题：
1. 小红书图片 CDN 的 referer 限制：浏览器直接 <img src> 加载会被拒
2. HackerNews 等外部文章的 og:image 跨域加载：需要后端代理

安全措施：
- 只允许 http/https scheme
- 阻止 SSRF（私有 IP / localhost）
- 限制响应大小 5MB
- 校验 content-type 为 image/*
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/proxy", tags=["proxy"])

# 小红书 CDN 域名（需要特殊 Referer）
_XHS_HOSTS = {
    "sns-img.xhscdn.com",
    "ci.xiaohongshu.com",
    "picasso-static.xiaohongshu.com",
    "sns-webpic-qc.xhscdn.com",
    "sns-img-bd.xhscdn.com",
    "sns-img-hw.xhscdn.com",
}

_MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB


def _maybe_cache_image_background(url: str, data: bytes, content_type: str) -> None:
    """CDN 图片本地化：后台异步保存到本地 + 更新数据库。

    当 proxy 成功代理到图片后触发。下次请求直接走本地路径，
    不再依赖 CDN 签名（小红书 CDN 链接约 2 天过期）。
    """
    import asyncio

    parsed = urlparse(url)
    hostname = parsed.hostname or ""

    # 仅对小红书 CDN 域名触发本地化
    if hostname not in _XHS_HOSTS:
        return

    async def _cache_and_update():
        try:
            from app.services.image_store import _ensure_dirs, _TOPIC_COVERS_DIR, _ext_from_content_type, is_local_url
            from app.db.session import AsyncSessionLocal
            from app.db.models import TopicPoolItem, PublishedContentPerformance
            from sqlalchemy import select, update as sa_update

            # 直接写文件（data 已经在内存中，无需再下载）
            _ensure_dirs()
            import hashlib
            content_id = hashlib.md5(url.encode()).hexdigest()[:16]
            ext = _ext_from_content_type(content_type)
            filename = f"{content_id}{ext}"
            filepath = _TOPIC_COVERS_DIR / filename
            filepath.write_bytes(data)
            local_url = f"/uploads/topic_covers/{filename}"

            async with AsyncSessionLocal() as db:
                # 更新选题池中所有匹配的记录
                stmt = (
                    sa_update(TopicPoolItem)
                    .where(TopicPoolItem.cover_img == url)
                    .values(cover_img=local_url)
                )
                result = await db.execute(stmt)
                if result.rowcount > 0:
                    logger.info(
                        f"proxy_image: cached {url[:60]} -> {local_url}, "
                        f"updated {result.rowcount} pool items"
                    )

                # 更新作品表中所有匹配的记录
                stmt3 = (
                    sa_update(PublishedContentPerformance)
                    .where(PublishedContentPerformance.cover_img_url == url)
                    .values(cover_img_url=local_url)
                )
                result3 = await db.execute(stmt3)
                if result3.rowcount > 0:
                    logger.info(
                        f"proxy_image: cached {url[:60]} -> {local_url}, "
                        f"updated {result3.rowcount} work records"
                    )

                # 也更新 images JSON 数组中的匹配 URL
                stmt2 = select(TopicPoolItem).where(
                    TopicPoolItem.images.contains([url])
                )
                rows = await db.scalars(stmt2)
                for row in rows:
                    if row.images and isinstance(row.images, list):
                        row.images = [
                            local_url if img == url else img
                            for img in row.images
                        ]

                # 作品表 images 也更新
                stmt4 = select(PublishedContentPerformance).where(
                    PublishedContentPerformance.images.contains([url])
                )
                rows4 = await db.scalars(stmt4)
                for row in rows4:
                    if row.images and isinstance(row.images, list):
                        row.images = [
                            local_url if img == url else img
                            for img in row.images
                        ]

                await db.commit()

        except Exception as e:
            logger.warning(f"proxy_image background cache failed: {e}")

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_cache_and_update())
    except RuntimeError:
        pass


async def _try_local_fallback(url: str) -> FileResponse | None:
    """CDN 请求失败时，尝试从数据库查找已本地化的图片文件。

    查找策略：
    1. 先查数据库中 cover_img / cover_img_url 是否已更新为 /uploads/... 路径
    2. 再按 URL 的 MD5 哈希直接在 uploads/ 目录下找文件
    """
    try:
        from app.db.session import AsyncSessionLocal
        from app.db.models import TopicPoolItem, PublishedContentPerformance
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            stmt = select(TopicPoolItem.cover_img).where(TopicPoolItem.cover_img == url).limit(1)
            row = await db.scalar(stmt)
            if row and row.startswith("/uploads/"):
                local_path = Path(row.lstrip("/"))
                if local_path.exists():
                    return FileResponse(local_path, media_type="image/webp")

            stmt2 = select(PublishedContentPerformance.cover_img_url).where(
                PublishedContentPerformance.cover_img_url == url
            ).limit(1)
            row2 = await db.scalar(stmt2)
            if row2 and row2.startswith("/uploads/"):
                local_path = Path(row2.lstrip("/"))
                if local_path.exists():
                    return FileResponse(local_path, media_type="image/webp")

        content_id = hashlib.md5(url.encode()).hexdigest()[:16]
        covers_dir = Path("uploads/topic_covers")
        for ext in (".webp", ".jpg", ".png", ".gif"):
            candidate = covers_dir / f"{content_id}{ext}"
            if candidate.exists():
                media = f"image/{ext.lstrip('.')}" if ext != ".jpg" else "image/jpeg"
                return FileResponse(candidate, media_type=media)

    except Exception as e:
        logger.warning(f"proxy_image local fallback failed: {e}")

    return None


def _is_private_host(hostname: str) -> bool:
    """SSRF 防护：检查 hostname 是否指向私有/回环地址。"""
    # 先尝试直接解析 IP
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        pass
    # 域名 → DNS 解析 → 检查 IP
    try:
        infos = socket.getaddrinfo(hostname, None)
        for info in infos:
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
                if ip.is_private or ip.is_loopback or ip.is_link_local:
                    return True
            except ValueError:
                continue
    except socket.gaierror:
        pass
    return False


@router.get("/image")
async def proxy_image(request: Request) -> StreamingResponse:
    """代理图片请求。

    用法: GET /api/proxy/image?url=https://example.com/image.jpg

    - 小红书 CDN：设置 Referer 绕过防盗链
    - 其他域名：用通用 UA 请求
    - SSRF 防护：阻止私有 IP / localhost
    - 大小限制：5MB
    """
    url = request.query_params.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="missing 'url' query param")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=403, detail="only http/https allowed")

    hostname = parsed.hostname or ""
    if not hostname:
        raise HTTPException(status_code=400, detail="invalid url: no hostname")

    # SSRF 防护
    if _is_private_host(hostname):
        raise HTTPException(status_code=403, detail=f"private host blocked: {hostname}")

    # 根据域名选择 Referer
    is_xhs = hostname in _XHS_HOSTS
    # 完整浏览器请求头（绕过 Cloudflare 等反爬）
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Sec-Ch-Ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "image",
        "Sec-Fetch-Mode": "no-cors",
        "Sec-Fetch-Site": "cross-site",
    }
    if is_xhs:
        headers["Referer"] = "https://www.xiaohongshu.com/"
        headers["Sec-Fetch-Site"] = "same-site"

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            logger.warning(f"proxy_image upstream {resp.status_code} for {url[:80]}, trying local fallback")
            fallback = await _try_local_fallback(url)
            if fallback:
                logger.info(f"proxy_image: served from local cache for {url[:80]}")
                return fallback
            raise HTTPException(status_code=502, detail=f"upstream returned {resp.status_code}")

        content_type = resp.headers.get("content-type", "")
        # 校验是图片类型
        if not content_type.startswith("image/"):
            logger.warning(f"proxy_image non-image content-type: {content_type} for {url[:80]}")
            raise HTTPException(status_code=415, detail=f"not an image: {content_type}")

        # 大小限制
        if len(resp.content) > _MAX_IMAGE_SIZE:
            raise HTTPException(status_code=413, detail="image too large (max 5MB)")

        # 后台异步：CDN 图片本地化（下次请求直接走本地，不再依赖 CDN 签名）
        # 仅对小红书 CDN 域名触发，避免无关 URL 的下载开销
        _maybe_cache_image_background(url, resp.content, content_type)

        return StreamingResponse(
            iter([resp.content]),
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=86400",  # 浏览器缓存1天
            },
        )
    except httpx.HTTPError as e:
        logger.warning(f"proxy_image fetch failed: {e}, trying local fallback")
        fallback = await _try_local_fallback(url)
        if fallback:
            logger.info(f"proxy_image: served from local cache (after fetch error) for {url[:80]}")
            return fallback
        raise HTTPException(status_code=502, detail=f"fetch failed: {e}")