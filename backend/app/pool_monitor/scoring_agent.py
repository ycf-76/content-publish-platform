"""价值评分器（ScoringAgent）。

对每条新入库内容计算综合热度分（满分 100）：
- 互动量得分（40分）：likes*0.3 + collects*0.4 + comments*0.2 + shares*0.1，
  归一化到 40 分制（基准：赞 > 5000 得满分）
- 爆发力得分（35分）：(comments + shares) / 总互动量，比例越高得分越高
  （说明有争议或实用性）
- 时效系数（25分）：发布 6h 内 ×1.2 加成；超过 24h 后每过 1h 扣 2 分

入池决策：综合热度分 ≥ 阈值（默认 60）则入池，否则丢弃。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.pool_monitor.config import get_pool_settings

logger = logging.getLogger(__name__)

# 热度状态常量（v6 合并后不再依赖独立 models.py，直接定义）
HEAT_STATUS_ACTIVE = "活跃"
HEAT_STATUS_DECAY = "衰退"
HEAT_STATUS_EXPIRED = "过期"


class ScoringAgent:
    """价值评分器：计算综合热度分并做入池决策。"""

    def compute_heat_score(
        self,
        raw_metrics: dict,
        published_at: datetime | None,
        platform: str = "",
    ) -> float:
        """计算综合热度分（0-100）。

        Args:
            raw_metrics: {"likes","collects","comments","shares"}
            published_at: 原始发布时间（aware/naive 均可，naive 视为 UTC）
            platform: 平台名（用于动态选择评分基准，空则用默认基准）
        """
        likes = float(raw_metrics.get("likes", 0) or 0)
        collects = float(raw_metrics.get("collects", 0) or 0)
        comments = float(raw_metrics.get("comments", 0) or 0)
        shares = float(raw_metrics.get("shares", 0) or 0)
        settings = get_pool_settings()

        # ===== 1. 互动量得分（40分）=====
        # 加权互动量归一化到 40 分制
        # 基准按平台动态选择：不同平台互动量级差异大，统一基准会误杀小众平台
        weighted = likes * 0.3 + collects * 0.4 + comments * 0.2 + shares * 0.1
        baselines = settings.platform_score_baselines or {}
        baseline = baselines.get(platform, settings.score_likes_baseline)
        baseline = max(baseline, 1)
        interaction_score = min(40.0, (weighted / baseline) * 40.0)

        # ===== 2. 爆发力得分（35分）=====
        # (评论+转发) 占总互动比例，比例越高越有争议/实用性
        total = likes + collects + comments + shares
        if total > 0:
            explosive_score = ((comments + shares) / total) * 35.0
        else:
            explosive_score = 0.0

        # ===== 3. 时效系数（25分）=====
        time_score = self._compute_time_score(published_at)

        score = interaction_score + explosive_score + time_score
        # 时效 1.2 加成可能使总分略超 100，封顶
        return round(min(100.0, max(0.0, score)), 2)

    @staticmethod
    def _compute_time_score(published_at: datetime | None) -> float:
        """时效分：6h 内 ×1.2 加成；24h 内满分；超 24h 每小时扣 2 分。"""
        if published_at is None:
            # 无发布时间（Tavily basic 等），给中等偏上时效分
            # 不过度惩罚未知时间（新闻源默认按较新处理）
            return 20.0
        now = datetime.now(timezone.utc)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        delta_hours = max(0.0, (now - published_at).total_seconds() / 3600.0)

        if delta_hours <= 6:
            return 25.0 * 1.2
        elif delta_hours <= 24:
            return 25.0
        else:
            return max(0.0, 25.0 - (delta_hours - 24) * 2.0)

    @staticmethod
    def should_pool(score: float) -> bool:
        """入池决策：分数 ≥ 阈值则入池。"""
        return score >= get_pool_settings().heat_score_threshold

    @staticmethod
    def decide_heat_status(score: float, published_at: datetime | None) -> str:
        """根据分数与时效决定热度状态（活跃/衰退/过期）。"""
        if published_at is None:
            return HEAT_STATUS_ACTIVE if score >= 60 else HEAT_STATUS_DECAY

        now = datetime.now(timezone.utc)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        hours = max(0.0, (now - published_at).total_seconds() / 3600.0)

        if hours > 72:
            return HEAT_STATUS_EXPIRED
        if hours > 24 or score < 50:
            return HEAT_STATUS_DECAY
        return HEAT_STATUS_ACTIVE
