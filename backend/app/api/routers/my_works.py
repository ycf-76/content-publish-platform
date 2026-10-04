"""我的作品 API。

提供端点：
- GET  /api/my-works：我的作品列表（分页+排序）
- GET  /api/my-works/{id}：单条作品详情+指标趋势
- GET  /api/my-works/attribution：我的归因分析结果（写作处方）
- POST /api/my-works/collect：粘贴链接采集数据入库
- POST /api/my-works/csv-import：CSV 批量导入（创作者中心数据）
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, func

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.db.models import PublishedContentPerformance
from app.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/my-works", tags=["my-works"])


def _public_images(images: Any) -> list[Any]:
    """Keep presentation-safe image/video entries, never expose local paths."""
    if not isinstance(images, list):
        return []
    cleaned: list[Any] = []
    for item in images:
        if isinstance(item, dict):
            cleaned.append({k: v for k, v in item.items() if k != "local_path"})
        else:
            cleaned.append(item)
    return cleaned


class CollectRequest(BaseModel):
    note_url: str = Field(description="内容链接（支持小红书/抖音/B站/微信/Instagram）")
    platform: str = Field(default="auto", description="平台标识：auto=自动检测 / xiaohongshu / douyin / bilibili / wechat_mp / instagram / threads")


class CsvImportRequest(BaseModel):
    platform: str = Field(default="xiaohongshu", description="平台标识")
    records: list[dict] = Field(description="CSV 导入的记录列表")


@router.get("")
async def list_my_works(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
    platform: str | None = Query(default=None, description="按平台筛选"),
    sort_by: str = Query(default="published_at", description="排序字段"),
    content_status: str | None = Query(default=None, description="按状态筛选：draft/published/collected"),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """我的作品列表（分页+排序+状态筛选）。"""
    async with AsyncSessionLocal() as db:
        stmt = select(PublishedContentPerformance).where(
            PublishedContentPerformance.user_id == user_id
        )
        if platform:
            stmt = stmt.where(PublishedContentPerformance.platform == platform)
        if content_status:
            statuses = [s.strip() for s in content_status.split(',') if s.strip()]
            if len(statuses) == 1:
                stmt = stmt.where(PublishedContentPerformance.content_status == statuses[0])
            elif len(statuses) > 1:
                stmt = stmt.where(PublishedContentPerformance.content_status.in_(statuses))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = await db.scalar(count_stmt) or 0

        if sort_by == "performance_score":
            stmt = stmt.order_by(desc(PublishedContentPerformance.performance_score))
        else:
            stmt = stmt.order_by(desc(PublishedContentPerformance.published_at))

        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        result = await db.scalars(stmt)
        records = list(result.all())

        items = []
        for r in records:
            items.append({
                "id": r.id,
                "workflow_id": r.workflow_id,
                "published_note_id": r.published_note_id,
                "topic": r.topic,
                "title": r.title,
                "content_text": r.content_text,
                "tags": r.tags,
                "cover_img_url": r.cover_img_url,
                "images": _public_images(r.images),
                "video_url": r.video_url,
                "platform": r.platform,
                "published_at": r.published_at.isoformat() if r.published_at else None,
                "collected_likes": r.collected_likes,
                "collected_collects": r.collected_collects,
                "collected_comments": r.collected_comments,
                "collected_shares": r.collected_shares,
                "performance_score": r.performance_score,
                "is_replicated": r.is_replicated,
                "predicted_viral_score": r.predicted_viral_score,
                "actual_viral_score": r.actual_viral_score,
                "prediction_error": r.prediction_error,
                "collected_at": r.collected_at.isoformat() if r.collected_at else None,
                "content_status": (
                    "collected" if r.collected_at and (r.collected_likes or r.collected_collects or r.collected_comments)
                    else r.content_status
                ),
                "title_pattern": r.title_pattern,
                "emotion_trigger": r.emotion_trigger,
                "content_structure": r.content_structure,
                "card_draft": getattr(r, "card_draft", None),
                "first_page_html": getattr(r, "first_page_html", None),
            })

        return StandardResponse(data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        })


@router.delete("/{record_id}")
async def delete_my_work(
    record_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """删除一条作品记录。"""
    async with AsyncSessionLocal() as db:
        stmt = select(PublishedContentPerformance).where(
            PublishedContentPerformance.id == record_id,
            PublishedContentPerformance.user_id == user_id,
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")
        await db.delete(record)
        await db.commit()
        return StandardResponse(data={"deleted": True, "id": record_id})


@router.get("/analysis-report")
async def get_analysis_report(
    platform: str | None = Query(None, description="按平台筛选分析"),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """AI 数据分析报告：跨平台洞察 + 写作处方 + 预测校准 + 行动建议。

    核心输出不是数据，是洞察和行动建议。
    """
    from app.services.self_attribution import SelfAttributionEngine, get_attribution_weight
    from app.services.agent_memory import load_for_workflow
    from app.services.performance_collector import compute_performance_score

    engine = SelfAttributionEngine()

    async with AsyncSessionLocal() as db:
        base_where = [
            PublishedContentPerformance.user_id == user_id,
            PublishedContentPerformance.collected_at.isnot(None),
        ]
        if platform:
            base_where.append(PublishedContentPerformance.platform == platform)

        all_stmt = select(PublishedContentPerformance).where(*base_where).order_by(desc(PublishedContentPerformance.performance_score))
        all_result = await db.scalars(all_stmt)
        all_works = list(all_result.all())

        total_count = len(all_works)

        if total_count == 0:
            return StandardResponse(data={
                "status": "no_data",
                "message": "暂无采集数据，请先通过链接采集或 CSV 导入",
                "actions": ["采集链接入库", "CSV 批量导入"],
            })

        high_works = [w for w in all_works if (w.performance_score or 0) >= 0.3]
        low_works = [w for w in all_works if (w.performance_score or 0) < 0.3]
        replicated_works = [w for w in all_works if w.is_replicated]

        all_scores = [w.performance_score for w in all_works if w.performance_score is not None]
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        median_score = sorted(all_scores)[len(all_scores) // 2] if all_scores else 0

        predicted_works = [w for w in all_works if w.predicted_viral_score is not None and w.actual_viral_score is not None]
        prediction_errors = [w.prediction_error for w in predicted_works if w.prediction_error is not None]
        avg_prediction_error = sum(prediction_errors) / len(prediction_errors) if prediction_errors else None
        overestimate_count = sum(1 for e in prediction_errors if e < -0.1)
        underestimate_count = sum(1 for e in prediction_errors if e > 0.1)
        accurate_count = len(prediction_errors) - overestimate_count - underestimate_count

        platform_stats: dict[str, dict] = {}
        for w in all_works:
            p = w.platform or "unknown"
            if p not in platform_stats:
                platform_stats[p] = {"count": 0, "total_score": 0.0, "replicated": 0, "likes": 0, "collects": 0}
            platform_stats[p]["count"] += 1
            platform_stats[p]["total_score"] += (w.performance_score or 0)
            if w.is_replicated:
                platform_stats[p]["replicated"] += 1
            platform_stats[p]["likes"] += (w.collected_likes or 0)
            platform_stats[p]["collects"] += (w.collected_collects or 0)

        platform_summary = []
        for p, s in platform_stats.items():
            platform_summary.append({
                "platform": p,
                "count": s["count"],
                "avg_score": round(s["total_score"] / s["count"], 4) if s["count"] else 0,
                "replicated_rate": round(s["replicated"] / s["count"], 3) if s["count"] else 0,
                "total_likes": s["likes"],
                "total_collects": s["collects"],
            })

        title_patterns: dict[str, list[float]] = {}
        emotion_triggers: dict[str, list[float]] = {}
        content_structures: dict[str, list[float]] = {}
        for w in all_works:
            score = w.performance_score or 0
            if w.title_pattern:
                title_patterns.setdefault(w.title_pattern, []).append(score)
            if w.emotion_trigger:
                emotion_triggers.setdefault(w.emotion_trigger, []).append(score)
            if w.content_structure:
                content_structures.setdefault(w.content_structure, []).append(score)

        def rank_dict(d: dict[str, list[float]]) -> list[dict]:
            items = [{"name": k, "avg_score": round(sum(v) / len(v), 4), "count": len(v)} for k, v in d.items() if v]
            return sorted(items, key=lambda x: x["avg_score"], reverse=True)

        pattern_ranking = rank_dict(title_patterns)
        emotion_ranking = rank_dict(emotion_triggers)
        structure_ranking = rank_dict(content_structures)

    memory = await load_for_workflow(user_id)
    my_attribution = memory.get("my_attribution", {})
    avoid_patterns = memory.get("avoid_patterns", [])
    my_weight = get_attribution_weight(total_count)

    top_works = all_works[:10]

    total_likes = sum(w.collected_likes or 0 for w in all_works)
    total_collects = sum(w.collected_collects or 0 for w in all_works)
    total_comments = sum(w.collected_comments or 0 for w in all_works)

    actions: list[dict] = []
    if total_count < 10:
        actions.append({"priority": "high", "action": "继续采集数据", "reason": f"当前 {total_count} 篇，需要 10+ 篇才能生成可靠分析"})
    if pattern_ranking:
        best = pattern_ranking[0]
        actions.append({"priority": "medium", "action": f"多用「{best['name']}」标题模式", "reason": f"{best['count']} 篇验证，平均表现最好"})
    if emotion_ranking:
        best_e = emotion_ranking[0]
        actions.append({"priority": "medium", "action": f"多用「{best_e['name']}」情绪钩子", "reason": f"{best_e['count']} 篇验证"})
    if avoid_patterns:
        items = avoid_patterns if isinstance(avoid_patterns, list) else avoid_patterns.get("items", [])
        if items:
            actions.append({"priority": "medium", "action": "避开低效模式", "reason": f"已有 {len(items)} 条避坑规则"})
    if len(low_works) > len(high_works) and total_count >= 5:
        actions.append({"priority": "medium", "action": "复盘低表现内容", "reason": f"{len(low_works)} 篇低表现 vs {len(high_works)} 篇高表现，找出差异"})

    confidence = "low" if total_count < 10 else ("medium" if total_count < 30 else "high")

    return StandardResponse(data={
        "status": "ok",
        "confidence": confidence,
        "sample_size": total_count,
        "my_weight": round(my_weight, 3),
        "overview": {
            "total": total_count,
            "high_performers": len(high_works),
            "low_performers": len(low_works),
            "replicated": len(replicated_works),
            "total_likes": total_likes,
            "total_collects": total_collects,
            "total_comments": total_comments,
            "avg_score": round(avg_score, 4),
        },
        "platform_comparison": platform_summary,
        "pattern_ranking": pattern_ranking[:8],
        "emotion_ranking": emotion_ranking[:6],
        "structure_ranking": structure_ranking[:6],
        "top_performers": [
            {
                "id": w.id,
                "title": w.title,
                "platform": w.platform,
                "score": round(w.performance_score or 0, 4),
                "likes": w.collected_likes,
                "collects": w.collected_collects,
                "comments": w.collected_comments,
                "cover_img_url": w.cover_img_url,
            }
            for w in top_works
        ],
        "writing_prescription": my_attribution,
        "avoid_patterns": avoid_patterns,
        "action_items": actions,
    })


@router.post("/trigger-attribution")
async def trigger_attribution(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """手动触发归因分析，生成/更新写作处方。"""
    from app.services.self_attribution import SelfAttributionEngine
    engine = SelfAttributionEngine()
    result = await engine.generate_writing_prescription(user_id)
    if result is None:
        return StandardResponse(success=False, data={}, message="数据不足（需要至少 5 篇已采集数据）")
    return StandardResponse(data=result, message="归因分析完成，写作处方已更新")


@router.get("/attribution")
async def get_attribution(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """我的归因分析结果（写作处方）。"""
    from app.services.agent_memory import load_for_workflow
    memory = await load_for_workflow(user_id)
    return StandardResponse(data={
        "my_attribution": memory.get("my_attribution", {}),
        "avoid_patterns": memory.get("avoid_patterns", []),
    })


@router.get("/{record_id}")
async def get_my_work_detail(
    record_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """单条作品详情。"""
    async with AsyncSessionLocal() as db:
        stmt = select(PublishedContentPerformance).where(
            PublishedContentPerformance.id == record_id,
            PublishedContentPerformance.user_id == user_id,
        )
        record = await db.scalar(stmt)
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")

        return StandardResponse(data={
            "id": record.id,
            "workflow_id": record.workflow_id,
            "published_note_id": record.published_note_id,
            "topic": record.topic,
            "title": record.title,
            "content_text": record.content_text,
            "tags": record.tags,
            "cover_img_url": record.cover_img_url,
            "images": _public_images(record.images),
            "video_url": record.video_url,
            "platform": record.platform,
            "published_at": record.published_at.isoformat() if record.published_at else None,
            "collected_likes": record.collected_likes,
            "collected_collects": record.collected_collects,
            "collected_comments": record.collected_comments,
            "collected_shares": record.collected_shares,
            "performance_score": record.performance_score,
            "is_replicated": record.is_replicated,
            "predicted_viral_score": record.predicted_viral_score,
            "actual_viral_score": record.actual_viral_score,
            "prediction_error": record.prediction_error,
            "title_pattern": record.title_pattern,
            "emotion_trigger": record.emotion_trigger,
            "content_structure": record.content_structure,
            "images": record.images,
            "selected_pattern": record.selected_pattern,
            "selected_direction": record.selected_direction,
            "collected_at": record.collected_at.isoformat() if record.collected_at else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        })


@router.post("/collect")
async def collect_note_data(
    payload: CollectRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """粘贴链接采集数据入库。

    降级链：SSR 解析（需 xsec_token）→ link-grabber → Web API → MCP
    提示：从手机 App 分享的链接自带 xsec_token，可直接解析。
    """
    from app.services.work_collector import collect_from_url, detect_platform, get_last_collect_errors, _clean_share_text
    from app.services.performance_collector import compute_performance_score

    cleaned_url = _clean_share_text(payload.note_url)
    platform = payload.platform
    if not platform or platform == "auto":
        platform = detect_platform(cleaned_url)

    result = await collect_from_url(payload.note_url, platform)

    if not result:
        errors = get_last_collect_errors()
        detail_msg = "；".join(errors) if errors else "所有采集方式均失败"
        # 针对抖音短链接给出特殊提示
        douyin_hint = ""
        if platform == "douyin" and "v.douyin.com" in payload.note_url:
            douyin_hint = "；抖音短链接(v.douyin.com)暂不支持服务端解析，请粘贴长链接格式（如 douyin.com/video/7xxxxx）"
        return StandardResponse(
            success=False,
            data={"note_url": payload.note_url, "errors": errors},
            message=f"采集失败（{detail_msg}）{douyin_hint}。建议：1) 从手机App分享链接（自带访问令牌，成功率最高）；2) 抖音请使用长链接格式；3) 确保浏览器扩展已连接且已登录",
        )

    # 入库
    async with AsyncSessionLocal() as db:
        from datetime import UTC, datetime

        score = compute_performance_score({
            "likes": result.get("likes", 0),
            "collects": result.get("collects", 0),
            "comments": result.get("comments", 0),
            "shares": result.get("shares", 0),
            "author_fans": result.get("author_fans", 1),
        })

        from app.services.image_store import cache_cover_image, cache_detail_images

        record_id_for_cache = result.get("note_id", "") or str(int(datetime.now(UTC).timestamp()))
        cover_img_url = result.get("cover_img_url", "")
        image_urls = result.get("image_urls", [])

        try:
            cover_img_url = await cache_cover_image(record_id_for_cache, cover_img_url)
        except Exception as e:
            logger.warning(f"cache_cover_image failed: {e}")

        try:
            image_urls = await cache_detail_images(record_id_for_cache, image_urls) or image_urls
        except Exception as e:
            logger.warning(f"cache_detail_images failed: {e}")

        record = PublishedContentPerformance(
            user_id=user_id,
            workflow_id="",
            published_note_id=result.get("note_id", ""),
            title=(result.get("title", "") or "")[:512],
            content_text=result.get("content_text"),
            tags=result.get("tags"),
            cover_img_url=cover_img_url,
            images=image_urls,
            platform=platform,
            collected_likes=result.get("likes", 0),
            collected_collects=result.get("collects", 0),
            collected_comments=result.get("comments", 0),
            collected_shares=result.get("shares", 0),
            performance_score=score,
            collected_at=datetime.now(UTC),
            published_at=datetime.now(UTC),
            content_status="collected",
        )
        db.add(record)
        await db.commit()
        await db.refresh(record)

    return StandardResponse(
        data={
            "id": record.id,
            "note_id": result.get("note_id", ""),
            "title": result.get("title", ""),
            "cover_img_url": result.get("cover_img_url", ""),
            "tags": result.get("tags", []),
            "likes": result.get("likes", 0),
            "collects": result.get("collects", 0),
            "comments": result.get("comments", 0),
            "shares": result.get("shares", 0),
            "author_nickname": result.get("author_nickname", ""),
            "note_type": result.get("note_type", ""),
            "platform": platform,
            "performance_score": score,
            "source": result.get("source", "unknown"),
        },
        message=f"采集成功（来源：{result.get('source', 'unknown')}）",
    )


@router.post("/csv-import")
async def csv_import(
    payload: CsvImportRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """CSV 批量导入（创作者中心数据）。"""
    from datetime import UTC, datetime

    imported = 0
    errors = 0

    async with AsyncSessionLocal() as db:
        for row in payload.records:
            try:
                record = PublishedContentPerformance(
                    user_id=user_id,
                    workflow_id=row.get("workflow_id", ""),
                    published_note_id=row.get("note_id"),
                    topic=row.get("topic"),
                    title=row.get("title", "")[:512] if row.get("title") else None,
                    platform=payload.platform,
                    published_at=(
                        datetime.fromisoformat(row["published_at"])
                        if row.get("published_at") else datetime.now(UTC)
                    ),
                    collected_likes=int(row.get("likes", 0) or 0),
                    collected_collects=int(row.get("collects", 0) or 0),
                    collected_comments=int(row.get("comments", 0) or 0),
                    collected_shares=int(row.get("shares", 0) or 0),
                    collected_at=datetime.now(UTC),
                    content_status="collected",
                )
                from app.services.performance_collector import compute_performance_score
                record.performance_score = compute_performance_score({
                    "likes": record.collected_likes,
                    "collects": record.collected_collects,
                    "comments": record.collected_comments,
                    "shares": record.collected_shares,
                    "author_fans": int(row.get("author_fans", 1) or 1),
                })
                db.add(record)
                imported += 1
            except Exception as e:
                errors += 1
                logger.warning(f"[csv_import] row failed: {e}")

        await db.commit()

    return StandardResponse(data={
        "imported": imported,
        "errors": errors,
        "platform": payload.platform,
    }, message=f"导入完成：{imported} 条成功，{errors} 条失败")


class CreateDraftRequest(BaseModel):
    title: str = Field(default="未命名草稿", max_length=512)
    platform: str = Field(default="xiaohongshu")
    topic: str | None = None


@router.post("/draft")
async def create_draft(
    payload: CreateDraftRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """创建草稿。"""
    from datetime import UTC, datetime
    record = PublishedContentPerformance(
        user_id=user_id,
        workflow_id="draft",
        title=payload.title,
        platform=payload.platform,
        topic=payload.topic,
        content_status="draft",
        published_at=datetime.now(UTC),
    )
    async with AsyncSessionLocal() as db:
        db.add(record)
        await db.commit()
        await db.refresh(record)
    return StandardResponse(data={
        "id": record.id,
        "title": record.title,
        "platform": record.platform,
        "content_status": record.content_status,
    })


class UpdateStatusRequest(BaseModel):
    content_status: str = Field(pattern="^(draft|published|collected)$")


@router.patch("/{record_id}/status")
async def update_content_status(
    record_id: str,
    payload: UpdateStatusRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """更新内容状态（草稿→已发布→已采集）。"""
    async with AsyncSessionLocal() as db:
        stmt = select(PublishedContentPerformance).where(
            PublishedContentPerformance.id == record_id,
            PublishedContentPerformance.user_id == user_id,
        )
        result = await db.scalars(stmt)
        record = result.first()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")
        record.content_status = payload.content_status
        await db.commit()
    return StandardResponse(data={"id": record_id, "content_status": payload.content_status})


@router.post("/{record_id}/refresh-images")
async def refresh_images(
    record_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """重新采集并缓存图片（解决 CDN 签名过期导致图片 403 的问题）。"""
    from app.services.work_collector import collect_from_url
    from app.services.image_store import cache_cover_image, cache_detail_images, is_local_url

    async with AsyncSessionLocal() as db:
        stmt = select(PublishedContentPerformance).where(
            PublishedContentPerformance.id == record_id,
            PublishedContentPerformance.user_id == user_id,
        )
        result = await db.scalars(stmt)
        record = result.first()
        if not record:
            raise HTTPException(status_code=404, detail="记录不存在")

        cover_cached = is_local_url(record.cover_img_url) if record.cover_img_url else True
        images_cached = bool(record.images and all(is_local_url(u) for u in record.images if u))

        if cover_cached and images_cached:
            return StandardResponse(data={"id": record_id, "status": "already_cached", "cover_img_url": record.cover_img_url})

        note_id = record.published_note_id
        platform = record.platform or "xiaohongshu"

        if note_id and platform == "xiaohongshu":
            note_url = f"https://www.xiaohongshu.com/explore/{note_id}"
            try:
                fresh_data = await collect_from_url(note_url, platform)
                if fresh_data:
                    fresh_cover = fresh_data.get("cover_img_url", "")
                    fresh_images = fresh_data.get("image_urls", [])

                    cache_id = note_id or record_id
                    try:
                        local_cover = await cache_cover_image(cache_id, fresh_cover)
                        if local_cover:
                            record.cover_img_url = local_cover
                    except Exception as e:
                        logger.warning(f"refresh_images cache_cover failed: {e}")

                    try:
                        local_images = await cache_detail_images(cache_id, fresh_images)
                        if local_images:
                            record.images = local_images
                    except Exception as e:
                        logger.warning(f"refresh_images cache_detail failed: {e}")

                    await db.commit()
                    await db.refresh(record)
                    return StandardResponse(data={
                        "id": record_id,
                        "status": "refreshed",
                        "cover_img_url": record.cover_img_url,
                    })
            except Exception as e:
                logger.warning(f"refresh_images collect failed: {e}")

        return StandardResponse(
            data={"id": record_id, "status": "failed", "cover_img_url": record.cover_img_url},
            message="重新采集失败，请手动删除后重新采集",
        )


# ═══════════════════════════════════════════
# 作品诊断（前端 work store 调用）
# ═══════════════════════════════════════════

@router.post("/{record_id}/diagnose")
async def diagnose_work(
    record_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """对单篇作品做 AI 诊断：分析标题/内容/标签的优化建议。"""
    try:
        from app.db.session import AsyncSessionLocal
        from app.db.models import PublishedContentPerformance
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            stmt = select(PublishedContentPerformance).where(
                PublishedContentPerformance.id == record_id,
                PublishedContentPerformance.user_id == user_id,
            )
            result = await db.execute(stmt)
            record = result.scalar_one_or_none()

            if not record:
                raise HTTPException(status_code=404, detail="作品不存在")

            title = record.title or ""
            content_text = getattr(record, "content_text", "") or ""
            tags = getattr(record, "tags", []) or []

            try:
                from app.engine.factory import get_deepseek_llm
                llm = get_deepseek_llm(model="deepseek-v3")
                prompt = (
                    f"分析以下小红书笔记，给出优化建议：\n\n"
                    f"标题：{title}\n"
                    f"正文：{content_text[:500]}\n"
                    f"标签：{', '.join(tags) if isinstance(tags, list) else str(tags)}\n\n"
                    "请从以下维度给出建议：\n"
                    "1. 标题吸引力（是否有悬念/数字/emoji）\n"
                    "2. 开头钩子（前3行是否抓住注意力）\n"
                    "3. 内容结构（是否有清晰分段/列表）\n"
                    "4. 标签覆盖（是否覆盖热门话题）\n"
                    "5. 互动引导（是否引导点赞/收藏/评论）\n\n"
                    "用 JSON 返回：{\"title_score\": 0-10, \"hook_score\": 0-10, "
                    "\"structure_score\": 0-10, \"tag_score\": 0-10, "
                    "\"interaction_score\": 0-10, \"suggestions\": [\"建议1\", \"建议2\"]}"
                )
                resp = await llm.chat(
                    [{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                )
                import json
                text = resp.get("content", "")
                diagnosis = json.loads(text)
            except Exception as llm_err:
                logger.warning(f"[diagnose] LLM failed: {llm_err}")
                diagnosis = {
                    "title_score": 5,
                    "hook_score": 5,
                    "structure_score": 5,
                    "tag_score": 5,
                    "interaction_score": 5,
                    "suggestions": ["AI 诊断暂不可用"],
                }

            return StandardResponse(data=diagnosis)

    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[diagnose] failed: {e}")
        return StandardResponse(data={"error": str(e)}, message="诊断失败")