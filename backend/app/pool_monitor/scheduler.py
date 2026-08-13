"""APScheduler 定时任务配置。

注册两个定时任务：
- pool_monitor：每 CRAWL_INTERVAL_MINUTES（默认10）分钟抓取一次
- pool_cleanup：每天 CLEANUP_HOUR（默认凌晨2点）执行一次水位清理

调度器在应用 lifespan 中启动 / 关闭（见 main.py）。
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.db.session import AsyncSessionLocal
from app.pool_monitor.config import get_pool_settings
from app.pool_monitor.monitor_agent import MonitorAgent
from app.pool_monitor.pool_manager import PoolManager

logger = logging.getLogger(__name__)

# 全局调度器单例（lifespan 启动时 start，关闭时 shutdown）
scheduler = AsyncIOScheduler(timezone="Asia/Shanghai")


async def _run_monitor() -> None:
    """定时任务：执行一次监控抓取。"""
    try:
        async with AsyncSessionLocal() as session:
            await MonitorAgent().run(session)
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
