"""自我归因引擎：从我的历史作品中找出什么对我有效。

核心流程：
1. 读取 published_content_performance 中已回采的记录
2. 规则统计：哪些 title_pattern / emotion_trigger / content_structure 对应高 performance_score
3. LLM 归因：让 LLM 总结出写作处方（什么模式对我有效 + 什么对我无效）
4. 写入 AgentMemory（MY_ATTRIBUTION + AVOID_PATTERNS）

冷启动策略：
- 我的作品 < 10 篇：全用别人的爆款模式（权重 0）
- 10-30 篇：我的模式权重从 0 线性增长到 0.6
- 30+ 篇：我的模式权重 0.6 → 0.8（上限 0.8，始终保留别人模式的参考）
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import desc, select, and_

from app.db.models import MemoryType, PublishedContentPerformance
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

_ATTRIBUTION_TRIGGER_INTERVAL = 5
_MIN_WORKS_FOR_LLM_ATTRIBUTION = 5


def get_attribution_weight(my_works_count: int) -> float:
    """我的模式 vs 别人模式的混合权重。

    Returns:
        我的模式权重（0.0 ~ 0.8）。
        别人模式权重 = 1 - 此值。
    """
    if my_works_count < 10:
        return 0.0
    elif my_works_count < 30:
        return (my_works_count - 10) / 20 * 0.6
    else:
        return min(0.8, 0.6 + (my_works_count - 30) * 0.01)


def blend_patterns(
    my_patterns: dict,
    others_patterns: dict | None,
    my_works_count: int,
) -> dict:
    """混合我的模式和别人的模式。

    Args:
        my_patterns: 我的归因处方
        others_patterns: 别人的爆款模式（来自 analyze Layer2/3）
        my_works_count: 我的作品数量

    Returns:
        混合后的模式 dict
    """
    my_weight = get_attribution_weight(my_works_count)
    others_weight = 1.0 - my_weight

    result: dict[str, Any] = {
        "my_weight": round(my_weight, 3),
        "others_weight": round(others_weight, 3),
    }

    if my_weight > 0 and my_patterns:
        result["what_works"] = my_patterns.get("what_works", [])
        result["best_title_pattern"] = my_patterns.get("best_title_pattern", "")
        result["best_emotion_trigger"] = my_patterns.get("best_emotion_trigger", "")
        result["best_content_structure"] = my_patterns.get("best_content_structure", "")

    if others_weight > 0 and others_patterns:
        result["others_patterns"] = others_patterns

    return result


async def maybe_trigger_attribution(user_id: str) -> bool:
    """检查是否触发归因分析。

    每积累 _ATTRIBUTION_TRIGGER_INTERVAL 篇新回采数据触发一次。
    """
    async with AsyncSessionLocal() as db:
        stmt = select(
            __import__("sqlalchemy").func.count()
        ).select_from(PublishedContentPerformance).where(
            and_(
                PublishedContentPerformance.user_id == user_id,
                PublishedContentPerformance.collected_at.isnot(None),
            )
        )
        count = await db.scalar(stmt) or 0

    if count and count % _ATTRIBUTION_TRIGGER_INTERVAL == 0:
        engine = SelfAttributionEngine()
        await engine.generate_writing_prescription(user_id)
        return True
    return False


class SelfAttributionEngine:
    """自我归因引擎：从我的历史作品中找出什么对我有效。"""

    async def generate_writing_prescription(self, user_id: str) -> dict | None:
        """生成写作处方并写入 AgentMemory。

        Returns:
            写作处方 dict，或 None（数据不足）
        """
        works = await self._load_my_works(user_id)
        if len(works) < _MIN_WORKS_FOR_LLM_ATTRIBUTION:
            logger.info(
                f"[self_attribution] skipped for user {user_id}: "
                f"only {len(works)} works (need {_MIN_WORKS_FOR_LLM_ATTRIBUTION})"
            )
            return None

        patterns = self._rule_based_attribution(works)

        prescription = await self._llm_attribution(user_id, works, patterns)

        if not prescription:
            prescription = patterns

        from app.services.agent_memory import save_memory
        await save_memory(
            user_id=user_id,
            memory_type=MemoryType.MY_ATTRIBUTION,
            memory_key="writing_prescription",
            memory_value=prescription,
            source="self_attribution",
            importance=0.9,
        )
        await save_memory(
            user_id=user_id,
            memory_type=MemoryType.AVOID_PATTERNS,
            memory_key="avoid_list",
            memory_value={"items": patterns.get("what_doesnt", [])},
            source="self_attribution",
            importance=0.7,
        )

        logger.info(
            f"[self_attribution] generated prescription for user {user_id}: "
            f"works={len(works)}, what_works={len(patterns.get('what_works', []))}, "
            f"what_doesnt={len(patterns.get('what_doesnt', []))}"
        )
        return prescription

    async def _load_my_works(self, user_id: str) -> list[dict]:
        """加载已回采的作品数据。"""
        async with AsyncSessionLocal() as db:
            stmt = (
                select(PublishedContentPerformance)
                .where(
                    and_(
                        PublishedContentPerformance.user_id == user_id,
                        PublishedContentPerformance.collected_at.isnot(None),
                    )
                )
                .order_by(desc(PublishedContentPerformance.performance_score))
                .limit(50)
            )
            result = await db.scalars(stmt)
            records = list(result.all())

        works = []
        for r in records:
            works.append({
                "id": r.id,
                "title": r.title or "",
                "topic": r.topic or "",
                "platform": r.platform,
                "performance_score": r.performance_score or 0.0,
                "predicted_viral_score": r.predicted_viral_score,
                "actual_viral_score": r.actual_viral_score,
                "prediction_error": r.prediction_error,
                "likes": r.collected_likes,
                "collects": r.collected_collects,
                "comments": r.collected_comments,
                "shares": r.collected_shares,
                "title_pattern": r.title_pattern,
                "emotion_trigger": r.emotion_trigger,
                "content_structure": r.content_structure,
                "is_replicated": r.is_replicated,
            })
        return works

    def _rule_based_attribution(self, works: list[dict]) -> dict:
        """规则统计归因：哪些特征对应高 performance_score。"""
        from collections import Counter

        if not works:
            return {"what_works": [], "what_doesnt": []}

        scores = [w["performance_score"] for w in works if w["performance_score"] > 0]
        if not scores:
            return {"what_works": [], "what_doesnt": []}

        sorted_scores = sorted(scores)
        median_score = sorted_scores[len(sorted_scores) // 2]

        high_works = [w for w in works if w["performance_score"] >= median_score]
        low_works = [w for w in works if w["performance_score"] < median_score]

        what_works: list[dict] = []
        what_doesnt: list[dict] = []

        title_patterns_high = Counter(w.get("title_pattern") for w in high_works if w.get("title_pattern"))
        title_patterns_low = Counter(w.get("title_pattern") for w in low_works if w.get("title_pattern"))
        for pattern, count in title_patterns_high.most_common(5):
            if pattern and count >= 2:
                what_works.append({"pattern": f"标题模式: {pattern}", "evidence": f"{count}篇高于中位数"})

        for pattern, count in title_patterns_low.most_common(3):
            if pattern and count >= 2 and pattern not in dict(title_patterns_high):
                what_doesnt.append({"pattern": f"标题模式: {pattern}", "reason": f"{count}篇低于中位数"})

        emotion_high = Counter(w.get("emotion_trigger") for w in high_works if w.get("emotion_trigger"))
        emotion_low = Counter(w.get("emotion_trigger") for w in low_works if w.get("emotion_trigger"))
        for emotion, count in emotion_high.most_common(3):
            if emotion and count >= 2:
                what_works.append({"pattern": f"情绪触发: {emotion}", "evidence": f"{count}篇高于中位数"})

        for emotion, count in emotion_low.most_common(2):
            if emotion and count >= 2 and emotion not in dict(emotion_high):
                what_doesnt.append({"pattern": f"情绪触发: {emotion}", "reason": f"{count}篇低于中位数"})

        structure_high = Counter(w.get("content_structure") for w in high_works if w.get("content_structure"))
        for struct, count in structure_high.most_common(3):
            if struct and count >= 2:
                what_works.append({"pattern": f"内容结构: {struct}", "evidence": f"{count}篇高于中位数"})

        best_title = title_patterns_high.most_common(1)[0][0] if title_patterns_high else None
        best_emotion = emotion_high.most_common(1)[0][0] if emotion_high else None
        best_structure = structure_high.most_common(1)[0][0] if structure_high else None

        return {
            "what_works": what_works[:10],
            "what_doesnt": what_doesnt[:5],
            "best_title_pattern": best_title,
            "best_emotion_trigger": best_emotion,
            "best_content_structure": best_structure,
            "median_score": round(median_score, 4),
            "total_works": len(works),
            "high_works": len(high_works),
            "low_works": len(low_works),
        }

    async def _llm_attribution(
        self, user_id: str, works: list[dict], rule_patterns: dict
    ) -> dict | None:
        """LLM 归因：让 LLM 总结出写作处方。"""
        try:
            from app.engine.factory import get_deepseek_llm
            llm = get_deepseek_llm(temperature=0.3)
            if llm is None:
                return None
        except Exception:
            return None

        works_summary = []
        for w in works[:20]:
            works_summary.append(
                f"- 标题: {w['title'][:50]}, "
                f"点赞: {w['likes']}, 收藏: {w['collects']}, "
                f"评论: {w['comments']}, "
                f"表现分: {w['performance_score']:.2f}, "
                f"{'✓爆款' if w.get('is_replicated') else '✗普通'}"
            )

        prompt = f"""你是一位数据分析专家，请分析以下小红书作品数据，找出什么模式对这个创作者有效。

**我的作品数据**（按表现分排序）:
{chr(10).join(works_summary)}

**规则统计初步结论**:
- 对我有效: {rule_patterns.get('what_works', [])}
- 对我无效: {rule_patterns.get('what_doesnt', [])}

请输出 JSON（不要 markdown fence）:
{{
  "what_works": [{{"pattern": "模式描述", "evidence": "证据"}}],
  "what_doesnt": [{{"pattern": "模式描述", "reason": "原因"}}],
  "best_title_pattern": "最佳标题模式",
  "best_emotion_trigger": "最佳情绪触发",
  "best_content_structure": "最佳内容结构",
  "writing_tips": ["写作建议1", "写作建议2", "写作建议3"]
}}"""

        try:
            raw = await llm.chat(messages=[{"role": "user", "content": prompt}])
            if not raw:
                return None

            import json
            content = raw.get("content", "") if isinstance(raw, dict) else str(raw)
            content = content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
                content = content.strip()
            if content.endswith("```"):
                content = content[:-3].strip()

            result = json.loads(content)
            if isinstance(result, dict) and "what_works" in result:
                return result

        except Exception as e:
            logger.warning(f"[self_attribution] LLM attribution failed: {e}")

        return None