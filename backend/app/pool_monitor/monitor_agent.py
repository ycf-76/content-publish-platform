"""监控智能体（MonitorAgent）—— v7 真实抓取版。

职责：每 10 分钟遍历 source_manager 已注册的各大平台 → 调 get_trending()
     抓全站热点 → 过滤近期内容 → SimHash 去重 → LLM 三维分类 → 评分入池
     （auto_source="monitor"），与手动抓取的数据统一在 topic_pool_items 表。

数据源：复用工作流的 source_manager（HackerNews / Reddit / Tavily / Builtin 等真实源），
     不再使用 MockDataSource。小红书因风控跳过（get_trending 需关键词且受频率限制）。

异常容错：单条数据解析失败不影响整体，捕获异常记日志后继续下一条。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.sources.base import TrendingContent
from app.tools.sources.manager import source_manager
from app.db.models import TopicPoolItem
from app.pool_monitor.config import get_effective_llm_api_key, get_pool_settings
from app.pool_monitor.scoring_agent import ScoringAgent
from app.pool_monitor.simhash_utils import hamming_distance, simhash

logger = logging.getLogger(__name__)

HEAT_STATUS_ACTIVE = "活跃"
HEAT_STATUS_DECAY = "衰退"
HEAT_STATUS_EXPIRED = "过期"

# 监控抓取时跳过的平台（风控/需关键词/不适用全站热门）
_MONITOR_SKIP_PLATFORMS = {"xiaohongshu"}


def _parse_published_at(s: str) -> datetime | None:
    """把 ISO8601 字符串解析成 aware datetime，失败/空返回 None。"""
    if not s or not s.strip():
        return None
    try:
        # 兼容末尾 Z 写法
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# LLM 分类（含关键词降级）
# ---------------------------------------------------------------------------

_CLASSIFY_PROMPT = """你是小红书内容分类器。根据以下内容，从三个维度各选一个标签：

情绪维度：情绪宣泄 / 知识科普 / 种草拔草 / 避雷吐槽 / 情感共鸣
场景维度：通勤 / 卧室 / 办公室 / 旅行 / 宿舍 / 健身房
视觉形式：大字报 / 前后对比图 / 合集拼图 / 沉浸式Vlog / 纯文字

内容：{text}

仅输出 JSON（不要 markdown，不要解释）：
{{"emotion": "情绪维度标签", "scene": "场景维度标签", "visual": "视觉形式标签"}}
"""


async def _classify_with_llm(text: str) -> dict:
    """调用 LLM 进行三维分类。失败时降级为关键词匹配。"""
    import json

    settings = get_pool_settings()
    api_key = get_effective_llm_api_key()
    if not api_key:
        return _classify_by_keywords(text)

    base_url = (settings.deepseek_base_url or "https://api.deepseek.com").rstrip("/")
    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": settings.llm_model,
        "messages": [{"role": "user", "content": _CLASSIFY_PROMPT.format(text=text[:300])}],
        "temperature": 0.1,
        "max_tokens": 200,
    }

    try:
        async with httpx.AsyncClient(timeout=settings.llm_timeout_seconds) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            parsed = json.loads(content)
            return {
                "emotion": str(parsed.get("emotion", "情感共鸣")).strip(),
                "scene": str(parsed.get("scene", "卧室")).strip(),
                "visual": str(parsed.get("visual", "纯文字")).strip(),
            }
    except Exception as e:
        logger.warning(f"LLM 分类失败，降级为关键词匹配: {e}")
        return _classify_by_keywords(text)


def _classify_by_keywords(text: str) -> dict:
    """基于关键词匹配的降级分类方案。"""
    emotion = "情感共鸣"
    if any(k in text for k in ["避雷", "踩雷", "别买", "难用", "智商税"]):
        emotion = "避雷吐槽"
    elif any(k in text for k in ["推荐", "种草", "好用", "回购", "安利"]):
        emotion = "种草拔草"
    elif any(k in text for k in ["教程", "攻略", "技巧", "知识", "科普", "必看"]):
        emotion = "知识科普"
    elif any(k in text for k in ["气死", "烦", "崩溃", "吐槽", "逼疯"]):
        emotion = "情绪宣泄"

    scene = "卧室"
    if any(k in text for k in ["通勤", "地铁", "上班路上"]):
        scene = "通勤"
    elif any(k in text for k in ["办公室", "打工", "工位", "久坐"]):
        scene = "办公室"
    elif any(k in text for k in ["旅行", "旅游", "出游", "行李"]):
        scene = "旅行"
    elif any(k in text for k in ["宿舍", "学生党"]):
        scene = "宿舍"
    elif any(k in text for k in ["健身", "运动", "健身房"]):
        scene = "健身房"

    visual = "纯文字"
    if any(k in text for k in ["合集", "盘点", "清单"]):
        visual = "合集拼图"
    elif any(k in text for k in ["对比", "前后", "改造"]):
        visual = "前后对比图"
    elif any(k in text for k in ["vlog", "Vlog", "记录", "沉浸"]):
        visual = "沉浸式Vlog"
    elif any(k in text for k in ["大字", "金句", "语录"]):
        visual = "大字报"

    return {"emotion": emotion, "scene": scene, "visual": visual}


# ---------------------------------------------------------------------------
# 监控智能体
# ---------------------------------------------------------------------------


class MonitorAgent:
    """监控智能体：遍历各大平台抓热点 → 去重 → 分类 → 评分 → 写入 topic_pool_items。

    复用工作流的 source_manager，调各平台 get_trending() 抓全站热门内容。
    小红书因风控跳过；其他平台（HackerNews / Reddit / Tavily / Builtin）按真实数据抓取。
    """

    def __init__(self, scorer: ScoringAgent | None = None) -> None:
        # 直接复用模块级单例 source_manager（与工作流共享同一批已初始化的数据源）
        self.source_manager = source_manager
        self.scorer = scorer or ScoringAgent()

    async def run(self, session: AsyncSession, user_id: str | None = None) -> dict:
        """执行一次完整抓取流程，返回统计摘要。"""
        settings = get_pool_settings()
        fetched = new_count = update_count = skip_count = fail_count = 0

        # 1. 遍历已注册平台抓全站热点
        platforms = [
            p for p in self.source_manager.list_platforms()
            if p not in _MONITOR_SKIP_PLATFORMS
        ]
        if not platforms:
            logger.warning("MonitorAgent: source_manager 无可用平台，跳过抓取")
            await session.commit()
            return {"fetched": 0, "new": 0, "updated": 0, "skipped": 0, "failed": 0}

        # 每平台配额：总预算 / 平台数，至少 3 条
        per_platform = max(settings.max_fetch_per_run // max(len(platforms), 1), 3)

        raw_items: list[TrendingContent] = []
        for plat in platforms:
            source = self.source_manager.get_source(plat)
            if source is None:
                continue
            try:
                items = await source.get_trending(limit=per_platform)
                raw_items.extend(items)
                logger.info(f"MonitorAgent 平台 {plat}: 抓到 {len(items)} 条")
            except Exception as e:
                logger.warning(f"MonitorAgent 平台 {plat} 抓取失败: {e}")

        # --- 用户偏好关键词抓取（个性化） ---
        pref_fetched = 0
        if user_id is not None:
            from app.services import agent_memory
            kws = await agent_memory.get_search_keywords(user_id, limit=3)
            if kws:
                pref_limit = max(per_platform // 2, 2)
                for plat in platforms:
                    source = self.source_manager.get_source(plat)
                    if source is None:
                        continue
                    for kw in kws:
                        try:
                            kw_items = await source.search_trending(keyword=kw, limit=pref_limit)
                            raw_items.extend(kw_items)
                            pref_fetched += len(kw_items)
                        except Exception as e:
                            logger.warning(
                                f"MonitorAgent 偏好抓取失败 platform={plat} keyword={kw!r}: {e}"
                            )
                logger.info(
                    f"MonitorAgent 偏好关键词触发抓取: user={user_id}, "
                    f"keywords={kws}, added={pref_fetched} 条"
                )

        fetched = len(raw_items)
        if fetched == 0:
            logger.info("MonitorAgent: 所有平台均无数据")
            await session.commit()
            return {"fetched": 0, "new": 0, "updated": 0, "skipped": 0, "failed": 0}

        # 2. 预加载池中近 7 天的指纹（减少内存占用）
        existing_fps = await self._load_existing_fingerprints(session)

        # 2.5 LLM 分类缓存：同一批次中相似内容共享分类结果，避免重复调 LLM
        classify_cache: list[tuple[str, dict]] = []  # [(fingerprint, dims)]

        # 3. 逐条处理
        for tc in raw_items:
            try:
                published = _parse_published_at(tc.published_at)
                if not self._is_recent(published):
                    logger.info(
                        f"MonitorAgent skip(超时): platform={tc.platform} "
                        f"title={tc.title[:30]} published={tc.published_at}"
                    )
                    skip_count += 1
                    continue

                fp_text = f"{tc.title}{(tc.summary or '')[:50]}"
                fp = simhash(fp_text)
                similar = self._find_similar(fp, existing_fps, settings.simhash_hamming_threshold)

                if similar is not None:
                    # 命中重复：只更新互动数据
                    await self._update_metrics(session, similar, tc, published)
                    update_count += 1
                    continue

                # LLM 三维分类（先查批次内缓存，命中则跳过 LLM 调用）
                dims: dict | None = None
                for cached_fp, cached_dims in classify_cache:
                    if hamming_distance(fp, cached_fp) <= settings.simhash_hamming_threshold:
                        dims = cached_dims
                        break
                if dims is None:
                    dims = await _classify_with_llm(f"{tc.title} {tc.summary or tc.content}")
                    classify_cache.append((fp, dims))

                # 评分（TrendingContent 无 collects 字段，置 0；platform 用于动态基准）
                raw_metrics = {
                    "likes": tc.likes,
                    "collects": 0,
                    "comments": tc.comments,
                    "shares": tc.shares,
                }
                score = self.scorer.compute_heat_score(raw_metrics, published, platform=tc.platform)

                if self.scorer.should_pool(score):
                    local_cover = tc.cover_img or None
                    if local_cover:
                        try:
                            from app.services.image_store import cache_cover_image
                            local_cover = await cache_cover_image(tc.content_id, local_cover)
                        except Exception as img_err:
                            logger.warning(f"MonitorAgent 封面图下载失败: {img_err}")

                    obj = TopicPoolItem(
                        platform=tc.platform,
                        title=tc.title[:500],
                        summary=(tc.summary or tc.content)[:2000],
                        content=tc.content or tc.summary or "",
                        author=tc.author,
                        likes=tc.likes,
                        collects=0,
                        comments=tc.comments,
                        shares=tc.shares,
                        cover_img=local_cover,
                        source_keyword="[monitor]",
                        auto_source="monitor",
                        simhash_fingerprint=fp,
                        heat_score=score,
                        heat_status=self.scorer.decide_heat_status(score, published),
                        dimensions=dims,
                        published_at=published,
                    )
                    session.add(obj)
                    await session.flush()
                    existing_fps.append((obj.id, fp))
                    new_count += 1
                else:
                    logger.info(
                        f"MonitorAgent skip(评分不足): platform={tc.platform} "
                        f"score={score:.2f} likes={tc.likes} comments={tc.comments} "
                        f"title={tc.title[:30]}"
                    )
                    skip_count += 1
            except Exception as e:
                logger.exception(f"MonitorAgent 处理单条失败，跳过: {e}")
                fail_count += 1

        await session.commit()
        logger.info(
            f"MonitorAgent 完成: fetched={fetched} new={new_count} "
            f"updated={update_count} skipped={skip_count} failed={fail_count}"
        )

        # 推送全局通知（有新内容时才推送，避免空通知打扰用户）
        if new_count > 0:
            try:
                from app.services.notification_bus import notification_bus
                await notification_bus.publish(
                    "topic_pool_monitor",
                    {
                        "fetched": fetched,
                        "new": new_count,
                        "updated": update_count,
                        "skipped": skip_count,
                        "failed": fail_count,
                        "message": f"选题池监控完成，发现 {new_count} 条新内容",
                    },
                )
            except Exception as notify_err:
                logger.warning(f"MonitorAgent 通知推送失败: {notify_err}")

        return {
            "fetched": fetched,
            "new": new_count,
            "updated": update_count,
            "skipped": skip_count,
            "failed": fail_count,
        }

    @staticmethod
    def _is_recent(published_at: datetime | None, within_hours: int = 24) -> bool:
        """是否在最近 within_hours 小时内（当日窗口）。

        严格要求：无发布时间一律视为非当日 → 过滤。
        （Tavily 已在 API 端用 days=1 过滤；HN/builtin 都返回真实或近似的发布时间）
        """
        if published_at is None:
            return False
        now = datetime.now(timezone.utc)
        if published_at.tzinfo is None:
            published_at = published_at.replace(tzinfo=timezone.utc)
        delta_hours = (now - published_at).total_seconds() / 3600.0
        return delta_hours <= within_hours

    @staticmethod
    async def _load_existing_fingerprints(session: AsyncSession) -> list[tuple[str, str]]:
        """预加载池中近 7 天的 (id, simhash_fingerprint)，减少内存占用。"""
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        result = await session.execute(
            select(TopicPoolItem.id, TopicPoolItem.simhash_fingerprint).where(
                TopicPoolItem.simhash_fingerprint.is_not(None),
                TopicPoolItem.created_at >= cutoff,
            )
        )
        return [(row[0], row[1] or "") for row in result.all()]

    @staticmethod
    def _find_similar(
        fp: str,
        existing: list[tuple[str, str]],
        threshold: int,
    ) -> str | None:
        for cid, exist_fp in existing:
            if not exist_fp:
                continue
            if hamming_distance(fp, exist_fp) <= threshold:
                return cid
        return None

    async def _update_metrics(
        self,
        session: AsyncSession,
        item_id: str,
        tc: TrendingContent,
        published_at: datetime | None,
    ) -> None:
        """命中重复时，只更新互动数据与热度分。"""
        obj = await session.get(TopicPoolItem, item_id)
        if obj is None:
            return
        obj.likes = tc.likes
        obj.collects = 0
        obj.comments = tc.comments
        obj.shares = tc.shares
        raw_metrics = {
            "likes": tc.likes,
            "collects": 0,
            "comments": tc.comments,
            "shares": tc.shares,
        }
        obj.heat_score = self.scorer.compute_heat_score(raw_metrics, published_at, platform=obj.platform)
        obj.heat_status = self.scorer.decide_heat_status(obj.heat_score, published_at)