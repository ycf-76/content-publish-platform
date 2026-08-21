"""Search node: 直接调 TrendingSearchSkill（不走 LLM Loop）。

搜索是确定性动作（调 API 拿数据），不需要 LLM 推理。
LLM 只在 analyze/copywrite 等需要推理的节点使用。

空结果 fallback：英文平台搜中文关键词返回 0 条时，调一次 LLM 翻译关键词重试。
这是 fallback 路径，主流程仍然不走 LLM。
"""

from __future__ import annotations

import asyncio
import logging

from app.agents.nodes._base import (
    NodeStatus,
    WorkflowState,
    _dlog,
    emit_node_event,
    logger,
)
from app.services.sse_bus import sse_bus


# 英文平台列表（这些平台搜中文关键词必然 0 结果，需要翻译）
_EN_PLATFORMS = {"hackernews", "reddit"}


async def _translate_keyword_for_en_platform(
    workflow_id: str,
    keyword: str,
) -> str | None:
    """调 LLM 把中文关键词翻译成英文（HackerNews/Reddit 等英文平台用）。

    红线：search 主流程不走 LLM，只在空结果 fallback 时调用此函数。
    LLM 不可用或调用失败时返回 None，调用方降级为原关键词。
    """
    from app.engine.factory import get_deepseek_llm

    llm = get_deepseek_llm()
    if llm is None:
        logger.info(f"[{workflow_id}] search retry: LLM unavailable, skip translation")
        return None

    # 极简 prompt，省钱：只输出翻译后的英文短语，不要解释
    prompt = (
        f"Translate the following search keyword to English for HackerNews search. "
        f"Output ONLY the translated English phrase (2-4 words), no quotes, no explanation.\n"
        f"Keyword: {keyword}"
    )
    try:
        resp = await llm.chat(messages=[{"role": "user", "content": prompt}])
        content = (resp.get("content") or "").strip().strip('"').strip("'")
        # 防御：去掉句号/换行，取第一行
        content = content.splitlines()[0].rstrip("。.").strip()
        if not content or len(content) > 100:
            logger.warning(
                f"[{workflow_id}] search retry: translation invalid: {content!r}"
            )
            return None
        logger.info(
            f"[{workflow_id}] search retry: translated '{keyword}' -> '{content}'"
        )
        return content
    except Exception as e:
        err_str = str(e)
        logger.warning(f"[{workflow_id}] search retry: translation failed: {e}")

        # 检测 DeepSeek 余额不足（402）→ 推送前端通知
        if "402" in err_str or "Insufficient Balance" in err_str or "余额" in err_str:
            await sse_bus.publish(workflow_id, "model_arrearage", {
                "workflow_id": workflow_id,
                "node_id": "search",
                "provider": "deepseek",
                "message": "DeepSeek 余额不足，无法翻译关键词（analyze 节点也会受影响）",
                "action_url": "https://platform.deepseek.com/usage",
                "action_text": "前往 DeepSeek 控制台充值",
            })
        return None


async def _save_search_results_to_pool(
    results: list[dict],
    keyword: str,
    workflow_id: str,
) -> None:
    """把搜索节点返回的结果存入选题池（fire-and-forget）。

    复用已有搜索结果，不重新抓取。按 (platform, content_id) + title 去重。
    auto_source='workflow'，与手动抓取(auto_source='manual')区分。
    """
    try:
        from app.db.session import AsyncSessionLocal
        from app.db.models import TopicPoolItem
        from sqlalchemy import select

        if not results:
            return

        # 预处理：过滤空标题，截断字段
        cleaned: list[dict] = []
        for item in results:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            platform = item.get("platform") or "unknown"
            cleaned.append({
                "platform": platform,
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
            return

        async with AsyncSessionLocal() as db:
            # 批量去重：按 platform 分组查 content_id + title
            saved_count = 0
            skipped_dup = 0
            seen_titles: set[str] = set()

            # 收集所有 content_id 和 title，跨平台查重（标题相同就跳过）
            all_titles = [it["title"] for it in cleaned]
            existing_titles: set[str] = set()
            if all_titles:
                rs = await db.execute(
                    select(TopicPoolItem.title).where(
                        TopicPoolItem.title.in_(all_titles)
                    )
                )
                existing_titles = {r[0] for r in rs if r[0]}

            # 按 (platform, content_id) 查重
            platform_cids: dict[str, list[str]] = {}
            for it in cleaned:
                if it["content_id"]:
                    platform_cids.setdefault(it["platform"], []).append(it["content_id"])

            existing_cids: set[tuple[str, str]] = set()
            for plat, cids in platform_cids.items():
                if cids:
                    rs = await db.execute(
                        select(TopicPoolItem.content_id).where(
                            TopicPoolItem.platform == plat,
                            TopicPoolItem.content_id.in_(cids),
                        )
                    )
                    for r in rs:
                        if r[0]:
                            existing_cids.add((plat, r[0]))

            for item in cleaned:
                key = (item["platform"], item["content_id"]) if item["content_id"] else None
                if key and key in existing_cids:
                    skipped_dup += 1
                    continue
                if item["title"] in existing_titles or item["title"] in seen_titles:
                    skipped_dup += 1
                    continue

                seen_titles.add(item["title"])
                pool_item = TopicPoolItem(
                    platform=item["platform"],
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
                    cover_img=item["cover_img"],
                    images=item["images"],
                    source_keyword=keyword[:500],
                    auto_source="workflow",
                )
                db.add(pool_item)
                saved_count += 1

            if saved_count > 0:
                await db.commit()

        logger.info(
            f"[{workflow_id}] search results saved to pool: "
            f"saved={saved_count}, skipped_dup={skipped_dup}, "
            f"total={len(cleaned)}"
        )
    except Exception as e:
        logger.warning(f"[{workflow_id}] save_search_results_to_pool failed: {e}")


async def _fetch_other_platforms_to_pool(keyword: str, workflow_id: str) -> None:
    """后台 fire-and-forget：抓取非小红书平台内容存入选题池。

    不阻塞主流程，异常静默（只记日志）。
    搜索 HackerNews/Reddit/tavily 等平台，结果存入 topic_pool_items 表。

    v2 优化：
    1. 各平台并发搜索（asyncio.gather），缩短总耗时
    2. 批量去重：一次性查所有 content_id + title，消除 N+1 查询
    3. 每平台独立 session，失败互不影响
    """
    try:
        from app.tools.sources.manager import source_manager
        from app.tools.trending_search import TrendingSearchSkill
        from app.db.session import AsyncSessionLocal
        from app.db.models import TopicPoolItem
        from sqlalchemy import select

        # 获取除 xiaohongshu 外的所有平台
        all_platforms = source_manager.list_platforms()
        other_platforms = [p for p in all_platforms if p != "xiaohongshu"]
        if not other_platforms:
            return

        skill = TrendingSearchSkill()

        async def _fetch_one(platform: str) -> list[dict]:
            """搜索单个平台，返回去重后待入库的 items。"""
            try:
                result = await skill.execute({
                    "keyword": keyword,
                    "limit": 10,
                    "platform": platform,
                    "disable_fallback": True,
                    "min_interactions": 0,
                })
                items = result.get("results", []) or []
                if not items:
                    return []

                # 预处理：过滤空标题，截断字段
                cleaned = []
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
                return cleaned
            except Exception as e:
                logger.warning(
                    f"[{workflow_id}] topic_pool: platform={platform} search failed: {e}"
                )
                return []

        # 并发搜索所有平台
        results_per_platform = await asyncio.gather(
            *[_fetch_one(p) for p in other_platforms]
        )

        total_saved = 0
        for platform, items in zip(other_platforms, results_per_platform):
            if not items:
                continue

            # 批量去重：一次查所有 content_id 和 title
            async with AsyncSessionLocal() as session:
                content_ids = [it["content_id"] for it in items if it["content_id"]]
                titles = [it["title"] for it in items]

                existing_cids: set[str] = set()
                existing_titles: set[str] = set()

                if content_ids:
                    rs = await session.execute(
                        select(TopicPoolItem.content_id).where(
                            TopicPoolItem.platform == platform,
                            TopicPoolItem.content_id.in_(content_ids),
                        )
                    )
                    existing_cids = {r[0] for r in rs if r[0]}

                if titles:
                    rs = await session.execute(
                        select(TopicPoolItem.title).where(
                            TopicPoolItem.platform == platform,
                            TopicPoolItem.title.in_(titles),
                        )
                    )
                    existing_titles = {r[0] for r in rs if r[0]}

                # 本批次内标题去重
                seen_titles: set[str] = set()
                saved_count = 0
                for item in items:
                    if item["content_id"] and item["content_id"] in existing_cids:
                        continue
                    if item["title"] in existing_titles:
                        continue
                    if item["title"] in seen_titles:
                        continue
                    seen_titles.add(item["title"])

                    session.add(TopicPoolItem(
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
                        cover_img=item["cover_img"],
                        images=item["images"],
                        source_keyword=keyword[:500],
                        raw=item["raw"],
                    ))
                    saved_count += 1

                if saved_count > 0:
                    await session.commit()

                total_saved += saved_count
                logger.info(
                    f"[{workflow_id}] topic_pool: platform={platform}, "
                    f"fetched={len(items)}, saved_new={saved_count}"
                )

        if total_saved > 0:
            logger.info(
                f"[{workflow_id}] topic_pool: saved {total_saved} items "
                f"from {len(other_platforms)} platforms (keyword={keyword!r})"
            )
    except Exception as e:
        # fire-and-forget：异常不传播，只记日志
        logger.warning(f"[{workflow_id}] _fetch_other_platforms_to_pool failed: {e}")


class _EmptySearchError(Exception):
    """搜索结果为空（触发 recovery 重试/拓宽关键词）。"""


async def _execute_search_with_recovery(
    workflow_id: str,
    node_id: str,
    skill,
    search_input: dict,
    timeout: float,
) -> dict:
    """执行搜索，并在空结果/异常时走 recovery：原样重试 → 拓宽关键词重试。

    复用 RecoveryLoop（RetryStrategy + BroadenKeywordStrategy），
    通过 _make_observer 把 recovery_* / circuit_open 事件桥接到 SSE。
    """
    from app.engine.harness.recovery import (
        BackoffPolicy,
        BroadenKeywordStrategy,
        RecoveryLoop,
        RetryStrategy,
    )
    from app.engine.schemas import RecoveryExhaustedError, WorkflowContext
    from app.engine.factory import _make_observer

    observer = _make_observer(workflow_id)
    recovery = RecoveryLoop(
        max_attempts=2,
        strategies=[RetryStrategy(), BroadenKeywordStrategy()],
        backoff=BackoffPolicy(base_delay=1.0, max_delay=10.0),
        observer=observer,
    )
    context = WorkflowContext(
        workflow_id=workflow_id,
        node_id=node_id,
        user_id="",
        account_id="",
    )

    class _AgentStub:
        agent_id = node_id

    async def _execute(inp: dict, ctx: WorkflowContext) -> dict:
        result = await asyncio.wait_for(skill.execute(inp), timeout=timeout)
        if result.get("count", 0) == 0:
            raise _EmptySearchError(f"搜索 '{inp.get('keyword')}' 无结果")
        return result

    try:
        return await recovery.execute_with_recovery(
            _AgentStub(), search_input, context, _execute
        )
    except RecoveryExhaustedError:
        return {
            "results": [],
            "count": 0,
            "summary": "搜索无结果（已重试并拓宽关键词）",
            "platform": search_input.get("platform", ""),
            "_error": "搜索无结果",
            "_error_type": "no_results",
        }


async def search_node(state: WorkflowState) -> dict:
    """Search node: 直接调 TrendingSearchSkill（不走 LLM Loop，避免依赖 LLM 余额）。

    搜索是确定性动作（调 API 拿数据），不需要 LLM 推理。
    LLM 只在 analyze/copywrite 等需要推理的节点使用。

    空结果 fallback：英文平台搜中文关键词返回 0 条时，调一次 LLM 翻译关键词重试。
    这是 fallback 路径，主流程仍然不走 LLM。
    """
    workflow_id = state["workflow_id"]
    node_id = "search"

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started (direct skill call, no LLM)")

    topic = state.get("topic", "")
    search_keyword = (state.get("search_keyword") or topic).strip()
    account_id = state.get("account_id", "")

    # 用户可在前端配置搜索结果数量（默认 10，避免返回过多浪费资源）
    model_settings = state.get("model_settings", {}) or {}
    search_limit = int(model_settings.get("search_limit", 10))
    # 防御：限制在 5-30 之间
    search_limit = max(5, min(30, search_limit))
    # 搜索平台：用户在前端选择的平台（空=全网搜索并发所有平台，默认 xiaohongshu）
    search_platform = str(model_settings.get("search_platform", "") or "").strip()
    if not search_platform:
        search_platform = ""  # 空字符串触发全网并发搜索

    try:
        from app.tools.trending_search import TrendingSearchSkill

        skill = TrendingSearchSkill()

        # 按用户选择的平台搜索：空=全网并发，非空=指定平台
        # 空结果/超时走 RecoveryLoop：原样重试 → 拓宽关键词重试
        SEARCH_TIMEOUT = 60.0
        search_input = {
            "keyword": search_keyword,
            "limit": search_limit,
            "min_interactions": 5,
            "time_range": "week",
            "platform": search_platform,
            "disable_fallback": False,  # 允许热门榜兜底，避免空结果中断流程
        }
        output = await _execute_search_with_recovery(
            workflow_id, node_id, skill, search_input, SEARCH_TIMEOUT
        )

        searched_platforms = output.get("filter_stats", {}).get("searched_platforms", [])

        # 后台 fire-and-forget：仅"全网搜索"时抓取其他平台内容存入选题池
        # 用户指定了具体平台时，尊重指定，不抓其他平台（贯彻"按指定来搜"）
        if not search_platform:
            asyncio.create_task(_fetch_other_platforms_to_pool(search_keyword, workflow_id))

        output["_model_used"] = "none (xiaohongshu only)"
        output["_duration_ms"] = 0
        output["_token_usage"] = {"prompt": 0, "completion": 0, "total": 0}

        final_count = output.get("count", 0)
        final_fallback = output.get("filter_stats", {}).get("fallback_used", False)
        logger.info(
            f"[{workflow_id}] {node_id} completed: "
            f"platform={output.get('platform')}, count={final_count}, "
            f"fallback={final_fallback}"
        )

        # 空结果：标记 ERROR 终止工作流
        if final_count == 0:
            output["_error"] = (
                f"小红书搜索关键词 '{search_keyword}' 无结果"
                "，请更换为更通用的小红书常用词后重试"
            )
            output["_error_type"] = "no_results"
            await sse_bus.publish(workflow_id, "workflow_error", {
                "workflow_id": workflow_id,
                "node_id": node_id,
                "error_type": "no_results",
                "message": output["_error"],
                "suggestion": "请尝试更换为小红书上更通用的搜索词",
            })
            await emit_node_event(workflow_id, node_id, "node_status_changed",
                                   {"status": "error"})
            await emit_node_event(workflow_id, node_id, "node_completed", output)
            return {
                "current_node": node_id,
                "node_statuses": {node_id: NodeStatus.ERROR.value},
                "node_outputs": {node_id: output},
            }

    except Exception as e:
        logger.exception(f"[{workflow_id}] {node_id} search failed: {e}")
        await emit_node_event(workflow_id, node_id, "node_error",
                              {"error": str(e), "error_type": type(e).__name__})
        output = {
            "results": [],
            "count": 0,
            "summary": f"search failed: {e}",
            "platform": "unknown",
            "_error": str(e),
            "_error_type": "search_exception",
        }
        await sse_bus.publish(workflow_id, "workflow_error", {
            "workflow_id": workflow_id,
            "node_id": node_id,
            "error_type": "search_exception",
            "message": f"搜索节点异常: {e}",
        })
        await emit_node_event(workflow_id, node_id, "node_status_changed",
                               {"status": "error"})
        await emit_node_event(workflow_id, node_id, "node_completed", output)
        return {
            "current_node": node_id,
            "node_statuses": {node_id: NodeStatus.ERROR.value},
            "node_outputs": {node_id: output},
        }

    await emit_node_event(workflow_id, node_id, "node_completed", output)

    # 后台 fire-and-forget：把搜索结果存入选题池（auto_source='workflow'）
    search_results = output.get("results", []) or []
    if search_results:
        asyncio.create_task(
            _save_search_results_to_pool(search_results, search_keyword, workflow_id)
        )

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }
