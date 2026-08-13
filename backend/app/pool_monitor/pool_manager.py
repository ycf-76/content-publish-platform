"""池子水位管理（PoolManager）—— v6 合并版。

每天凌晨 2:00 执行一次清理任务（操作 topic_pool_items 表）：
1. 删除创建时间超过 72h 且 热度分 < 40 的 monitor 数据
2. 若池中数量仍 > 200，按热度分升序删除，直至 ≤ 200
3. 若池中数量 < 150，触发一次紧急补抓（立即调用 MonitorAgent）

注意：清理只针对 auto_source="monitor" 的自动数据，手动抓取的数据
（auto_source="manual"）不参与自动清理，避免误删用户主动收藏的内容。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TopicPoolItem
from app.pool_monitor.config import get_pool_settings
from app.pool_monitor.monitor_agent import MonitorAgent

logger = logging.getLogger(__name__)


class PoolManager:
    """池子水位管理器：清理过期低质 + 容量平衡 + 紧急补抓。"""

    def __init__(self, monitor: MonitorAgent | None = None) -> None:
        self.monitor = monitor or MonitorAgent()

    async def cleanup(self, session: AsyncSession) -> dict:
        """执行一次完整清理流程。"""
        settings = get_pool_settings()
        now = datetime.now(timezone.utc)
        expire_threshold = now - timedelta(hours=settings.cleanup_expire_hours)

        before = await self._count(session)

        # 步骤1：删除超时且低分的 monitor 数据（手动数据不动）
        stmt1 = delete(TopicPoolItem).where(
            TopicPoolItem.created_at < expire_threshold,
            TopicPoolItem.heat_score < settings.cleanup_expire_score,
            TopicPoolItem.auto_source == "monitor",
        )
        result1 = await session.execute(stmt1)
        await session.commit()
        expired_deleted = result1.rowcount or 0
        logger.info(f"PoolManager 步骤1：删除过期低质 {expired_deleted} 条")

        # 步骤2：若仍超量，按热度分升序删至 max_pool_size（仅 monitor 数据）
        total_after_step1 = await self._count(session)
        overflow_deleted = 0
        if total_after_step1 > settings.max_pool_size:
            excess = total_after_step1 - settings.max_pool_size
            low_stmt = (
                select(TopicPoolItem.id)
                .where(TopicPoolItem.auto_source == "monitor")
                .order_by(TopicPoolItem.heat_score.asc())
                .limit(excess)
            )
            ids = [row[0] for row in (await session.execute(low_stmt)).all()]
            if ids:
                await session.execute(delete(TopicPoolItem).where(TopicPoolItem.id.in_(ids)))
                await session.commit()
                overflow_deleted = len(ids)
            logger.info(
                f"PoolManager 步骤2：超量 {total_after_step1} > {settings.max_pool_size}，"
                f"删除最低分 {overflow_deleted} 条"
            )

        # 步骤3：若低于最低水位，触发紧急补抓
        refetch_result = None
        total_after_step2 = await self._count(session)
        if total_after_step2 < settings.pool_min_threshold:
            logger.info(
                f"PoolManager 步骤3：池子 {total_after_step2} < {settings.pool_min_threshold}，触发紧急补抓"
            )
            refetch_result = await self.monitor.run(session)

        after = await self._count(session)
        logger.info(
            f"PoolManager 清理完成: before={before} expired={expired_deleted} "
            f"overflow={overflow_deleted} after={after} refetch={refetch_result is not None}"
        )
        return {
            "before": before,
            "expired_deleted": expired_deleted,
            "overflow_deleted": overflow_deleted,
            "refetch": refetch_result,
            "after": after,
        }

    @staticmethod
    async def _count(session: AsyncSession) -> int:
        result = await session.execute(select(func.count()).select_from(TopicPoolItem))
        return int(result.scalar() or 0)
