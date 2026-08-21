"""工作流僵尸清理。

解决两类僵尸：
1. review_required 后一直没人审核的 PAUSED 工作流 → 超时终止（释放 DB 脏记录）
2. 节点卡死、长期 running 的工作流 → 超时挂起（释放并发名额）

清理后按 DB 中实际 running 数校准 Redis 并发计数器，保证计数不漂移。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from app.db.models import Workflow, WorkflowStatus
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# 阈值（可后续移到 config）
PAUSED_TIMEOUT_HOURS = 24        # 未审核超过 24h → 终止
RUNNING_TIMEOUT_MINUTES = 120    # 连续 running 超过 2h → 挂起


async def cleanup_stale_workflows() -> dict[str, int]:
    """清理僵尸工作流，返回清理统计。"""
    now = datetime.now(UTC)
    paused_deadline = now - timedelta(hours=PAUSED_TIMEOUT_HOURS)
    running_deadline = now - timedelta(minutes=RUNNING_TIMEOUT_MINUTES)

    result = {"paused_terminated": 0, "running_suspended": 0}

    async with AsyncSessionLocal() as db:
        # 1. 长时间 PAUSED → 终止（已释放过并发名额，这里只清 DB 记录）
        stale_paused = await db.scalars(
            select(Workflow).where(
                Workflow.status == WorkflowStatus.PAUSED,
                Workflow.updated_at < paused_deadline,
            )
        )
        for wf in stale_paused:
            wf.status = WorkflowStatus.TERMINATED
            result["paused_terminated"] += 1

        # 2. 长期 running → 挂起（释放并发名额）
        stale_running = await db.scalars(
            select(Workflow).where(
                Workflow.status == WorkflowStatus.RUNNING,
                Workflow.updated_at < running_deadline,
            )
        )
        for wf in stale_running:
            wf.status = WorkflowStatus.SUSPENDED
            result["running_suspended"] += 1

        changed = result["paused_terminated"] > 0 or result["running_suspended"] > 0
        if changed:
            await db.commit()

            # 3. 用 DB 实际 running 数校准 Redis 并发计数器
            running_count = await db.scalar(
                select(func.count()).select_from(Workflow).where(
                    Workflow.status == WorkflowStatus.RUNNING
                )
            )
            from app.cache import redis_client

            await redis_client.set("count:active_workflows", running_count or 0)

    logger.info(f"[workflow_cleanup] {result}")
    return result
