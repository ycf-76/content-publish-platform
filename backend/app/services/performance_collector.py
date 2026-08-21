"""发布内容表现回采 + 分析权重校准。

分析智能体优化方案 阶段4：反馈闭环。

核心流程：
1. T+7 回采：每天 03:00 扫描 7 天前发布的内容，采集实际表现数据
2. 权重校准：每周一 04:00 分析过去 4 周的表现数据，校准 viral_score 权重

校准逻辑：
- 初始权重：rate_weight=0.5, viral_weight=0.3, likes_weight=0.2
- 如果"内容型爆款"特征对应的 is_replicated=true 比例 > 60%，
  提高 interaction_rate 的权重
- 校准结果记录到 analysis_weight_history 表，可追溯
- 积累 10 条以上发布记录后才触发校准，避免小样本过拟合
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update, and_, func

from app.db.models import AnalysisWeightHistory, PublishedContentPerformance
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

# 当前权重（可被校准更新）
_current_weights: dict[str, float] = {
    "rate_weight": 0.5,
    "viral_weight": 0.3,
    "likes_weight": 0.2,
}

# 校准门槛
_MIN_RECORDS_FOR_CALIBRATION = 10
_REPLICATION_THRESHOLD = 0.3


def get_current_weights() -> dict[str, float]:
    """返回当前 viral_score 的三个权重。"""
    return dict(_current_weights)


def compute_performance_score(note: dict) -> float:
    """计算单条发布内容的综合表现分（复用 Layer 1 同样的公式思路）。

    用发布者自己的粉丝数作为分母，衡量内容本身的引爆能力。
    """
    import math

    likes = max(note.get("likes", 0), 0)
    comments = max(note.get("comments", 0), 0)
    fans = max(note.get("author_fans", 1), 1)

    interaction_rate = likes / fans
    viral_coefficient = likes / (math.sqrt(fans) + 1)
    quality_score = comments / max(likes, 1)

    weights = get_current_weights()
    score = (
        interaction_rate * weights["rate_weight"]
        + viral_coefficient * weights["viral_weight"]
        + likes * weights["likes_weight"]
    )
    return round(score, 4)


async def record_publication(
    user_id: str,
    workflow_id: str,
    topic: str | None = None,
    selected_pattern: dict | None = None,
    selected_direction: dict | None = None,
    published_note_id: str | None = None,
) -> str:
    """记录一次发布行为，供 T+7 回采。

    在工作流产出内容并成功发布后调用。
    """
    from datetime import UTC, datetime

    async with AsyncSessionLocal() as db:
        record = PublishedContentPerformance(
            user_id=user_id,
            workflow_id=workflow_id,
            published_note_id=published_note_id,
            topic=topic,
            selected_pattern=selected_pattern,
            selected_direction=selected_direction,
            published_at=datetime.now(UTC),
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)
        logger.info(
            f"[performance_collector] recorded publication: "
            f"workflow={workflow_id}, note={published_note_id}"
        )
        return record.id


async def collect_performance_7d() -> int:
    """T+7 回采：扫描 7 天前发布的内容，采集实际表现数据。

    Returns:
        成功回采的记录数
    """
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    target_start = now - timedelta(days=7, hours=12)
    target_end = now - timedelta(days=6, hours=12)

    async with AsyncSessionLocal() as db:
        stmt = select(PublishedContentPerformance).where(
            and_(
                PublishedContentPerformance.published_at.between(target_start, target_end),
                PublishedContentPerformance.collected_at.is_(None),
                PublishedContentPerformance.published_note_id.isnot(None),
            )
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        if not records:
            logger.info("[performance_collector] T+7: no records to collect")
            return 0

        collected = 0
        for record in records:
            try:
                stats = await _fetch_note_stats(record.published_note_id)
                if stats is None:
                    continue

                perf_score = compute_performance_score({
                    "likes": stats.get("likes", 0),
                    "comments": stats.get("comments", 0),
                    "author_fans": stats.get("author_fans", 1),
                })
                is_replicated = perf_score > _REPLICATION_THRESHOLD

                await db.execute(
                    update(PublishedContentPerformance)
                    .where(PublishedContentPerformance.id == record.id)
                    .values(
                        collected_likes=stats.get("likes", 0),
                        collected_collects=stats.get("collects", 0),
                        collected_comments=stats.get("comments", 0),
                        collected_shares=stats.get("shares", 0),
                        collected_at=now,
                        performance_score=perf_score,
                        is_replicated=is_replicated,
                    )
                )
                collected += 1

            except Exception as e:
                logger.warning(
                    f"[performance_collector] T+7 collect failed for "
                    f"record={record.id}: {e}"
                )

        await db.commit()
        logger.info(
            f"[performance_collector] T+7: collected {collected}/{len(records)} records"
        )
        return collected


async def _fetch_note_stats(note_id: str) -> dict | None:
    """通过 MCP 抓取发布笔记的当前数据。

    TODO: 接入 MCP client 后实现。当前返回 None 跳过。
    """
    # 预留接口：后续接入 MCP client 后实现
    # from app.account.mcp_manager import get_mcp_manager
    # mcp = await get_mcp_manager()
    # return await mcp.get_note_stats(note_id)
    logger.debug(f"[performance_collector] _fetch_note_stats: not implemented, note_id={note_id}")
    return None


async def calibrate_weights() -> dict[str, float] | None:
    """基于历史表现数据校准 viral_score 的三个权重。

    每周执行一次，分析过去 4 周的 is_replicated 数据。
    积累 10 条以上发布记录后才触发校准。

    Returns:
        新权重 dict，或 None（数据不足，未校准）
    """
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    four_weeks_ago = now - timedelta(days=28)

    async with AsyncSessionLocal() as db:
        stmt = select(PublishedContentPerformance).where(
            and_(
                PublishedContentPerformance.collected_at > four_weeks_ago,
                PublishedContentPerformance.is_replicated.isnot(None),
            )
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

        if len(records) < _MIN_RECORDS_FOR_CALIBRATION:
            logger.info(
                f"[performance_collector] calibration skipped: "
                f"only {len(records)} records (need {_MIN_RECORDS_FOR_CALIBRATION})"
            )
            return None

        replicated = [r for r in records if r.is_replicated]
        if len(replicated) < 3:
            logger.info("[performance_collector] calibration skipped: too few replicated")
            return None

        # 统计成功复制的内容，采用了哪些 viral_type 的特征
        type_counts: dict[str, int] = {"内容型": 0, "双重型": 0, "粉丝型": 0, "普通": 0}
        for r in replicated:
            pattern = r.selected_pattern or {}
            viral_type = pattern.get("source_viral_type", "普通")
            type_counts[viral_type] = type_counts.get(viral_type, 0) + 1

        total = sum(type_counts.values())
        content_ratio = type_counts.get("内容型", 0) / total if total > 0 else 0
        dual_ratio = type_counts.get("双重型", 0) / total if total > 0 else 0

        old_weights = get_current_weights()
        new_weights = dict(old_weights)

        # 内容型占比高 → 提高 interaction_rate 权重
        if content_ratio > 0.6:
            new_weights["rate_weight"] = min(old_weights["rate_weight"] + 0.05, 0.7)
            new_weights["likes_weight"] = max(old_weights["likes_weight"] - 0.03, 0.1)
            new_weights["viral_weight"] = 1.0 - new_weights["rate_weight"] - new_weights["likes_weight"]
        elif content_ratio < 0.3:
            new_weights["rate_weight"] = max(old_weights["rate_weight"] - 0.05, 0.3)
            new_weights["likes_weight"] = min(old_weights["likes_weight"] + 0.03, 0.4)
            new_weights["viral_weight"] = 1.0 - new_weights["rate_weight"] - new_weights["likes_weight"]

        # 双重型占比高 → 提高 viral_coefficient 权重
        if dual_ratio > 0.4:
            new_weights["viral_weight"] = min(old_weights["viral_weight"] + 0.05, 0.5)
            new_weights["likes_weight"] = max(new_weights["likes_weight"] - 0.05, 0.1)
            new_weights["rate_weight"] = 1.0 - new_weights["viral_weight"] - new_weights["likes_weight"]

        # 归一化确保总和为 1
        total_w = sum(new_weights.values())
        if total_w > 0:
            new_weights = {k: round(v / total_w, 4) for k, v in new_weights.items()}

        # 记录权重变更历史
        for wname in ("rate_weight", "viral_weight", "likes_weight"):
            if new_weights[wname] != old_weights[wname]:
                history = AnalysisWeightHistory(
                    weight_name=wname,
                    old_value=old_weights[wname],
                    new_value=new_weights[wname],
                    adjustment_reason=(
                        f"T+7 calibration: content_ratio={content_ratio:.2f}, "
                        f"dual_ratio={dual_ratio:.2f}, "
                        f"replicated={len(replicated)}/{len(records)}"
                    ),
                )
                db.add(history)

        await db.commit()

        # 更新内存中的权重
        _current_weights.update(new_weights)
        logger.info(
            f"[performance_collector] weights calibrated: "
            f"{old_weights} → {new_weights}"
        )
        return new_weights