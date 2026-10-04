"""APScheduler 定时任务配置。

注册两个定时任务：
- pool_monitor：每 CRAWL_INTERVAL_MINUTES（默认10）分钟抓取一次
- pool_cleanup：每天 CLEANUP_HOUR（默认凌晨2点）执行一次水位清理

v8：监控抓取增加活跃用户画像驱动——定时任务查 DB 获取活跃用户，
    传 user_id 给 MonitorAgent 使偏好关键词抓取逻辑生效。
    不需要 JWT，后台任务直接查数据库获取 user_id。

调度器在应用 lifespan 中启动 / 关闭（见 main.py）。
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select, desc

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.db.session import AsyncSessionLocal
from app.pool_monitor.config import get_pool_settings
from app.pool_monitor.monitor_agent import MonitorAgent
from app.pool_monitor.pool_manager import PoolManager

logger = logging.getLogger(__name__)

_ACTIVE_USER_LIMIT = 10

scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def _get_active_user_ids(limit: int = _ACTIVE_USER_LIMIT) -> list[str]:
    """从 agent_memory 获取近期最活跃的用户 ID 列表。

    活跃度定义：搜索关键词记忆条数最多的用户（近期搜索越频繁越活跃）。
    不需要 JWT，直接查数据库。
    """
    try:
        from app.db.models import AgentMemory
        async with AsyncSessionLocal() as session:
            stmt = (
                select(AgentMemory.user_id, func.count().label("cnt"))
                .where(
                    AgentMemory.memory_type == "preferences",
                    AgentMemory.memory_key == "search_keywords",
                )
                .group_by(AgentMemory.user_id)
                .order_by(desc("cnt"))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.all()]
    except Exception as e:
        logger.warning(f"_get_active_user_ids failed: {e}")
        return []


async def _run_monitor() -> None:
    """定时任务：执行一次监控抓取（全局 + 活跃用户画像驱动）。

    1. 全局热点抓取（无 user_id，与原有逻辑一致）
    2. 活跃用户画像驱动抓取（传 user_id，触发偏好关键词抓取）
    """
    try:
        async with AsyncSessionLocal() as session:
            await MonitorAgent().run(session)

        active_user_ids = await _get_active_user_ids()
        if active_user_ids:
            logger.info(f"监控抓取：发现 {len(active_user_ids)} 个活跃用户，启动画像驱动抓取")
            for uid in active_user_ids:
                try:
                    async with AsyncSessionLocal() as session:
                        await MonitorAgent().run(session, user_id=uid)
                except Exception as e:
                    logger.warning(f"画像驱动抓取失败 user_id={uid}: {e}")
    except Exception as e:
        logger.exception(f"定时监控任务执行失败: {e}")


async def _run_cleanup() -> None:
    """定时任务：执行一次水位清理。"""
    try:
        async with AsyncSessionLocal() as session:
            await PoolManager().cleanup(session)
    except Exception as e:
        logger.exception(f"定时清理任务执行失败: {e}")


def setup_scheduler() -> AsyncIOScheduler:
    """注册定时任务（重复调用会 replace_existing，避免重复注册）。"""
    settings = get_pool_settings()

    scheduler.add_job(
        _run_monitor,
        IntervalTrigger(minutes=settings.crawl_interval_minutes),
        id="pool_monitor",
        name="选题池监控抓取",
        replace_existing=True,
        # 避免实例重启后任务堆积
        max_instances=1,
        coalesce=True,
    )

    scheduler.add_job(
        _run_cleanup,
        CronTrigger(hour=settings.cleanup_hour, minute=0),
        id="pool_cleanup",
        name="选题池水位清理",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    logger.info(
        f"选题池调度器已注册: monitor 每 {settings.crawl_interval_minutes} 分钟, "
        f"cleanup 每天 {settings.cleanup_hour:02d}:00"
    )
    return scheduler