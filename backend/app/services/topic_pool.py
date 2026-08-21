"""选题池服务（v6 合并：手动抓取 + 监控数据统一管理）。

管理工作流搜索时后台抓取的其他平台内容 + 监控模块自动抓取评分的热点内容。
两者都写入 topic_pool_items 表，通过 auto_source 字段区分：
- auto_source="manual"：用户主动抓取（fetch_and_save）
- auto_source="monitor"：监控定时抓取并评分入库（MonitorAgent）
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import func, select, delete, case, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TopicPoolItem
from app.db.session import is_sqlite, is_mysql

logger = logging.getLogger(__name__)


class TopicPoolService:
    """选题池 CRUD + 统计 + 手动抓取。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_items(
        self,
        platform: str | None = None,
        keyword: str | None = None,
        favorited_only: bool = False,
        auto_source: str | None = None,
        emotion: str | None = None,
        scene: str | None = None,
        visual: str | None = None,
        sort: str = "created_desc",
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """分页查询选题池条目（手动 + 监控数据统一查询）。

        Args:
            platform: 平台筛选（空 = 全部）
            keyword: 标题/摘要模糊搜索（空 = 不搜）
            favorited_only: 仅看收藏
            auto_source: 来源筛选 manual/monitor（空 = 全部）
            emotion/scene/visual: 三维标签筛选（监控数据才有）
            sort: created_desc（默认，最新在前）/ heat_desc（热度分降序）
            page: 页码（1-based）
            size: 每页条数
        """
        stmt = select(TopicPoolItem)

        if platform:
            stmt = stmt.where(TopicPoolItem.platform == platform)
        if favorited_only:
            stmt = stmt.where(TopicPoolItem.is_favorited.is_(True))
        if auto_source:
            stmt = stmt.where(TopicPoolItem.auto_source == auto_source)
        if keyword:
            pattern = f"%{keyword}%"
            stmt = stmt.where(
                TopicPoolItem.title.ilike(pattern)
                | TopicPoolItem.summary.ilike(pattern)
                | TopicPoolItem.source_keyword.ilike(pattern)
            )
        # 维度筛选：PostgreSQL 用 JSONB 索引查询，SQLite/MySQL 回退 LIKE
        if emotion:
            if is_sqlite or is_mysql:
                stmt = stmt.where(TopicPoolItem.dimensions.like(f'%"emotion": "{emotion}"%'))
            else:
                stmt = stmt.where(TopicPoolItem.dimensions["emotion"].as_string() == emotion)
        if scene:
            if is_sqlite or is_mysql:
                stmt = stmt.where(TopicPoolItem.dimensions.like(f'%"scene": "{scene}"%'))
            else:
                stmt = stmt.where(TopicPoolItem.dimensions["scene"].as_string() == scene)
        if visual:
            if is_sqlite or is_mysql:
                stmt = stmt.where(TopicPoolItem.dimensions.like(f'%"visual": "{visual}"%'))
            else:
                stmt = stmt.where(TopicPoolItem.dimensions["visual"].as_string() == visual)

        # 总数
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar_one()

        # 排序
        if sort == "heat_desc":
            stmt = stmt.order_by(TopicPoolItem.heat_score.desc())
        else:
            stmt = stmt.order_by(TopicPoolItem.created_at.desc())

        # 分页
        offset = (page - 1) * size
        stmt = stmt.offset(offset).limit(size)
        result = await self.db.execute(stmt)
        rows = result.scalars().all()

        items = [_to_dict(row) for row in rows]
        return {"items": items, "total": total, "page": page, "size": size}

    async def toggle_favorite(self, item_id: str) -> dict[str, Any]:
        """切换收藏状态。"""
        stmt = select(TopicPoolItem).where(TopicPoolItem.id == item_id)
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return {"success": False, "message": "条目不存在"}

        item.is_favorited = not item.is_favorited
        await self.db.commit()
        return {
            "success": True,
            "item_id": item_id,
            "is_favorited": item.is_favorited,
        }

    async def delete_item(self, item_id: str) -> dict[str, Any]:
        """删除单个条目。"""
        stmt = delete(TopicPoolItem).where(TopicPoolItem.id == item_id)
        result = await self.db.execute(stmt)
        await self.db.commit()
        return {"success": result.rowcount > 0, "item_id": item_id}

    async def get_detail(self, item_id: str) -> dict[str, Any] | None:
        """查询详情（含 content/raw 完整字段），并自增浏览次数。

        注意：不自动生成 AI 摘要（避免每次访问消耗 token）。
        AI 摘要由前端主动调用 generate_ai_summary 接口按需生成。
        """
        stmt = select(TopicPoolItem).where(TopicPoolItem.id == item_id)
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return None

        # 浏览次数 +1
        item.view_count = (item.view_count or 0) + 1
        await self.db.commit()

        return _to_dict(item, include_full=True)

    async def get_related(
        self,
        item_id: str,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        """关联内容推荐：同 source_keyword 优先，其次同 platform 补充。

        策略：
        1. 同 source_keyword 的条目（最相关，按热度降序）
        2. 不足 limit 时用同 platform 条目补充
        3. 排除当前条目，Python 层去重
        """
        cur_stmt = select(TopicPoolItem.source_keyword, TopicPoolItem.platform).where(
            TopicPoolItem.id == item_id
        )
        cur_result = await self.db.execute(cur_stmt)
        cur_row = cur_result.first()
        if not cur_row:
            return []
        keyword, platform = cur_row

        related: list[dict[str, Any]] = []
        seen_ids: set[str] = {item_id}

        # 1. 同 source_keyword
        if keyword:
            kw_stmt = (
                select(TopicPoolItem)
                .where(
                    TopicPoolItem.id != item_id,
                    TopicPoolItem.source_keyword == keyword,
                )
                .order_by(TopicPoolItem.heat_score.desc(), TopicPoolItem.created_at.desc())
                .limit(limit)
            )
            kw_result = await self.db.execute(kw_stmt)
            for row in kw_result.scalars().all():
                if row.id not in seen_ids:
                    related.append(_to_dict(row))
                    seen_ids.add(row.id)

        # 2. 同 platform 补充
        if len(related) < limit and platform:
            remaining = limit - len(related)
            plat_stmt = (
                select(TopicPoolItem)
                .where(
                    TopicPoolItem.id != item_id,
                    TopicPoolItem.platform == platform,
                )
                .order_by(TopicPoolItem.heat_score.desc(), TopicPoolItem.created_at.desc())
                .limit(remaining + 10)
            )
            plat_result = await self.db.execute(plat_stmt)
            for row in plat_result.scalars().all():
                if row.id not in seen_ids:
                    related.append(_to_dict(row))
                    seen_ids.add(row.id)
                    if len(related) >= limit:
                        break

        return related[:limit]

    async def generate_ai_summary(
        self,
        item_id: str,
        force: bool = False,
    ) -> dict[str, Any]:
        """调用 LLM 生成 AI 详细摘要 + 提取关键词标签。

        成本控制：使用 deepseek-chat（V3，最便宜），温度 0.3（摘要要稳定）。
        已有 ai_summary 且非 force 时直接返回缓存，不消耗 token。

        Args:
            item_id: 条目 ID
            force: True 时强制重新生成

        Returns:
            {success, ai_summary, tags, token_usage, cached, message}
        """
        import json
        import re
        from datetime import datetime, timezone

        stmt = select(TopicPoolItem).where(TopicPoolItem.id == item_id)
        result = await self.db.execute(stmt)
        item = result.scalar_one_or_none()
        if not item:
            return {"success": False, "message": "条目不存在"}

        # 缓存命中：已有 AI 摘要且非强制刷新
        if item.ai_summary and not force:
            return {
                "success": True,
                "ai_summary": item.ai_summary,
                "tags": item.tags or [],
                "cached": True,
                "token_usage": 0,
                "message": "AI 摘要已存在（使用缓存，未消耗 token）",
            }

        # 获取 LLM 实例（延迟 import 避免循环依赖）
        from app.engine.factory import get_deepseek_llm

        llm = get_deepseek_llm(temperature=0.3)
        if llm is None:
            return {"success": False, "message": "LLM 不可用（未配置 deepseek_api_key）"}

        # 构造输入：优先 content，其次 summary
        source_text = (item.content or "").strip()
        if not source_text:
            source_text = (item.summary or "").strip()
        if not source_text:
            return {
                "success": False,
                "message": "条目无内容可生成摘要（content 和 summary 均为空）",
            }

        # 截断超长内容（控制 token 消耗，约 4000 字符 ≈ 2000 token）
        if len(source_text) > 4000:
            source_text = source_text[:4000] + "\n...(内容已截断)"

        prompt = (
            "你是一个内容分析助手。请基于以下内容生成深度摘要和关键词标签。\n\n"
            f"标题：{item.title}\n"
            f"平台：{item.platform}\n"
            f"来源关键词：{item.source_keyword or '无'}\n"
            f"内容：\n{source_text}\n\n"
            "要求：\n"
            "1. ai_summary：200-400 字深度摘要，提炼核心观点、关键信息和亮点，不要简单复述原文\n"
            "2. tags：5-8 个关键词标签（不含#号），覆盖主题、领域、情绪、受众等维度\n\n"
            "返回 JSON（不要 markdown 代码块）：\n"
            '{"ai_summary": "...", "tags": ["关键词1", "关键词2"]}'
        )

        messages = [{"role": "user", "content": prompt}]

        try:
            resp = await llm.chat(
                messages,
                response_format={"type": "json_object"},
            )
        except Exception as e:
            logger.error(f"generate_ai_summary: LLM 调用失败: {e}")
            return {"success": False, "message": f"LLM 调用失败: {e}"}

        content = (resp.get("content") or "").strip()
        if not content:
            return {"success": False, "message": "LLM 返回空内容"}

        # 解析 JSON
        parsed: dict[str, Any] | None = None
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # 兜底：提取首个含 ai_summary 的 JSON 片段
            match = re.search(r"\{[^{}]*\"ai_summary\"[^{}]*\}", content, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass

        if not parsed:
            return {
                "success": False,
                "message": "LLM 返回内容无法解析为 JSON",
                "raw": content[:500],
            }

        ai_summary = (parsed.get("ai_summary") or "").strip()
        tags_raw = parsed.get("tags") or []
        if not isinstance(tags_raw, list):
            tags_raw = []
        tags = [str(t).strip() for t in tags_raw if str(t).strip()][:10]

        if not ai_summary:
            return {"success": False, "message": "LLM 未生成有效摘要"}

        # 持久化
        item.ai_summary = ai_summary
        item.tags = tags if tags else None
        item.ai_summary_generated_at = datetime.now(timezone.utc)
        await self.db.commit()

        token_usage = resp.get("token_usage", 0)
        logger.info(
            f"generate_ai_summary: item_id={item_id}, tokens={token_usage}, "
            f"summary_len={len(ai_summary)}, tags_count={len(tags)}"
        )

        return {
            "success": True,
            "ai_summary": ai_summary,
            "tags": tags,
            "token_usage": token_usage,
            "cached": False,
            "message": "AI 摘要生成成功",
        }

    async def get_stats(self) -> dict[str, Any]:
        """统计：总数 + 收藏数 + 各平台数量 + monitor 条数 + 平均热度分 + 情绪分布。

        优化：将 5 次独立查询合并为 3 次（聚合统计 + 平台分布 + 情绪分布）。
        使用 CASE WHEN 条件聚合替代 PostgreSQL 专有的 FILTER 语法，兼容 MySQL/SQLite。
        """
        agg_stmt = select(
            func.count().label("total"),
            func.sum(case((TopicPoolItem.is_favorited.is_(True), 1), else_=0)).label("favorited"),
            func.sum(case((TopicPoolItem.auto_source == "monitor", 1), else_=0)).label("monitor_count"),
            func.avg(
                case(
                    (TopicPoolItem.auto_source == "monitor", TopicPoolItem.heat_score),
                    else_=None,
                )
            ).label("avg_heat"),
        )
        agg_result = await self.db.execute(agg_stmt)
        agg_row = agg_result.one()
        total = agg_row.total
        favorited = int(agg_row.favorited or 0)
        monitor_count = int(agg_row.monitor_count or 0)
        avg_heat = float(agg_row.avg_heat or 0)

        # 各平台数量
        plat_stmt = (
            select(TopicPoolItem.platform, func.count())
            .group_by(TopicPoolItem.platform)
        )
        plat_result = await self.db.execute(plat_stmt)
        platforms = {row[0]: row[1] for row in plat_result}

        # 情绪分布（监控数据）
        emo_result = await self.db.execute(
            select(TopicPoolItem.dimensions).where(
                TopicPoolItem.auto_source == "monitor",
                TopicPoolItem.dimensions.is_not(None),
            )
        )
        emotions: dict[str, int] = {}
        for (dims,) in emo_result:
            if isinstance(dims, dict):
                emo = dims.get("emotion")
                if emo:
                    emotions[emo] = emotions.get(emo, 0) + 1

        return {
            "total": total,
            "favorited": favorited,
            "monitor_count": monitor_count,
            "avg_heat_score": round(avg_heat, 2),
            "platforms": platforms,
            "emotions": emotions,
        }

    async def fetch_and_save(
        self,
        keyword: str,
        platform: str,
        limit: int = 10,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """主动抓取指定平台内容存入选题池（auto_source=manual）。

        复用 TrendingSearchSkill 抓取，按 (platform, content_id) 去重后落库。
        支持所有平台（包括 xiaohongshu，需桥接页面在线）。

        Args:
            keyword: 搜索关键词
            platform: 目标平台（hackernews/reddit/tavily/xiaohongshu 等）
            limit: 抓取条数（默认 10）

        Returns:
            {saved_count, skipped_duplicate, fetched_count, platform, items}
        """
        from app.tools.trending_search import TrendingSearchSkill

        skill = TrendingSearchSkill()
        try:
            result = await skill.execute({
                "keyword": keyword,
                "limit": limit,
                "platform": platform,
                "disable_fallback": True,
                "min_interactions": 0,
            })
        except Exception as e:
            logger.warning(f"fetch_and_save: search failed for {platform}: {e}")
            return {
                "saved_count": 0,
                "skipped_duplicate": 0,
                "fetched_count": 0,
                "platform": platform,
                "items": [],
                "error": str(e),
            }

        items = result.get("results", []) or []
        if not items:
            diag_error = ""
            if platform == "xiaohongshu":
                try:
                    from app.api.routers.mcp_bridge import bridge_state
                    sub_count = len(bridge_state._subscribers)
                    if sub_count == 0:
                        diag_error = "桥接页面未在线（SSE无订阅）。请打开桥接页面并保持标签页在前台"
                    else:
                        diag_error = f"桥接SSE订阅数={sub_count}，但扩展60s内未响应。请确认：1)扩展已重新加载 2)浏览器已登录小红书 3)桥接页面在前台标签页"
                except Exception as diag_e:
                    diag_error = f"桥接诊断失败: {diag_e}"
            return {
                "saved_count": 0,
                "skipped_duplicate": 0,
                "fetched_count": 0,
                "platform": platform,
                "items": [],
                "error": diag_error or None,
            }

        saved_items: list[dict] = []
        saved_count = 0
        skipped_duplicate = 0
        seen_titles: set[str] = set()

        cleaned: list[dict] = []
        for item in items:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            cleaned.append({
                "content_id": str(item.get("content_id") or ""),
                "title": title[:500],
                "summary": (item.get("summary") or "")[:2000],
                "content": item.get("content") or "",
                "url": item.get("url") or "",
                "author": item.get("author") or "",
                "likes": int(item.get("likes") or 0),
                "comments": int(item.get("comments") or 0),
                "collects": int(item.get("collects") or 0),
                "shares": int(item.get("shares") or 0),
                "fans_count": int(item.get("fans_count") or 0),
                "cover_img": item.get("cover_img") or "",
                "images": item.get("images") or None,
                "raw": item.get("raw") or None,
            })

        if not cleaned:
            return {
                "saved_count": 0,
                "skipped_duplicate": 0,
                "fetched_count": len(items),
                "platform": platform,
                "items": [],
            }

        # 批量去重
        content_ids = [it["content_id"] for it in cleaned if it["content_id"]]
        titles = [it["title"] for it in cleaned]

        existing_cids: set[str] = set()
        existing_titles: set[str] = set()

        if content_ids:
            rs = await self.db.execute(
                select(TopicPoolItem.content_id).where(
                    TopicPoolItem.platform == platform,
                    TopicPoolItem.content_id.in_(content_ids),
                )
            )
            existing_cids = {r[0] for r in rs if r[0]}

        if titles:
            rs = await self.db.execute(
                select(TopicPoolItem.title).where(
                    TopicPoolItem.platform == platform,
                    TopicPoolItem.title.in_(titles),
                )
            )
            existing_titles = {r[0] for r in rs if r[0]}

        for item in cleaned:
            if item["title"] in seen_titles:
                skipped_duplicate += 1
                continue
            if item["content_id"] and item["content_id"] in existing_cids:
                skipped_duplicate += 1
                seen_titles.add(item["title"])
                continue
            if item["title"] in existing_titles:
                skipped_duplicate += 1
                seen_titles.add(item["title"])
                continue

            seen_titles.add(item["title"])

            local_cover = item["cover_img"]
            local_images = item["images"]
            try:
                from app.services.image_store import cache_cover_image, cache_detail_images
                if local_cover:
                    local_cover = await cache_cover_image(
                        item["content_id"] or "", local_cover
                    )
                if local_images:
                    local_images = await cache_detail_images(
                        item["content_id"] or "", local_images
                    )
            except Exception as img_err:
                logger.warning(f"fetch_and_save 图片下载失败: {img_err}")

            pool_item = TopicPoolItem(
                platform=platform,
                content_id=item["content_id"] or None,
                title=item["title"],
                summary=item["summary"],
                content=item["content"],
                url=item["url"],
                author=item["author"],
                likes=item["likes"],
                comments=item["comments"],
                collects=item["collects"],
                shares=item["shares"],
                fans_count=item["fans_count"],
                cover_img=local_cover,
                images=local_images,
                source_keyword=keyword[:500],
                auto_source="manual",
            )
            self.db.add(pool_item)
            saved_count += 1
            saved_items.append(_to_dict(pool_item))

        if saved_count > 0:
            await self.db.commit()
            if user_id is not None:
                from app.services import agent_memory
                weight = saved_count if saved_count <= 10 else 10
                await agent_memory.record_search_keyword(user_id, keyword, weight=weight)

        logger.info(
            f"fetch_and_save: platform={platform}, keyword={keyword!r}, "
            f"fetched={len(items)}, saved_new={saved_count}, skipped_dup={skipped_duplicate}"
        )

        return {
            "saved_count": saved_count,
            "skipped_duplicate": skipped_duplicate,
            "fetched_count": len(items),
            "platform": platform,
            "items": saved_items,
        }


def _to_dict(item: TopicPoolItem, include_full: bool = False) -> dict[str, Any]:
    """ORM 转 dict（默认不含 content/raw，减少列表传输量；含监控+详情页字段）。

    Args:
        item: ORM 实例
        include_full: True 时包含 content 和 raw 字段（详情页用）
    """
    data: dict[str, Any] = {
        "id": item.id,
        "platform": item.platform,
        "content_id": item.content_id,
        "title": item.title,
        "summary": item.summary,
        "url": item.url,
        "author": item.author,
        "likes": item.likes,
        "comments": item.comments,
        "collects": item.collects,
        "shares": item.shares,
        "fans_count": item.fans_count,
        "cover_img": item.cover_img,
        "images": item.images or [],
        "source_keyword": item.source_keyword,
        "is_favorited": item.is_favorited,
        # 监控字段
        "auto_source": item.auto_source,
        "heat_score": float(item.heat_score or 0),
        "heat_status": item.heat_status,
        "dimensions": item.dimensions,
        "published_at": item.published_at.isoformat() if item.published_at else "",
        "created_at": item.created_at.isoformat() if item.created_at else "",
        # 详情页字段（v7）
        "tags": item.tags or [],
        "ai_summary": item.ai_summary,
        "view_count": item.view_count,
        "ai_summary_generated_at": item.ai_summary_generated_at.isoformat()
        if item.ai_summary_generated_at
        else "",
    }
    if include_full:
        data["content"] = item.content
        data["raw"] = item.raw
    return data