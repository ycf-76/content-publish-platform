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

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

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
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)

        if resp.status_code != 200:
            logger.warning(f"proxy_image upstream {resp.status_code} for {url[:80]}")
            raise HTTPException(status_code=502, detail=f"upstream returned {resp.status_code}")

        content_type = resp.headers.get("content-type", "")
        # 校验是图片类型
        if not content_type.startswith("image/"):
            logger.warning(f"proxy_image non-image content-type: {content_type} for {url[:80]}")
            raise HTTPException(status_code=415, detail=f"not an image: {content_type}")

        # 大小限制
        if len(resp.content) > _MAX_IMAGE_SIZE:
            raise HTTPException(status_code=413, detail="image too large (max 5MB)")

        return StreamingResponse(
            iter([resp.content]),
            media_type=content_type,
            headers={
                "Cache-Control": "public, max-age=86400",  # 浏览器缓存1天
            },
        )
    except httpx.HTTPError as e:
        logger.warning(f"proxy_image fetch failed: {e}")
        raise HTTPException(status_code=502, detail=f"fetch failed: {e}")
