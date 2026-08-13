"""选题池监控模块入口 —— v6 合并版。

职责：注册 APScheduler 定时任务 + 启动检查（池<阈值立即抓取）。
不再建独立表（已合并到 topic_pool_items），不再提供独立 API 路由
（监控数据查询走 /api/topic-pool，手动触发走 /api/topic-pool/monitor/fetch）。

集成方式（在现有 app/main.py 的 lifespan 中调用）：
    from app.pool_monitor.main import pool_startup
    await pool_startup()          # 注册调度器 + 启动检查
    # 关闭时：from app.pool_monitor.main import pool_shutdown; pool_shutdown()
"""
from __future__ import annotations

import logging

from sqlalchemy import func, select

from app.db.models import TopicPoolItem
from app.db.session import AsyncSessionLocal
from app.pool_monitor.config import get_pool_settings
from app.pool_monitor.monitor_agent import MonitorAgent
from app.pool_monitor.scheduler import scheduler, setup_scheduler

logger = logging.getLogger(__name__)


async def startup_check() -> None:
    """启动检查：若池子 monitor 数据数量 < 阈值，立即触发一次抓取。"""
    settings = get_pool_settings()
    async with AsyncSessionLocal() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(TopicPoolItem)
                .where(TopicPoolItem.auto_source == "monitor")
            )
        ).scalar() or 0
        if count < settings.pool_startup_threshold:
            logger.info(f"启动检查：monitor 数据 {count} < {settings.pool_startup_threshold}，立即触发抓取")
            await MonitorAgent().run(session)
        else:
            logger.info(f"启动检查：monitor 数据 {count}，无需补抓")


async def pool_startup() -> None:
    """模块启动流程：注册调度器 → 启动调度器 → 启动检查。"""
    setup_scheduler()
    if not scheduler.running:
        scheduler.start()
    await startup_check()


def pool_shutdown() -> None:
    """模块关闭流程：停止调度器。"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
    logger.info("选题池调度器已停止")