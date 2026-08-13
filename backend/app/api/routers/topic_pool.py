"""选题池 API 路由（v6 合并：手动抓取 + 监控数据统一入口）。

GET    /api/topic-pool              列表（支持平台/关键词/收藏/来源/热度排序/维度筛选）
GET    /api/topic-pool/stats         统计（总数/收藏/各平台/各情绪/平均热度分）
POST   /api/topic-pool/fetch         主动抓取指定平台内容存入选题池
POST   /api/topic-pool/monitor/fetch 手动触发一次监控抓取（MonitorAgent）
POST   /api/topic-pool/{id}/favorite 切换收藏
DELETE /api/topic-pool/{id}          删除条目
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.db.session import get_db
from app.services.topic_pool import TopicPoolService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/topic-pool", tags=["topic-pool"])


@router.get("")
async def list_items(
    platform: str | None = Query(None, description="平台筛选：hackernews/reddit/tavily/xiaohongshu/小红书/抖音/微博"),
    keyword: str | None = Query(None, description="标题/摘要模糊搜索"),
    favorited_only: bool = Query(False, description="仅看收藏"),
    auto_source: str | None = Query(None, description="来源筛选：manual/monitor"),
    emotion: str | None = Query(None, description="情绪维度筛选"),
    scene: str | None = Query(None, description="场景维度筛选"),
    visual: str | None = Query(None, description="视觉形式筛选"),
    sort: str = Query("created_desc", description="排序：created_desc/heat_desc"),
    page: int = Query(1, ge=1, description="页码（1-based）"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict[str, Any]]:
    """分页查询选题池条目（手动抓取 + 监控数据统一查询）。"""
    service = TopicPoolService(db)
    data = await service.list_items(
        platform=platform,
        keyword=keyword,
        favorited_only=favorited_only,
        auto_source=auto_source,
        emotion=emotion,
        scene=scene,
        visual=visual,
        sort=sort,
        page=page,
        size=size,
    )
    return StandardResponse(data=data)


@router.get("/stats")
async def get_stats(
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict[str, Any]]:
    """统计：总数 + 收藏数 + 各平台数量 + 各情绪数量 + 平均热度分 + monitor 条数。"""
    service = TopicPoolService(db)
    data = await service.get_stats()
    return StandardResponse(data=data)



@router.get("/recommended")
async def get_recommended(
    limit: int = Query(10, ge=1, le=30, description="返回条数"),
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """基于用户经常搜索的关键词返回推荐热点。

    1. 从 agent_memory 获取用户最常搜索的 5 个关键词
    2. 对每个关键词查询选题池中热度最高的内容
    3. 合并去重后按热度排序返回
    4. 无搜索历史时回退到全局热门内容
    """
    from app.services import agent_memory

    service = TopicPoolService(db)
    seen_ids: set[str] = set()
    combined: list[dict] = []

    keywords: list[str] = []
    try:
        keywords = await agent_memory.get_search_keywords(user_id, limit=5)
    except Exception as e:
        logger.warning(f"[topic-pool] get_search_keywords failed: {e}")

    if keywords:
        per_kw = max(limit // len(keywords), 2)
        for kw in keywords:
            try:
                data = await service.list_items(
                    keyword=kw, sort="heat_desc", page=1, size=per_kw,
                )
                for item in data.get("items", []):
                    item_id = item.get("id", "")
                    if item_id and item_id not in seen_ids:
                        item["_matched_keyword"] = kw
                        combined.append(item)
                        seen_ids.add(item_id)
            except Exception as e:
                logger.warning(f"[topic-pool] recommended query for {kw!r} failed: {e}")

    if len(combined) < limit:
        try:
            data = await service.list_items(
                sort="heat_desc", page=1, size=limit,
            )
            for item in data.get("items", []):
                item_id = item.get("id", "")
                if item_id and item_id not in seen_ids:
                    combined.append(item)
                    seen_ids.add(item_id)
                    if len(combined) >= limit:
                        break
        except Exception as e:
            logger.warning(f"[topic-pool] recommended fallback failed: {e}")

    combined = combined[:limit]
    return StandardResponse(data={
        "items": combined,
        "total": len(combined),
        "keywords": keywords,
    })


class FetchRequest(BaseModel):
    """主动抓取请求（手动模式）。"""
    keyword: str = Field(..., description="搜索关键词")
    platform: str = Field(..., description="目标平台：hackernews/reddit/tavily/xiaohongshu")
    limit: int = Field(100, ge=1, le=100, description="抓取条数（最多100）")


@router.post("/fetch")
async def fetch_to_pool(
    request: FetchRequest,
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """主动抓取指定平台内容存入选题池（auto_source=manual）。

    支持所有平台：
    - hackernews/reddit/tavily：直接 HTTP 请求，速度快
    - xiaohongshu：通过浏览器扩展抓取，需桥接页面在线，受频率限制（30s间隔/每日30次）

    按 (platform, content_id) 去重，重复内容自动跳过。
    """
    keyword = request.keyword.strip()
    if not keyword:
        raise HTTPException(status_code=400, detail="关键词不能为空")

    service = TopicPoolService(db)
    data = await service.fetch_and_save(
        keyword=keyword,
        platform=request.platform,
        limit=request.limit,
        user_id=user_id,
    )

    return StandardResponse(data=data)


@router.post("/monitor/fetch")
async def monitor_fetch(
    db: AsyncSession = Depends(get_db),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict[str, Any]]:
    """手动触发一次监控抓取（MonitorAgent，auto_source=monitor）。

    用于测试定时任务效果：抓取 → SimHash 去重 → LLM 分类 → 评分 → 入池。
    """
    from app.pool_monitor.monitor_agent import MonitorAgent

    agent = MonitorAgent()
    result = await agent.run(db, user_id=user_id)
    return StandardResponse(data={"success": True, "result": result})


@router.get("/{item_id}")
async def get_detail(
    item_id: str,
    related_limit: int = Query(8, ge=0, le=20, description="关联推荐条数（0=不返回关联）"),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict[str, Any]]:
    """获取选题池条目详情（含完整 content/raw 字段）+ 关联内容推荐。

    每次访问自增 view_count。
    AI 摘要不会自动生成（需主动调用 POST /{item_id}/ai-summary）。
    """
    service = TopicPoolService(db)
    detail = await service.get_detail(item_id)
    if not detail:
        raise HTTPException(status_code=404, detail="条目不存在")

    related: list[dict] = []
    if related_limit > 0:
        related = await service.get_related(item_id, limit=related_limit)

    return StandardResponse(data={
        "detail": detail,
        "related": related,
    })


@router.post("/{item_id}/ai-summary")
async def generate_ai_summary(
    item_id: str,
    force: bool = Query(False, description="True=强制重新生成（消耗token），False=有缓存则用缓存"),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict[str, Any]]:
    """调用 LLM 生成 AI 详细摘要 + 提取关键词标签。

    成本控制：
    - 使用 deepseek-chat（V3，最便宜的模型）
    - 已有 ai_summary 且 force=False 时返回缓存，不消耗 token
    - force=True 时强制重新生成

    返回：{success, ai_summary, tags, token_usage, cached, message}
    """
    service = TopicPoolService(db)
    data = await service.generate_ai_summary(item_id, force=force)
    if not data.get("success"):
        raise HTTPException(status_code=400, detail=data.get("message", "AI 摘要生成失败"))
    return StandardResponse(data=data)


@router.post("/{item_id}/favorite")
async def toggle_favorite(
    item_id: str,
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict[str, Any]]:
    """切换收藏状态。"""
    service = TopicPoolService(db)
    data = await service.toggle_favorite(item_id)
    if not data.get("success"):
        raise HTTPException(status_code=404, detail=data.get("message", "条目不存在"))
    return StandardResponse(data=data)


@router.delete("/{item_id}")
async def delete_item(
    item_id: str,
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict[str, Any]]:
    """删除单个条目。"""
    service = TopicPoolService(db)
    data = await service.delete_item(item_id)
    if not data.get("success"):
        raise HTTPException(status_code=404, detail="条目不存在")
    return StandardResponse(data=data)
