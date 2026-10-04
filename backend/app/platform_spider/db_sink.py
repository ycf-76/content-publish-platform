"""Spider 结果入库：写入 PublishedContentPerformance 表。

入库格式严格对齐 my_works.py 的 collect_note_data 端点逻辑，
确保前端 workStore.mapApiToWorkItem() 零改动即可展示到"已采集"列表。

关键：content_status='collected' → 前端 worksByStatus.collected 自动展示
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update as sa_update

from app.db.models import PublishedContentPerformance
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)


async def save_scraped_item(item: dict[str, Any], platform: str, user_id: str) -> bool:
    """Spider yield item → PublishedContentPerformance 入库。

    入库格式对齐 my_works.py:collect_note_data 的逻辑，
    确保前端 workStore.mapApiToWorkItem() 零改动即可展示到"已采集"列表。

    关键：content_status='collected' → worksByStatus.collected 自动展示
    """
    try:
        from app.services.performance_collector import compute_performance_score
        score = compute_performance_score({
            "likes": item.get("likes", 0),
            "collects": item.get("collects", 0),
            "comments": item.get("comments", 0),
            "shares": item.get("shares", 0),
        })
    except Exception:
        score = 0.0

    cover_img_url = item.get("cover_img_url", "")
    image_urls = item.get("image_urls", [])
    video_url = item.get("video_url", "")

    try:
        cover_img_url = await _cache_cover_image(item.get("note_id", ""), cover_img_url)
    except Exception:
        pass

    note_id = item.get("note_id", "")
    if not note_id:
        note_id = item.get("title", "")[:64] or f"unknown_{datetime.now(UTC).timestamp()}"
        logger.warning(f"save_scraped_item: note_id 为空，使用 fallback id: {note_id}")
    now = datetime.now(UTC)

    async with AsyncSessionLocal() as db:
        existing = await db.scalar(
            select(PublishedContentPerformance.id).where(
                PublishedContentPerformance.user_id == user_id,
                PublishedContentPerformance.platform == platform,
                PublishedContentPerformance.published_note_id == note_id,
            )
        )

        if existing:
            await db.execute(
                sa_update(PublishedContentPerformance)
                .where(PublishedContentPerformance.id == existing)
                .values(
                    title=(item.get("title", "") or "")[:512],
                    content_text=item.get("content_text"),
                    tags=item.get("tags"),
                    cover_img_url=cover_img_url,
                    images=image_urls if image_urls else None,
                    video_url=video_url or None,
                    collected_likes=item.get("likes", 0),
                    collected_collects=item.get("collects", 0),
                    collected_comments=item.get("comments", 0),
                    collected_shares=item.get("shares", 0),
                    performance_score=score,
                    collected_at=now,
                    content_status="collected",
                )
            )
            await db.commit()
            return True

        record = PublishedContentPerformance(
            user_id=user_id,
            workflow_id="",
            published_note_id=note_id,
            title=(item.get("title", "") or "")[:512],
            content_text=item.get("content_text"),
            tags=item.get("tags"),
            cover_img_url=cover_img_url,
            images=image_urls if image_urls else None,
            video_url=video_url or None,
            platform=platform,
            collected_likes=item.get("likes", 0),
            collected_collects=item.get("collects", 0),
            collected_comments=item.get("comments", 0),
            collected_shares=item.get("shares", 0),
            performance_score=score,
            collected_at=now,
            published_at=now,
            content_status="collected",
        )
        db.add(record)
        await db.commit()

    return True


async def update_sync_status(
    user_id: str, platform: str, status: str, error: str | None = None
) -> None:
    """更新 PlatformAccount 的同步状态。"""
    from app.db.models import PlatformAccount

    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_update(PlatformAccount)
            .where(
                PlatformAccount.user_id == user_id,
                PlatformAccount.platform == platform,
            )
            .values(
                sync_status=status,
                sync_error=error,
                updated_at=datetime.now(UTC),
            )
        )
        if status == "idle":
            await db.execute(
                sa_update(PlatformAccount)
                .where(
                    PlatformAccount.user_id == user_id,
                    PlatformAccount.platform == platform,
                )
                .values(last_synced_at=datetime.now(UTC))
            )
        await db.commit()


async def update_works_count(user_id: str, platform: str, count: int) -> None:
    """更新 PlatformAccount 的作品数。"""
    from app.db.models import PlatformAccount

    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_update(PlatformAccount)
            .where(
                PlatformAccount.user_id == user_id,
                PlatformAccount.platform == platform,
            )
            .values(works_count=count, updated_at=datetime.now(UTC))
        )
        await db.commit()


async def update_platform_uid(user_id: str, platform: str, uid: str) -> None:
    """更新 PlatformAccount 的 platform_uid。"""
    from app.db.models import PlatformAccount

    async with AsyncSessionLocal() as db:
        await db.execute(
            sa_update(PlatformAccount)
            .where(
                PlatformAccount.user_id == user_id,
                PlatformAccount.platform == platform,
            )
            .values(platform_uid=uid, updated_at=datetime.now(UTC))
        )
        await db.commit()


async def _cache_cover_image(note_id: str, url: str) -> str:
    """缓存封面图到本地（对齐 my_works.py 逻辑）。"""
    if not url or not url.startswith(("http://", "https://")):
        return url

    try:
        from app.services.image_store import save_topic_cover
        local_url = await save_topic_cover(note_id, url)
        if local_url:
            return local_url
    except Exception:
        pass

    return url