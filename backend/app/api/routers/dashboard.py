"""数据看板 API。

仿照小红书创作者中心数据看板设计：
- GET  /api/dashboard/overview：账号概览（核心指标 + 趋势）
- GET  /api/dashboard/content-analysis：内容分析（笔记排行 + 维度分布）
- GET  /api/dashboard/follower-analysis：粉丝分析（增长趋势 + 来源）
- GET  /api/dashboard/platform/:platform：单平台详细数据

数据来源：PublishedContentPerformance（Spider 同步入库）+ PlatformAccount（扫码绑定）
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select, func, case, and_

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.db.models import PublishedContentPerformance, PlatformAccount
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

PLATFORM_LABELS = {
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "bilibili": "B站",
    "wechat_mp": "微信公众号",
    "weibo": "微博",
}

ALL_PLATFORMS = ["xiaohongshu", "douyin", "bilibili", "wechat_mp", "weibo"]


def _dt(dt_val: datetime | None) -> str | None:
    if not dt_val:
        return None
    return dt_val.isoformat()


def _reads(r: PublishedContentPerformance) -> int:
    return (r.collected_likes or 0) + (r.collected_collects or 0) + (r.collected_comments or 0)


def _interactions(r: PublishedContentPerformance) -> int:
    return _reads(r) + (r.collected_shares or 0)


def _engagement_rate(r: PublishedContentPerformance) -> float:
    rd = _reads(r)
    if rd == 0:
        return 0.0
    return round(_interactions(r) / rd * 100, 2)


@router.get("/overview")
async def get_overview(
    days: int = Query(default=7, ge=1, le=90, description="统计天数"),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """账号概览：核心指标卡片 + 日粒度趋势折线 + 平台账号列表。

    数据策略：查该用户所有 PublishedContentPerformance 记录，
    不依赖 published_at 做时间过滤（Spider 同步数据 published_at=入库时间），
    days 参数仅影响趋势图的时间窗口。
    """
    now = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        user_base = PublishedContentPerformance.user_id == user_id

        total_reads_val = await db.scalar(
            select(func.coalesce(func.sum(
                PublishedContentPerformance.collected_likes
                + PublishedContentPerformance.collected_collects
                + PublishedContentPerformance.collected_comments
            ), 0)).where(user_base)
        ) or 0

        total_interactions_val = await db.scalar(
            select(func.coalesce(func.sum(
                PublishedContentPerformance.collected_likes
                + PublishedContentPerformance.collected_collects
                + PublishedContentPerformance.collected_comments
                + PublishedContentPerformance.collected_shares
            ), 0)).where(user_base)
        ) or 0

        total_count = await db.scalar(
            select(func.count()).select_from(
                select(PublishedContentPerformance).where(user_base).subquery()
            )
        ) or 0

        collected_count = await db.scalar(
            select(func.count()).select_from(
                select(PublishedContentPerformance).where(
                    user_base,
                    PublishedContentPerformance.collected_at.isnot(None),
                ).subquery()
            )
        ) or 0

        hot_count = await db.scalar(
            select(func.coalesce(func.sum(
                case((PublishedContentPerformance.is_replicated == True, 1), else_=0)
            ), 0)).where(user_base)
        ) or 0

        avg_engagement_rate = 0.0
        if total_reads_val > 0:
            avg_engagement_rate = round(total_interactions_val / total_reads_val * 100, 2)

        since = now - timedelta(days=days)
        daily_trend = []
        for i in range(days):
            day = since + timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            day_base = and_(
                PublishedContentPerformance.user_id == user_id,
                PublishedContentPerformance.collected_at >= day_start,
                PublishedContentPerformance.collected_at < day_end,
            )

            day_interactions = await db.scalar(
                select(func.coalesce(func.sum(
                    PublishedContentPerformance.collected_likes
                    + PublishedContentPerformance.collected_collects
                    + PublishedContentPerformance.collected_comments
                    + PublishedContentPerformance.collected_shares
                ), 0)).where(day_base)
            ) or 0

            day_count = await db.scalar(
                select(func.count()).select_from(
                    select(PublishedContentPerformance).where(day_base).subquery()
                )
            ) or 0

            daily_trend.append({
                "date": day_start.strftime("%m-%d"),
                "interactions": day_interactions,
                "count": day_count,
            })

        platform_accounts = await db.scalars(
            select(PlatformAccount).where(PlatformAccount.user_id == user_id)
        )
        accounts = []
        for acc in platform_accounts.all():
            accounts.append({
                "platform": acc.platform,
                "platform_label": PLATFORM_LABELS.get(acc.platform, acc.platform),
                "platform_nickname": acc.platform_nickname,
                "platform_avatar_url": acc.platform_avatar_url,
                "fans_count": acc.fans_count or 0,
                "works_count": acc.works_count or 0,
                "last_synced_at": _dt(acc.last_synced_at),
                "sync_status": acc.sync_status,
                "bound": True,
            })

        bound_platforms = {a["platform"] for a in accounts}
        for p in ALL_PLATFORMS:
            if p not in bound_platforms:
                accounts.append({
                    "platform": p,
                    "platform_label": PLATFORM_LABELS.get(p, p),
                    "platform_nickname": None,
                    "platform_avatar_url": None,
                    "fans_count": 0,
                    "works_count": 0,
                    "last_synced_at": None,
                    "sync_status": "idle",
                    "bound": False,
                })

        platform_content_stats: dict[str, dict] = {}
        for p in ALL_PLATFORMS:
            p_base = and_(
                PublishedContentPerformance.user_id == user_id,
                PublishedContentPerformance.platform == p,
            )
            p_likes = await db.scalar(
                select(func.coalesce(func.sum(PublishedContentPerformance.collected_likes), 0)).where(p_base)
            ) or 0
            p_collects = await db.scalar(
                select(func.coalesce(func.sum(PublishedContentPerformance.collected_collects), 0)).where(p_base)
            ) or 0
            p_comments = await db.scalar(
                select(func.coalesce(func.sum(PublishedContentPerformance.collected_comments), 0)).where(p_base)
            ) or 0
            p_shares = await db.scalar(
                select(func.coalesce(func.sum(PublishedContentPerformance.collected_shares), 0)).where(p_base)
            ) or 0
            p_count = await db.scalar(
                select(func.count()).select_from(
                    select(PublishedContentPerformance).where(p_base).subquery()
                )
            ) or 0
            platform_content_stats[p] = {
                "likes": p_likes,
                "collects": p_collects,
                "comments": p_comments,
                "shares": p_shares,
                "reads": p_likes + p_collects + p_comments,
                "interactions": p_likes + p_collects + p_comments + p_shares,
                "count": p_count,
            }

    return StandardResponse(data={
        "summary": {
            "total_reads": total_reads_val,
            "total_interactions": total_interactions_val,
            "total_count": total_count,
            "collected_count": collected_count,
            "hot_count": hot_count,
            "avg_engagement_rate": avg_engagement_rate,
        },
        "daily_trend": daily_trend,
        "platform_accounts": accounts,
        "platform_content_stats": platform_content_stats,
        "days": days,
    })


@router.get("/content-analysis")
async def get_content_analysis(
    platform: str | None = Query(None, description="按平台筛选"),
    sort_by: str = Query(default="performance", description="排序: performance/reads/latest"),
    limit: int = Query(default=10, ge=1, le=50),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """内容分析：笔记排行 + 维度分布。

    仿小红书创作者中心「内容分析」tab。
    查所有数据，不做时间过滤。
    """
    async with AsyncSessionLocal() as db:
        conditions = [PublishedContentPerformance.user_id == user_id]
        if platform:
            conditions.append(PublishedContentPerformance.platform == platform)

        base = and_(*conditions)

        if sort_by == "reads":
            order = desc(
                PublishedContentPerformance.collected_likes
                + PublishedContentPerformance.collected_collects
                + PublishedContentPerformance.collected_comments
            )
        elif sort_by == "latest":
            order = desc(PublishedContentPerformance.collected_at)
        else:
            order = desc(PublishedContentPerformance.performance_score)

        top_stmt = (
            select(PublishedContentPerformance)
            .where(base)
            .order_by(order)
            .limit(limit)
        )
        top_result = await db.scalars(top_stmt)
        top_items = []
        for r in top_result.all():
            top_items.append({
                "id": r.id,
                "title": r.title or r.topic or "无标题",
                "cover_img_url": r.cover_img_url,
                "platform": r.platform,
                "published_at": _dt(r.published_at),
                "collected_at": _dt(r.collected_at),
                "likes": r.collected_likes or 0,
                "collects": r.collected_collects or 0,
                "comments": r.collected_comments or 0,
                "shares": r.collected_shares or 0,
                "reads": _reads(r),
                "interactions": _interactions(r),
                "engagement_rate": _engagement_rate(r),
                "is_replicated": r.is_replicated or False,
                "performance_score": r.performance_score,
                "content_status": r.content_status,
            })

        all_stmt = select(PublishedContentPerformance).where(base)
        all_result = await db.scalars(all_stmt)
        all_records = list(all_result.all())

        content_type_dist = {"image_text": 0, "video": 0}
        pattern_dist: dict[str, int] = {}
        emotion_dist: dict[str, int] = {}
        platform_dist: dict[str, int] = {}

        for r in all_records:
            if r.video_url:
                content_type_dist["video"] += 1
            else:
                content_type_dist["image_text"] += 1

            if r.title_pattern:
                pattern_dist[r.title_pattern] = pattern_dist.get(r.title_pattern, 0) + 1
            if r.emotion_trigger:
                emotion_dist[r.emotion_trigger] = emotion_dist.get(r.emotion_trigger, 0) + 1
            p = r.platform or "unknown"
            platform_dist[p] = platform_dist.get(p, 0) + 1

        pattern_ranking = sorted(pattern_dist.items(), key=lambda x: x[1], reverse=True)[:8]
        emotion_ranking = sorted(emotion_dist.items(), key=lambda x: x[1], reverse=True)[:8]

    return StandardResponse(data={
        "top_items": top_items,
        "content_type_dist": content_type_dist,
        "pattern_ranking": [{"name": k, "count": v} for k, v in pattern_ranking],
        "emotion_ranking": [{"name": k, "count": v} for k, v in emotion_ranking],
        "platform_dist": platform_dist,
        "total": len(all_records),
    })


@router.get("/follower-analysis")
async def get_follower_analysis(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """粉丝分析：各平台粉丝数 + 绑定状态。"""
    async with AsyncSessionLocal() as db:
        result = await db.scalars(
            select(PlatformAccount).where(PlatformAccount.user_id == user_id)
        )
        accounts = result.all()

    total_fans = 0
    platform_fans = []
    for acc in accounts:
        fans = acc.fans_count or 0
        total_fans += fans
        platform_fans.append({
            "platform": acc.platform,
            "platform_label": PLATFORM_LABELS.get(acc.platform, acc.platform),
            "fans_count": fans,
            "works_count": acc.works_count or 0,
            "nickname": acc.platform_nickname,
            "avatar_url": acc.platform_avatar_url,
            "last_synced_at": _dt(acc.last_synced_at),
            "bound": True,
        })

    return StandardResponse(data={
        "total_fans": total_fans,
        "platform_fans": platform_fans,
    })


@router.get("/platform/{platform}")
async def get_platform_detail(
    platform: str,
    days: int = Query(default=7, ge=1, le=90),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """单平台详细数据：核心指标 + 趋势 + Top 内容。"""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    async with AsyncSessionLocal() as db:
        p_base = and_(
            PublishedContentPerformance.user_id == user_id,
            PublishedContentPerformance.platform == platform,
        )

        total_likes = await db.scalar(
            select(func.coalesce(func.sum(PublishedContentPerformance.collected_likes), 0)).where(p_base)
        ) or 0
        total_collects = await db.scalar(
            select(func.coalesce(func.sum(PublishedContentPerformance.collected_collects), 0)).where(p_base)
        ) or 0
        total_comments = await db.scalar(
            select(func.coalesce(func.sum(PublishedContentPerformance.collected_comments), 0)).where(p_base)
        ) or 0
        total_shares = await db.scalar(
            select(func.coalesce(func.sum(PublishedContentPerformance.collected_shares), 0)).where(p_base)
        ) or 0
        total_count = await db.scalar(
            select(func.count()).select_from(
                select(PublishedContentPerformance).where(p_base).subquery()
            )
        ) or 0
        hot_count = await db.scalar(
            select(func.coalesce(func.sum(
                case((PublishedContentPerformance.is_replicated == True, 1), else_=0)
            ), 0)).where(p_base)
        ) or 0

        total_reads = total_likes + total_collects + total_comments
        total_interactions = total_reads + total_shares
        avg_engagement_rate = round(total_interactions / total_reads * 100, 2) if total_reads > 0 else 0

        daily_trend = []
        for i in range(days):
            day = since + timedelta(days=i)
            day_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            day_base = and_(
                PublishedContentPerformance.user_id == user_id,
                PublishedContentPerformance.platform == platform,
                PublishedContentPerformance.collected_at >= day_start,
                PublishedContentPerformance.collected_at < day_end,
            )
            day_interactions = await db.scalar(
                select(func.coalesce(func.sum(
                    PublishedContentPerformance.collected_likes
                    + PublishedContentPerformance.collected_collects
                    + PublishedContentPerformance.collected_comments
                    + PublishedContentPerformance.collected_shares
                ), 0)).where(day_base)
            ) or 0
            day_count = await db.scalar(
                select(func.count()).select_from(
                    select(PublishedContentPerformance).where(day_base).subquery()
                )
            ) or 0
            daily_trend.append({
                "date": day_start.strftime("%m-%d"),
                "interactions": day_interactions,
                "count": day_count,
            })

        top_stmt = (
            select(PublishedContentPerformance)
            .where(p_base)
            .order_by(desc(PublishedContentPerformance.performance_score))
            .limit(5)
        )
        top_result = await db.scalars(top_stmt)
        top_items = []
        for r in top_result.all():
            top_items.append({
                "id": r.id,
                "title": r.title or r.topic or "无标题",
                "cover_img_url": r.cover_img_url,
                "likes": r.collected_likes or 0,
                "collects": r.collected_collects or 0,
                "comments": r.collected_comments or 0,
                "shares": r.collected_shares or 0,
                "reads": _reads(r),
                "is_replicated": r.is_replicated or False,
                "published_at": _dt(r.published_at),
            })

        acc_result = await db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.user_id == user_id,
                PlatformAccount.platform == platform,
            )
        )
        account_info = None
        if acc_result:
            account_info = {
                "nickname": acc_result.platform_nickname,
                "fans_count": acc_result.fans_count or 0,
                "works_count": acc_result.works_count or 0,
                "last_synced_at": _dt(acc_result.last_synced_at),
            }

    return StandardResponse(data={
        "platform": platform,
        "platform_label": PLATFORM_LABELS.get(platform, platform),
        "summary": {
            "total_likes": total_likes,
            "total_collects": total_collects,
            "total_comments": total_comments,
            "total_shares": total_shares,
            "total_reads": total_reads,
            "total_interactions": total_interactions,
            "total_count": total_count,
            "hot_count": hot_count,
            "avg_engagement_rate": avg_engagement_rate,
        },
        "daily_trend": daily_trend,
        "top_items": top_items,
        "account_info": account_info,
        "days": days,
    })