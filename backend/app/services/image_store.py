"""图片本地文件存储服务。

统一管理选题池封面图/详情图 + 用户头像的本地存储。
当前使用本地文件系统，接口设计预留 OSS 切换能力。

目录结构：
  uploads/
  ├── topic_covers/          # 选题池封面图
  │   └── {content_id}.webp
  ├── topic_images/          # 选题池详情图
  │   └── {content_id}_{idx}.webp
  └── avatars/               # 用户头像
      └── {user_id}.webp

前端访问路径：
  /uploads/topic_covers/xxx.webp
  /uploads/topic_images/xxx_0.webp
  /uploads/avatars/user_id.webp
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

_BASE_DIR = Path(os.environ.get("UPLOAD_DIR", "uploads"))
_TOPIC_COVERS_DIR = _BASE_DIR / "topic_covers"
_TOPIC_IMAGES_DIR = _BASE_DIR / "topic_images"
_AVATARS_DIR = _BASE_DIR / "avatars"

_DIRS_INITIALIZED = False


def _ensure_dirs() -> None:
    global _DIRS_INITIALIZED
    if _DIRS_INITIALIZED:
        return
    for d in (_TOPIC_COVERS_DIR, _TOPIC_IMAGES_DIR, _AVATARS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    _DIRS_INITIALIZED = True


def _ext_from_content_type(ct: str) -> str:
    ct_lower = (ct or "").lower()
    if "webp" in ct_lower:
        return ".webp"
    if "png" in ct_lower:
        return ".png"
    if "gif" in ct_lower:
        return ".gif"
    if "jpeg" in ct_lower or "jpg" in ct_lower:
        return ".jpg"
    return ".webp"


async def download_image(url: str, timeout: float = 15.0) -> tuple[bytes, str] | None:
    """从 URL 下载图片，返回 (data, content_type) 或 None。"""
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        }
        parsed_host = url.split("/")[2] if "/" in url[8:] else ""
        xhs_hosts = {
            "sns-img.xhscdn.com",
            "ci.xiaohongshu.com",
            "picasso-static.xiaohongshu.com",
            "sns-webpic-qc.xhscdn.com",
            "sns-img-bd.xhscdn.com",
            "sns-img-hw.xhscdn.com",
        }
        if parsed_host in xhs_hosts:
            headers["Referer"] = "https://www.xiaohongshu.com/"

        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"download_image failed: status={resp.status_code} url={url[:80]}")
                return None
            content_type = resp.headers.get("content-type", "image/webp")
            if not content_type.startswith("image/"):
                logger.warning(f"download_image non-image: {content_type} url={url[:80]}")
                return None
            if len(resp.content) > 5 * 1024 * 1024:
                logger.warning(f"download_image too large: {len(resp.content)} url={url[:80]}")
                return None
            return resp.content, content_type
    except Exception as e:
        logger.warning(f"download_image error: {e} url={url[:80]}")
        return None


async def save_topic_cover(
    content_id: str,
    image_url: str,
) -> str | None:
    """下载选题封面图到本地，返回本地 URL 路径（如 /uploads/topic_covers/xxx.webp）。

    如果下载失败，返回 None（调用方应保留原 URL）。
    """
    _ensure_dirs()
    result = await download_image(image_url)
    if result is None:
        return None

    data, content_type = result
    ext = _ext_from_content_type(content_type)
    filename = f"{content_id}{ext}" if content_id else f"{int(time.time())}{ext}"
    filepath = _TOPIC_COVERS_DIR / filename

    filepath.write_bytes(data)
    return f"/uploads/topic_covers/{filename}"


async def save_topic_images(
    content_id: str,
    image_urls: list[str],
) -> list[str]:
    """批量下载选题详情图到本地，返回本地 URL 路径列表。

    下载失败的图片保留原 URL。
    """
    if not image_urls:
        return []

    _ensure_dirs()
    local_urls: list[str] = []

    for idx, url in enumerate(image_urls):
        result = await download_image(url)
        if result is None:
            local_urls.append(url)
            continue

        data, content_type = result
        ext = _ext_from_content_type(content_type)
        filename = f"{content_id}_{idx}{ext}"
        filepath = _TOPIC_IMAGES_DIR / filename

        filepath.write_bytes(data)
        local_urls.append(f"/uploads/topic_images/{filename}")

    return local_urls


async def save_avatar(
    user_id: str,
    image_data: bytes,
    content_type: str,
) -> str:
    """保存用户头像到本地文件系统，返回本地 URL 路径。"""
    _ensure_dirs()

    for old in _AVATARS_DIR.glob(f"{user_id}.*"):
        old.unlink(missing_ok=True)

    ext = _ext_from_content_type(content_type)
    filename = f"{user_id}{ext}"
    filepath = _AVATARS_DIR / filename

    filepath.write_bytes(image_data)
    return f"/uploads/avatars/{filename}"


def get_avatar_path(user_id: str) -> Path | None:
    """获取用户头像的本地文件路径，不存在返回 None。"""
    _ensure_dirs()
    for p in _AVATARS_DIR.glob(f"{user_id}.*"):
        return p
    return None


def is_local_url(url: str) -> bool:
    """判断 URL 是否为本地存储路径。"""
    return bool(url and url.startswith("/uploads/"))


async def cache_cover_image(content_id: str, cover_img: str) -> str:
    """如果封面图是外链，下载到本地并返回本地路径；已是本地路径则直接返回。"""
    if not cover_img:
        return cover_img
    if is_local_url(cover_img):
        return cover_img
    local = await save_topic_cover(content_id, cover_img)
    return local if local else cover_img


async def cache_detail_images(content_id: str, images: list[str] | None) -> list[str] | None:
    """如果详情图包含外链，批量下载到本地并返回混合路径列表。"""
    if not images:
        return images
    has_external = any(not is_local_url(u) for u in images if u)
    if not has_external:
        return images
    return await save_topic_images(content_id, images)


def cleanup_expired_images(days: int = 30) -> int:
    """清理超过 N 天的未引用图片文件。

    简单策略：删除超过指定天数的文件。
    生产环境应配合数据库查询，只删除未被引用的文件。
    """
    import datetime

    _ensure_dirs()
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    count = 0
    for dir_path in (_TOPIC_COVERS_DIR, _TOPIC_IMAGES_DIR):
        if not dir_path.exists():
            continue
        for f in dir_path.iterdir():
            if f.is_file():
                mtime = datetime.datetime.fromtimestamp(f.stat().st_mtime)
                if mtime < cutoff:
                    f.unlink(missing_ok=True)
                    count += 1
    return count