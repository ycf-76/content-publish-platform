"""LangGraph orchestration layer.

Corresponds to architecture doc Ch.5 (Layer A).
Red lines:
- Nodes must call Harness, not MCP/LLM directly.
- Routing must be hardcoded (no LLM decisions).
- Use SqliteSaver for checkpoints (persistent, no stale state across restarts).
- 软语义节点（quality_check_*）是分散式守卫，只判质量不做路由决策。
"""

from __future__ import annotations

import asyncio
import json
import logging
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, TypedDict

from app.services.sse_bus import sse_bus


def _merge_dict(left: dict, right: dict | None) -> dict:
    """LangGraph reducer for dict fields: merge right into left (non-destructive).

    用于 node_outputs / node_statuses：每个节点返回自己的部分，
    reducer 会合并到现有 state 中，而不是覆盖整个 dict。
    """
    if right is None:
        return left or {}
    result = dict(left or {})
    result.update(right)
    return result

# Optional imports for LangGraph
# 注意：PostgresSaver 的导入依赖 psycopg_binary，未安装时会 ImportError。
# 项目用 AsyncSqliteSaver（持久化）做 interrupt/resume，不需要 PostgresSaver，所以单独 try，不阻塞 StateGraph。
try:
    from langgraph.graph import END, StateGraph
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    END = None
    StateGraph = None
    AsyncSqliteSaver = None

# PostgresSaver 仅在需要 PostgreSQL checkpointer 时使用，可选
try:
    from langgraph.checkpoint.postgres import PostgresSaver  # noqa: F401
except ImportError:
    PostgresSaver = None


# 全局 AsyncSqliteSaver 单例（持久化 checkpointer）
# 用于支持 interrupt_before + resume 机制：
# - analyze 节点前 interrupt，等待用户点击"进入分析"
# - image_gen 节点前 interrupt，等待前端卡片编辑器注入图片
# - image_review 节点前 interrupt，等待人工审核
# - final_review 节点前 interrupt，等待人工审核
# - 持久化到磁盘，进程重启后状态不丢失（解决 MemorySaver 重启丢状态问题）
# - 必须用 Async 版本：langgraph 的 astream/astream(None) 要求 saver 支持 async 接口
_global_checkpointer = None


async def init_global_checkpointer():
    """在应用 lifespan 启动时初始化全局 AsyncSqliteSaver 单例。

    必须在 async context 中调用（aiosqlite.connect 需要 await）。
    全局共享保证：start_workflow 启动 graph 和 submit_review/inject resume graph
    必须使用同一个 checkpointer 实例，否则 thread_id 无法关联状态。

    持久化到 backend/data/langgraph_checkpoints.sqlite：
    - 后端重启后 checkpoint 保留，中断的工作流可继续 resume
    - AsyncSqliteSaver 配合 astream(input) / astream(None) resume 使用
    """
    global _global_checkpointer
    if _global_checkpointer is None:
        import os

        # checkpoint 数据库路径：backend/data/langgraph_checkpoints.sqlite
        data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
        os.makedirs(data_dir, exist_ok=True)
        db_path = os.path.join(data_dir, "langgraph_checkpoints.sqlite")

        # Windows + aiosqlite + AsyncSqliteSaver 反复出现 disk I/O error：
        # setup() 是幂等的（CREATE TABLE IF NOT EXISTS，表已存在不报错），
        # 无法暴露运行时写入失败 —— graph 执行时 checkpointer.aput 才报错，此时已无法降级。
        # 默认直接用 MemorySaver 彻底绕过；如需持久化 checkpoint，
        # 设置环境变量 LANGGRAPH_USE_SQLITE=1 启用 AsyncSqliteSaver（含写入测试）。
        use_sqlite = os.environ.get("LANGGRAPH_USE_SQLITE") == "1"

        if use_sqlite and AsyncSqliteSaver is not None:
            conn = None
            try:
                import sqlite3
                import aiosqlite

                # Windows 兼容：主线程先用 sqlite3 预创建文件 + WAL 模式，
                # 然后 aiosqlite.connect 只需"打开已存在文件"，避开创建路径上的偶发 bug
                priming = sqlite3.connect(db_path, check_same_thread=False)
                try:
                    priming.execute("PRAGMA journal_mode=WAL;")
                    priming.execute("PRAGMA busy_timeout=5000;")
                    priming.execute("PRAGMA synchronous=NORMAL;")
                    priming.commit()
                finally:
                    priming.close()

                conn = await aiosqlite.connect(db_path)
                await conn.execute("PRAGMA journal_mode=WAL;")
                await conn.execute("PRAGMA busy_timeout=5000;")
                _global_checkpointer = AsyncSqliteSaver(conn)
                await _global_checkpointer.setup()  # 建表（幂等）

                # 写入测试：setup() 幂等无法验证真实写入能力。
                # PRAGMA wal_checkpoint(TRUNCATE) 强制 WAL 刷盘，暴露磁盘 I/O 问题；
                # 失败则立即降级到 MemorySaver，避免 graph 执行时才报错。
                await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

                logger.info(f"[graph] AsyncSqliteSaver initialized + write-tested at {db_path}")
                import sys
                print("[graph] init_global_checkpointer OK: AsyncSqliteSaver", file=sys.stderr, flush=True)
                return _global_checkpointer
            except Exception as e:
                logger.warning(
                    f"[graph] AsyncSqliteSaver init/write-test failed, falling back to MemorySaver: {e}"
                )
                # 清理：关闭泄漏的 conn，重置 checkpointer，走默认降级
                if conn is not None:
                    try:
                        await conn.close()
                    except Exception:
                        pass
                _global_checkpointer = None

        # 默认方案：MemorySaver（内存 checkpointer，重启后断点丢失，但工作流可运行）
        # resume 时若 checkpoint 丢失，前端提示用户重新开始工作流
        try:
            from langgraph.checkpoint.memory import MemorySaver
            _global_checkpointer = MemorySaver()
            logger.info("[graph] MemorySaver initialized (checkpoints not persisted across restarts)")
            import sys
            print("[graph] init_global_checkpointer OK: MemorySaver", file=sys.stderr, flush=True)
        except Exception as e:
            logger.error(f"[graph] MemorySaver init also failed: {e}")
            _global_checkpointer = None
    return _global_checkpointer


def get_global_checkpointer():
    """获取已初始化的全局 AsyncSqliteSaver 单例。

    注意：必须在应用启动时调用 init_global_checkpointer() 完成初始化后才能使用。
    若未初始化，返回 None（build_workflow_graph 会因缺少 checkpointer 跳过 interrupt 支持）。
    """
    if _global_checkpointer is None:
        import sys
        print("[graph] WARNING: get_global_checkpointer() returns None — init not called?", file=sys.stderr, flush=True)
    return _global_checkpointer

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ===== DEBUG: 发布流程诊断日志（写到独立文件，便于排查 publish 不执行的问题） =====
import os as _os
_debug_logger = logging.getLogger("publish_debug")
if not _debug_logger.handlers:
    _debug_logger.setLevel(logging.DEBUG)
    try:
        _log_dir = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "logs")
        _os.makedirs(_log_dir, exist_ok=True)
        _fh = logging.FileHandler(_os.path.join(_log_dir, "publish_debug.log"), encoding="utf-8")
        _fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        _debug_logger.addHandler(_fh)
    except Exception:
        pass
_debug_logger.propagate = False

def _dlog(msg: str) -> None:
    _debug_logger.info(msg)


# ---------------------------------------------------------------------------
# Node Status Enum (9 states, matching protocol Ch.4)
# ---------------------------------------------------------------------------


class NodeStatus(str, Enum):  # ruff: noqa: UP042
    """Node status enum matching protocol."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_REVIEW = "awaiting_review"
    PASSED = "passed"
    REJECTED = "rejected"
    ERROR = "error"
    SUSPENDED = "suspended"
    COMPLETED = "completed"
    TERMINATED = "terminated"


# ---------------------------------------------------------------------------
# Workflow State (TypedDict for LangGraph)
# ---------------------------------------------------------------------------


class WorkflowState(TypedDict, total=False):
    """Workflow state passed between LangGraph nodes.

    D6: No stale state field. Recovery uses LangGraph native checkpoint.
    """

    workflow_id: str
    user_id: str
    account_id: str
    topic: str
    current_node: str
    # Annotated reducer：节点返回的部分 dict 会被合并到现有 state，
    # 而不是覆盖整个 node_statuses / node_outputs。
    # 这样新增节点不需要透传前序节点的输出。
    node_statuses: Annotated[dict[str, str], _merge_dict]  # node_key -> NodeStatus.value
    node_outputs: Annotated[dict[str, dict], _merge_dict]  # node_key -> output_data
    node_errors: Annotated[dict[str, dict], _merge_dict]  # node_key -> error info
    recovery_attempts: Annotated[dict[str, int], _merge_dict]  # node_key -> attempts count
    pending_reviews: list[dict]  # current pending reviews
    pending_suggestions: list[dict]  # supervisor suggestions
    suspended_until: str | None  # ISO datetime for D15 suspension
    # 用户在右侧工作区选择的模型/温度/风格配置（透传到各节点）
    # 字段：text_model, image_model, temperature, writing_style, image_style
    model_settings: dict
    # 选题池参考素材（从选题池"发起新工作流"时携带）
    # 包含 title/summary/url/platform/source_keyword/likes 等，
    # 注入 copywrite 节点的 LLM prompt 作为参考内容
    reference: dict
    # 用户级长期记忆（工作流启动时从 AgentMemory 加载）
    # 字段：writing_style / image_style / preferred_topics / avoided_topics
    #       / recent_topics / recent_copywrites
    # 各节点读取此字段注入 prompt（如 copywrite 注入历史文案 + 偏好文风）
    user_memory: dict


def initial_state(
    workflow_id: str,
    user_id: str,
    account_id: str,
    topic: str,
    model_settings: dict | None = None,
    reference: dict | None = None,
    user_memory: dict | None = None,
) -> WorkflowState:
    """Create initial workflow state."""
    return WorkflowState(
        workflow_id=workflow_id,
        user_id=user_id,
        account_id=account_id,
        topic=topic,
        current_node="search",
        node_statuses={
            "search": NodeStatus.PENDING.value,
            "analyze": NodeStatus.PENDING.value,
            "image_plan": NodeStatus.PENDING.value,
            "image_gen": NodeStatus.PENDING.value,
            "image_review": NodeStatus.PENDING.value,
            "copywrite": NodeStatus.PENDING.value,
            "audit": NodeStatus.PENDING.value,
            "final_review": NodeStatus.PENDING.value,
            "publish": NodeStatus.PENDING.value,
        },
        node_outputs={},
        node_errors={},
        recovery_attempts={},
        pending_reviews=[],
        pending_suggestions=[],
        suspended_until=None,
        # 用户在右侧工作区选择的模型/温度/风格配置（None 时用空 dict）
        model_settings=dict(model_settings or {}),
        # 选题池参考素材（None 时用空 dict）
        reference=dict(reference or {}),
        # 用户级长期记忆（None 时用空 dict）
        user_memory=dict(user_memory or {}),
    )


# ---------------------------------------------------------------------------
# SSE Event Helpers
# ---------------------------------------------------------------------------


async def emit_workflow_event(
    workflow_id: str,
    event_type: str,
    payload: dict,
) -> None:
    """Emit workflow-level SSE event."""
    await sse_bus.publish(workflow_id, event_type, payload)


async def emit_node_event(
    workflow_id: str,
    node_id: str,
    event_type: str,
    payload: dict | None = None,
) -> None:
    """Emit node-level SSE event."""
    await sse_bus.publish(
        workflow_id,
        event_type,
        {"node_id": node_id, **(payload or {})},
    )


async def _run_node_harness(
    node_id: str,
    workflow_id: str,
    state: WorkflowState,
    harness_factory: str,
    harness_input: dict,
    fallback_output: dict,
) -> dict:
    """统一调用 harness 的封装。

    - harness_factory: app.agents.harnesses.factory 里的函数名
    - 失败时发 node_error 事件，并把 fallback_output 作为 node_outputs 写回状态，
      保证 workflow 不因单节点崩溃而中断。
    - 把 workflow_id 写入 current_workflow_id ContextVar，让 MCP 层能感知上下文。
    """
    from app.agents.core.schemas import WorkflowContext
    from app.agents.harnesses import factory as harness_factory_mod
    from app.services.context import current_workflow_id

    factory_fn = getattr(harness_factory_mod, harness_factory, None)
    if factory_fn is None:
        logger.error(f"[{workflow_id}] {node_id} unknown harness factory: {harness_factory}")
        await emit_node_event(workflow_id, node_id, "node_error",
                              {"error": f"unknown factory: {harness_factory}"})
        return dict(fallback_output)

    context = WorkflowContext(
        workflow_id=workflow_id,
        node_id=node_id,
        user_id=state.get("user_id", ""),
        account_id=state.get("account_id", ""),
        topic=state.get("topic", ""),
        upstream_outputs=state.get("node_outputs", {}),
    )

    token = current_workflow_id.set(workflow_id)
    try:
        harness = factory_fn(workflow_id)
        agent_output = await harness.run(harness_input, context)
        output = dict(agent_output.output)
        # 透传 trace 元数据（不写库，仅 SSE 用）
        output["_token_usage"] = agent_output.token_usage
        output["_duration_ms"] = agent_output.duration_ms
        output["_model_used"] = agent_output.model_used or ""
        return output
    except Exception as e:
        logger.exception(f"[{workflow_id}] {node_id} harness run failed: {e}")
        await emit_node_event(workflow_id, node_id, "node_error",
                              {"error": str(e), "error_type": type(e).__name__})
        return {**fallback_output, "_error": str(e)}
    finally:
        current_workflow_id.reset(token)


# ---------------------------------------------------------------------------
# Node Functions
# ---------------------------------------------------------------------------


async def _translate_keyword_for_en_platform(
    workflow_id: str,
    keyword: str,
) -> str | None:
    """调 LLM 把中文关键词翻译成英文（HackerNews/Reddit 等英文平台用）。

    红线：search 主流程不走 LLM，只在空结果 fallback 时调用此函数。
    LLM 不可用或调用失败时返回 None，调用方降级为原关键词。
    """
    from app.agents.harnesses.factory import get_deepseek_llm

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


# 英文平台列表（这些平台搜中文关键词必然 0 结果，需要翻译）
_EN_PLATFORMS = {"hackernews", "reddit"}


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
        from app.agents.skills.sources.manager import source_manager
        from app.agents.skills.trending_search import TrendingSearchSkill
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
        from app.agents.skills.trending_search import TrendingSearchSkill

        skill = TrendingSearchSkill()

        # 按用户选择的平台搜索：空=全网并发，非空=指定平台
        # 整体超时 60s：防止小红书 Playwright 卡死导致搜索无限挂起
        # 超时后给用户明确反馈，终止工作流
        SEARCH_TIMEOUT = 60.0
        try:
            output = await asyncio.wait_for(
                skill.execute({
                    "keyword": topic,
                    "limit": search_limit,
                    "min_interactions": 5,
                    "time_range": "week",
                    "platform": search_platform,
                    "disable_fallback": False,  # 允许热门榜兜底，避免空结果中断流程
                }),
                timeout=SEARCH_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.error(
                f"[{workflow_id}] {node_id} search timeout after {SEARCH_TIMEOUT}s"
            )
            output = {
                "results": [],
                "count": 0,
                "summary": f"搜索超时（{int(SEARCH_TIMEOUT)}秒），请稍后重试",
                "platform": search_platform or "all",
                "_error": f"搜索超时，已自动终止（{int(SEARCH_TIMEOUT)}秒）",
                "_error_type": "search_timeout",
            }
            await sse_bus.publish(workflow_id, "workflow_error", {
                "workflow_id": workflow_id,
                "node_id": node_id,
                "error_type": "search_timeout",
                "message": f"搜索超时，已自动终止（{int(SEARCH_TIMEOUT)}秒），请稍后重试",
                "suggestion": "小红书接口可能较慢或网络不畅，请稍后重试或更换关键词",
            })
            await emit_node_event(workflow_id, node_id, "node_status_changed",
                                   {"status": "error"})
            await emit_node_event(workflow_id, node_id, "node_completed", output)
            return {
                "current_node": node_id,
                "node_statuses": {node_id: NodeStatus.ERROR.value},
                "node_outputs": {node_id: output},
            }

        searched_platforms = output.get("filter_stats", {}).get("searched_platforms", [])

        # 后台 fire-and-forget：仅"全网搜索"时抓取其他平台内容存入选题池
        # 用户指定了具体平台时，尊重指定，不抓其他平台（贯彻"按指定来搜"）
        if not search_platform:
            asyncio.create_task(_fetch_other_platforms_to_pool(topic, workflow_id))

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
                f"小红书搜索关键词 '{topic}' 无结果"
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
            _save_search_results_to_pool(search_results, topic, workflow_id)
        )

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }


async def analyze_node(state: WorkflowState) -> dict:
    """Analyze node: 三层分层分析架构。

    Layer 1：规则层（0 LLM 成本）—— 派生指标 + 分位数分类 + 爆点分排序
    Layer 2：LLM 粗分析（top 5，1 次调用）—— 标题钩子 / 内容结构 / 情绪触发点
    Layer 3：LLM 深度归因（top 2，1 次调用）—— 趋势信号 + 选题建议

    可插拔：通过 SkillRegistry 加载 analyze 节点的 Skill 子类，
    第三方可在 backend/skills/ 下注册自己的 AnalyzeSkillBase 子类。

    LLM 不可用时降级为只返回 Layer 1 结果。
    """
    import time
    from app.agents.skills.viral_analyzer import analyze_viral
    from app.agents.harnesses.factory import get_deepseek_llm
    from app.agents.skills.registry import get_skill_class
    # 触发内置 Skill 注册（import 即注册）
    import app.agents.skills.analyze_skill  # noqa: F401

    workflow_id = state["workflow_id"]
    node_id = "analyze"

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started (3-layer analysis)")

    topic = state.get("topic", "")
    # 用户在右侧工作区选择的模型/温度/analyze skill 配置
    model_settings = state.get("model_settings", {}) or {}
    user_temperature = model_settings.get("temperature")
    user_text_model = model_settings.get("text_model")
    # 用户可选择 analyze 节点的 skill name（None 时用默认 "standard"）
    analyze_skill_name = model_settings.get("analyze_skill") or "standard"
    search_output = state.get("node_outputs", {}).get("search", {})
    raw_results = search_output.get("results", [])

    # 用户级长期记忆中的偏好（preferred_topics / avoided_topics）
    # 注入 Layer3 prompt，让 LLM 推荐选题时优先/避免某些方向
    user_memory = state.get("user_memory", {}) or {}
    user_preferences = {
        "preferred_topics": user_memory.get("preferred_topics") or [],
        "avoided_topics": user_memory.get("avoided_topics") or [],
    }

    # 通过 registry 加载 analyze Skill（支持第三方插件）
    analyze_skill_cls = get_skill_class("analyze", analyze_skill_name)
    if analyze_skill_cls is None:
        logger.warning(
            f"[{workflow_id}] analyze skill '{analyze_skill_name}' not found, "
            f"falling back to StandardAnalyzeSkill"
        )
        from app.agents.skills.analyze_skill import StandardAnalyzeSkill
        analyze_skill_cls = StandardAnalyzeSkill
    analyze_skill = analyze_skill_cls()
    logger.info(
        f"[{workflow_id}] analyze using skill: {analyze_skill.name} "
        f"({analyze_skill.__class__.__name__})"
    )

    start_time = time.time()
    total_tokens = 0
    model_used = "layer1_only"

    try:
        # ===== Layer 1: 规则层（0 LLM 成本） =====
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 33,
            "current_node": node_id,
            "layer": 1,
            "message": "Layer 1 规则层：计算派生指标与爆款分类",
        })
        with_metrics, layer1_stats = analyze_viral(raw_results)
        logger.info(
            f"[{workflow_id}] analyze Layer1 done: "
            f"total={layer1_stats.get('total', 0)}, "
            f"method={layer1_stats.get('classification_method')}, "
            f"distribution={layer1_stats.get('type_distribution')}"
        )

        # LLM 不可用时降级（使用用户配置的温度+模型）
        llm = get_deepseek_llm(temperature=user_temperature, model=user_text_model)
        if llm is None:
            logger.warning(f"[{workflow_id}] analyze: LLM unavailable, Layer1 only")
            output = {
                "results": with_metrics,
                "patterns": {"_skipped": "no_llm"},
                "insights": {"_skipped": "no_llm"},
                "filter_stats": search_output.get("filter_stats", {}),
                "layer1_stats": layer1_stats,
                "_model_used": "none (layer1 only)",
                "_duration_ms": int((time.time() - start_time) * 1000),
                "_token_usage": {"prompt": 0, "completion": 0, "total": 0},
            }
            await emit_node_event(workflow_id, node_id, "node_completed", output)
            return {
                "current_node": node_id,
                "node_statuses": {node_id: NodeStatus.COMPLETED.value},
                "node_outputs": {node_id: output},
            }

        # ===== Layer 2: LLM 粗分析（top 5） =====
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 60,
            "current_node": node_id,
            "layer": 2,
            "message": "Layer 2 LLM 粗分析：识别标题钩子 / 内容结构 / 情绪触发点",
        })
        await emit_node_event(workflow_id, node_id, "tool_call_start", {
            "tool": "deepseek_layer2",
            "input_size": min(5, len(with_metrics)),
        })
        top5 = with_metrics[:5]
        patterns = await analyze_skill.analyze_layer2(llm, top5, topic)
        await emit_node_event(workflow_id, node_id, "tool_call_end", {
            "tool": "deepseek_layer2",
            "success": "_error" not in patterns and "_parse_failed" not in patterns,
        })
        logger.info(
            f"[{workflow_id}] analyze Layer2 done: "
            f"patterns_keys={list(patterns.keys())}"
        )

        # ===== Layer 3: LLM 深度归因（top 2） =====
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 85,
            "current_node": node_id,
            "layer": 3,
            "message": "Layer 3 LLM 深度归因：趋势信号 + 选题建议",
        })
        await emit_node_event(workflow_id, node_id, "tool_call_start", {
            "tool": "deepseek_layer3",
            "input_size": min(2, len(with_metrics)),
        })
        top2 = with_metrics[:2]
        insights = await analyze_skill.analyze_layer3(
            llm, top2, with_metrics, patterns, topic, user_preferences
        )
        await emit_node_event(workflow_id, node_id, "tool_call_end", {
            "tool": "deepseek_layer3",
            "success": "_error" not in insights and "_parse_failed" not in insights,
        })
        logger.info(
            f"[{workflow_id}] analyze Layer3 done: "
            f"insights_keys={list(insights.keys())}"
        )

        model_used = "deepseek-v3 (3-layer)"

        # 组装最终输出
        output = {
            "results": with_metrics,
            "patterns": patterns,
            "insights": insights,
            "filter_stats": search_output.get("filter_stats", {}),
            "layer1_stats": layer1_stats,
            "_model_used": model_used,
            "_duration_ms": int((time.time() - start_time) * 1000),
            "_token_usage": {"prompt": 0, "completion": 0, "total": total_tokens},
        }

        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 100,
            "current_node": node_id,
            "layer": "done",
            "message": "三层分析完成",
        })
        await emit_node_event(workflow_id, node_id, "node_completed", output)

    except Exception as e:
        logger.exception(f"[{workflow_id}] analyze_node failed: {e}")
        await emit_node_event(workflow_id, node_id, "node_error",
                              {"error": str(e), "error_type": type(e).__name__})
        # 降级：只返回原始 results
        output = {
            "results": raw_results,
            "patterns": {"_error": str(e)},
            "insights": {"_error": str(e)},
            "filter_stats": search_output.get("filter_stats", {}),
            "layer1_stats": {},
            "_model_used": "error_fallback",
            "_duration_ms": int((time.time() - start_time) * 1000),
            "_error": str(e),
        }
        await emit_node_event(workflow_id, node_id, "node_completed", output)

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }


# ---------------------------------------------------------------------------
# Image Plan Node：调 LLM 生成 blueprint（动态布局蓝图）
# ---------------------------------------------------------------------------


async def image_plan_node(state: WorkflowState) -> dict:
    """图片规划节点：调 LLM 生成 4 张卡片的文案初稿（card_draft），供前端卡片编辑器加载。

    唯一职责：
    - 读取 copywrite 的 title/content/tags/key_points
    - 调 LLM 生成 card_draft（4 张卡：cover/content/quote/list 的文案）
    - 工作流在 image_gen 前 interrupt，前端编辑器加载 card_draft 供用户调整
    - 用户调整后 html2canvas 出图，通过 inject 接口注入 image_gen 输出

    红线：
    - 本节点不生成图片（不调 Playwright，不调通义万相）
    - 只输出文案初稿，图片由前端卡片编辑器生成
    """
    import time
    import json as _json

    workflow_id = state["workflow_id"]
    node_id = "image_plan"
    start_time = time.time()

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    try:
        copywrite_output = state.get("node_outputs", {}).get("copywrite", {})
    except Exception:
        copywrite_output = {}
    title = (copywrite_output or {}).get("title", "")
    content = (copywrite_output or {}).get("content", "")
    tags = (copywrite_output or {}).get("tags", [])
    key_points = (copywrite_output or {}).get("key_points", [])
    structured_items = (copywrite_output or {}).get("structured_items", []) or []
    topic = state.get("topic", "")

    # 读取 analyze 的 execution_brief（配图风格建议 + 内容类型）
    # 让卡片文案风格和文案内容保持一致
    analyze_output = state.get("node_outputs", {}).get("analyze", {}) or {}
    analyze_insights = analyze_output.get("insights", {}) or {}
    analyze_recommendations = analyze_insights.get("recommendations") or []
    visual_suggestion = ""
    analyze_content_type = ""
    if analyze_recommendations and isinstance(analyze_recommendations[0], dict):
        brief = analyze_recommendations[0].get("execution_brief") or {}
        if isinstance(brief, dict):
            visual_suggestion = str(brief.get("visual_suggestion", "")).strip()
            analyze_content_type = str(brief.get("content_type", "")).strip()

    # 用户配置
    model_settings = state.get("model_settings", {}) or {}
    user_temperature = model_settings.get("temperature")
    user_text_model = model_settings.get("text_model")

    from app.agents.harnesses.factory import get_deepseek_llm

    await emit_node_event(workflow_id, node_id, "progress_update", {
        "progress": 30,
        "step": "card_draft_planning",
        "message": "LLM 正在规划卡片文案...",
    })

    llm = get_deepseek_llm(temperature=user_temperature, model=user_text_model)

    card_draft: dict = {"pages": [], "suggested_template": "minimal_white"}
    model_used = "fallback"

    try:
        if structured_items:
            # 知识清单型：直接构造卡片，每页 4-5 个词条，零 LLM 成本
            # 第 1 张固定封面，后续按每页 4 条切分 structured_items
            items_per_page = 4
            pages_list: list[dict] = [{
                "type": "cover",
                "title": title[:40] if title else topic,
                "subtitle": f"共 {len(structured_items)} 个知识点",
                "footer": "@灵犀工坊",
            }]
            for i in range(0, len(structured_items), items_per_page):
                chunk = structured_items[i:i + items_per_page]
                list_items = [
                    f"{it.get('term', '')}：{it.get('definition', '')}"
                    for it in chunk
                    if it.get("term")
                ]
                if list_items:
                    pages_list.append({
                        "type": "list",
                        "title": f"{topic}（{i + 1}-{i + len(list_items)}）",
                        "listItems": list_items,
                        "footer": f"第 {len(pages_list)}/{((len(structured_items) - 1) // items_per_page) + 2} 页",
                    })
            card_draft = {
                "pages": pages_list,
                "suggested_template": _recommend_template(topic, analyze_content_type),
            }
            model_used = "structured_split (no LLM)"
            logger.info(
                f"[{workflow_id}] {node_id} structured card_draft: "
                f"{len(pages_list)} pages from {len(structured_items)} items"
            )
        else:
            # 非知识清单型：调 LLM 规划 4 张卡（cover/content/quote/list）
            # 构造 prompt：让 LLM 根据 copywrite 生成 4 张卡的文案初稿
            # 输出格式严格匹配前端 CardEditorPanel 的 CardPage 结构
            visual_hint = (
                f"\n**配图风格建议**（来自分析节点，卡片文案风格应与此一致）:\n{visual_suggestion}\n"
                if visual_suggestion else ""
            )
            prompt = (
                "你是小红书卡片文案规划师。根据以下文案内容，规划 4 张小红书卡片（1080×1440 竖图）的文案。\n\n"
                "要求：\n"
                "1. 第 1 张是封面（cover）：吸引眼球的标题 + 副标题 + 署名\n"
                "2. 第 2 张是正文（content）：一个小标题 + 2-3 段正文（正文要完整，不要截断）\n"
                "3. 第 3 张是金句（quote）：一句戳中读者的话 + 出处\n"
                "4. 第 4 张是清单（list）：一个清单标题 + 3-5 个要点\n"
                f"{visual_hint}\n"
                "5. 模板选择：根据主题从以下 3 套中选最合适的一套：\n"
                "   - minimal_white：白底黑字红色点缀，适合知识干货、教育、科普\n"
                "   - warm_card：米黄底深棕字，适合美食、旅行、生活方式、穿搭\n"
                "   - dark_tech：深蓝底白字霓虹绿点缀，适合科技、AI、编程、数码\n"
                "6. 强调色（custom_accent）：根据主题推荐一个十六进制颜色值，用于卡片标题/序号/分割线等强调元素\n"
                "   - 知识干货可用 #FF2442（红）或 #065F46（绿）\n"
                "   - 美食旅行可用 #D97706（橙）或 #B45309（棕）\n"
                "   - 科技编程可用 #10B981（绿）或 #3B82F6（蓝）\n\n"
                "严格输出以下 JSON 格式（不要输出其他内容，不要 markdown 代码块）：\n"
                '{\n'
                '  "pages": [\n'
                '    {"type": "cover", "title": "封面标题", "subtitle": "副标题", "footer": "@灵犀工坊"},\n'
                '    {"type": "content", "title": "正文小标题", "content": "第一段正文\\n\\n第二段正文"},\n'
                '    {"type": "quote", "content": "金句内容", "footer": "— 出处"},\n'
                '    {"type": "list", "title": "清单标题", "listItems": ["要点1", "要点2", "要点3"]}\n'
                '  ],\n'
                '  "suggested_template": "minimal_white",\n'
                '  "custom_accent": "#FF2442"\n'
                '}\n\n'
                f"主题：{topic}\n"
                f"标题：{title}\n"
                f"正文：{content[:800]}\n"
                f"标签：{', '.join(tags) if isinstance(tags, list) else tags}\n"
                f"要点：{', '.join(key_points) if isinstance(key_points, list) and key_points else '无'}\n"
            )

            if llm is not None:
                try:
                    resp = await llm.chat(
                        messages=[{"role": "user", "content": prompt}],
                    )
                    raw = (resp.get("content") or "").strip()
                    # 去掉可能的 markdown 代码块标记
                    if raw.startswith("```"):
                        raw = raw.split("\n", 1)[-1]
                        if raw.endswith("```"):
                            raw = raw.rsplit("```", 1)[0]
                        raw = raw.strip()
                    parsed = _json.loads(raw)
                    if isinstance(parsed, dict) and isinstance(parsed.get("pages"), list):
                        card_draft = parsed
                        model_used = llm.model_name or "deepseek"
                        logger.info(
                            f"[{workflow_id}] {node_id} card_draft generated: "
                            f"{len(card_draft['pages'])} pages"
                        )
                    else:
                        raise ValueError("invalid card_draft structure")
                except Exception as e:
                    logger.warning(f"[{workflow_id}] {node_id} LLM card_draft failed: {e}, using fallback")
                    card_draft = _build_card_draft_fallback(topic, title, content, tags, key_points)
            else:
                logger.warning(f"[{workflow_id}] {node_id} LLM unavailable, using fallback card_draft")
                card_draft = _build_card_draft_fallback(topic, title, content, tags, key_points)
    except Exception as e:
        logger.exception(f"[{workflow_id}] {node_id} card_draft generation failed unexpectedly: {e}")
        card_draft = _build_card_draft_fallback(topic, title, content, tags, key_points)
        model_used = "fallback (exception)"

    # 根据推荐的模板和主题，推荐装饰层配置
    suggested_template_id = card_draft.get("suggested_template", "minimal_white")
    suggested_decoration = _recommend_decoration(
        template=suggested_template_id,
        topic=topic,
        content_type=analyze_content_type,
    )
    card_draft["suggested_decoration"] = suggested_decoration

    output = {
        "image_plan": {"plan": [], "skipped": True, "reason": "card_editor_mode"},
        "card_draft": card_draft,
        "copywrite_passthrough": {
            "title": title,
            "content": content,
            "tags": tags if isinstance(tags, list) else [],
            "key_points": key_points,
        },
        "_model_used": model_used,
        "_duration_ms": int((time.time() - start_time) * 1000),
        "_token_usage": 0,
        "_source": "card_editor_mode",
    }
    await emit_node_event(workflow_id, node_id, "node_completed", output)
    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }


def _recommend_template(topic: str, content_type: str = "") -> str:
    """根据内容类型推荐卡片模板，topic 关键词作兜底。

    优先级：content_type 映射 > topic 关键词 > 默认 minimal_white

    映射表（对齐 analyze 节点 _VALID_CONTENT_TYPES）：
    - 清单型 / 教程型 → minimal_white（白底清晰，重 readability）
    - 观点型 → dark_tech（深色有态度）
    - 对比型 / 叙事型 → warm_card（暖色亲和/温馨）
    """
    # 1. content_type 优先（analyze 节点已校验枚举，可信度高）
    _CONTENT_TYPE_MAP = {
        "清单型": "minimal_white",
        "教程型": "minimal_white",
        "观点型": "dark_tech",
        "对比型": "warm_card",
        "叙事型": "warm_card",
    }
    if content_type in _CONTENT_TYPE_MAP:
        return _CONTENT_TYPE_MAP[content_type]

    # 2. content_type 为空或未知时，用 topic 关键词兜底
    text = (topic or "").lower()
    warm_keywords = [
        "美食", "食谱", "早餐", "晚餐", "午餐", "旅行", "旅游", "生活方式",
        "家居", "穿搭", "美妆", "护肤", "日常", "生活", "咖啡", "烘焙",
        "探店", "节日", "宠物", "花艺",
    ]
    tech_keywords = [
        "科技", "ai", "编程", "代码", "数码", "互联网", "python",
        "javascript", "技术", "开发", "软件", "工具", "效率", "电脑",
        "手机", "算法", "数据", "机器学习", "前端", "后端",
    ]
    for kw in warm_keywords:
        if kw in text:
            return "warm_card"
    for kw in tech_keywords:
        if kw in text:
            return "dark_tech"

    # 3. 默认
    return "minimal_white"


def _recommend_decoration(
    template: str, topic: str = "", content_type: str = ""
) -> dict:
    """根据模板 + 内容类型推荐装饰层配置。

    返回结构化 dict，与前端 DecorationConfig 对齐。
    策略：
    - warm_card → gradient_orbs（暖光斑）/ noise（纸张纹理）
    - dark_tech → grid_lines（网格线）/ geometric（几何色块）
    - minimal_white → dots（波点）/ wave（波浪）/ noise（纸张纹理）
    - content_type 细分覆盖默认
    """
    text = (topic or "").lower()

    # content_type 细分
    if content_type in ("清单型", "教程型"):
        return {
            "type": "noise",
            "color1": "#92400E",
            "color2": "#78716C",
            "opacity": 0.06,
            "param1": 0.5,
            "param2": 1,
        }
    if content_type == "观点型":
        return {
            "type": "geometric",
            "color1": "#818CF8",
            "color2": "#F472B6",
            "opacity": 0.15,
            "param1": 0.6,
            "param2": -15,
        }
    if content_type in ("对比型", "叙事型"):
        return {
            "type": "gradient_orbs",
            "color1": "#FDE68A",
            "color2": "#FCA5A5",
            "opacity": 0.35,
            "param1": 0.25,
            "param2": 0.65,
        }

    # topic 关键词细分
    food_kw = ["美食", "食谱", "早餐", "晚餐", "午餐", "咖啡", "烘焙", "探店"]
    travel_kw = ["旅行", "旅游", "探店", "节日", "花艺"]
    tech_kw = [
        "科技", "ai", "编程", "代码", "数码", "python",
        "javascript", "技术", "开发", "算法", "数据", "机器学习",
    ]
    life_kw = ["生活方式", "家居", "穿搭", "美妆", "护肤", "日常", "生活", "宠物"]

    for kw in food_kw:
        if kw in text:
            return {
                "type": "gradient_orbs",
                "color1": "#FDE68A",
                "color2": "#FCA5A5",
                "opacity": 0.35,
                "param1": 0.25,
                "param2": 0.65,
            }
    for kw in travel_kw:
        if kw in text:
            return {
                "type": "wave",
                "color1": "#7DD3FC",
                "color2": "#BAE6FD",
                "opacity": 0.2,
                "param1": 3,
                "param2": 40,
            }
    for kw in tech_kw:
        if kw in text:
            return {
                "type": "grid_lines",
                "color1": "#94A3B8",
                "color2": "#475569",
                "opacity": 0.12,
                "param1": 80,
                "param2": 1,
            }
    for kw in life_kw:
        if kw in text:
            return {
                "type": "dots",
                "color1": "#F9A8D4",
                "color2": "#FDE68A",
                "opacity": 0.25,
                "param1": 48,
                "param2": 6,
            }

    # 按 template 兜底
    _TEMPLATE_DECO = {
        "warm_card": {
            "type": "gradient_orbs",
            "color1": "#FDE68A",
            "color2": "#FCA5A5",
            "opacity": 0.3,
            "param1": 0.25,
            "param2": 0.65,
        },
        "dark_tech": {
            "type": "grid_lines",
            "color1": "#94A3B8",
            "color2": "#475569",
            "opacity": 0.12,
            "param1": 80,
            "param2": 1,
        },
        "minimal_white": {
            "type": "noise",
            "color1": "#92400E",
            "color2": "#78716C",
            "opacity": 0.06,
            "param1": 0.5,
            "param2": 1,
        },
    }
    return _TEMPLATE_DECO.get(template, {"type": "none", "color1": "#FDE68A", "color2": "#FCA5A5", "opacity": 0.3})


def _build_card_draft_fallback(topic: str, title: str, content: str, tags, key_points) -> dict:
    """LLM 不可用时的 card_draft 兜底：用 copywrite 内容拼 4 张卡。"""
    # 把正文按换行分段，取前 2 段作为 content 卡
    paragraphs = [p.strip() for p in (content or "").split("\n") if p.strip()][:2]
    content_text = "\n\n".join(paragraphs) if paragraphs else "正文内容待补充"

    # key_points 作为 list 卡的来源
    if isinstance(key_points, list) and key_points:
        list_items = [str(k)[:100] for k in key_points[:5]]
    else:
        list_items = ["要点一", "要点二", "要点三"]

    return {
        "pages": [
            {
                "type": "cover",
                "title": title or "点击编辑标题",
                "subtitle": "副标题（可选）",
                "footer": "@灵犀工坊",
            },
            {
                "type": "content",
                "title": "核心观点",
                "content": content_text,
            },
            {
                "type": "quote",
                "content": "一句戳中读者的话，放在这里作为金句。",
                "footer": "— 灵犀工坊",
            },
            {
                "type": "list",
                "title": "要点清单",
                "listItems": list_items,
            },
        ],
        "suggested_template": _recommend_template(topic, ""),
    }


async def image_gen_node(state: WorkflowState) -> dict:
    """Image generation node: 接收前端卡片编辑器注入的图片，校验并打包到 image_review。

    工作机制：
    - image_plan 完成后，工作流在 image_gen 前 interrupt 暂停
    - 前端卡片编辑器加载 card_draft，用户调整后 html2canvas 出图
    - 前端调 inject-card-images 接口，把图片 base64 + plan_context 写入 state
    - inject 接口 resume 工作流，image_gen_node 执行
    - 本节点读取 image_plan 的规划 + inject 的图片 + plan_context
    - 校验图片数量、对比模板变更，打包完整上下文给下游

    红线：
    - 本节点不再主动渲染（不调 Playwright，不调通义万相）
    - 图片完全由前端卡片编辑器生成
    - 本节点做校验和打包，不做生成
    """
    import time

    workflow_id = state["workflow_id"]
    node_id = "image_gen"
    start_time = time.time()

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    # 读取 image_plan 的规划（建立显式数据依赖）
    plan_output = state.get("node_outputs", {}).get("image_plan", {}) or {}
    card_draft = plan_output.get("card_draft", {})
    original_template = card_draft.get("suggested_template", "")
    original_accent = card_draft.get("custom_accent", "")
    original_page_count = len(card_draft.get("pages", []))

    # 读取 inject 的图片 + plan_context
    image_gen_output = state.get("node_outputs", {}).get("image_gen", {}) or {}
    injected_images = image_gen_output.get("images_base64", [])
    plan_context = image_gen_output.get("plan_context", {}) or {}

    if injected_images:
        # 校验：图片数量是否和规划一致
        final_template = plan_context.get("template", "")
        final_accent = plan_context.get("accent", "")
        final_page_count = plan_context.get("page_count", 0)
        final_page_types = plan_context.get("page_types", [])
        actual_count = len(injected_images)
        count_match = (final_page_count == 0) or (actual_count == final_page_count)
        template_changed = bool(original_template and final_template and original_template != final_template)

        logger.info(
            f"[{workflow_id}] {node_id} received {actual_count} injected images, "
            f"template={final_template}, accent={final_accent}, "
            f"count_match={count_match}, template_changed={template_changed}"
        )

        output = {
            "images_base64": injected_images,
            "image_count": actual_count,
            "image_details": image_gen_output.get("image_details", []),
            "image_prompts": [],
            "style": image_gen_output.get("style", "卡片编辑器"),
            "is_candidate_mode": False,
            "is_blueprint_mode": False,
            "is_card_editor_mode": True,
            "plan_context": plan_context,
            "card_draft_summary": {
                "original_template": original_template,
                "final_template": final_template,
                "original_accent": original_accent,
                "final_accent": final_accent,
                "original_page_count": original_page_count,
                "final_page_count": final_page_count,
                "template_changed": template_changed,
                "page_types": final_page_types,
            },
            "validation": {
                "count_match": count_match,
                "expected_count": final_page_count or original_page_count,
                "actual_count": actual_count,
            },
            "_model_used": "card_editor_inject",
            "_duration_ms": int((time.time() - start_time) * 1000),
            "_token_usage": {"prompt": 0, "completion": 0, "total": 0},
            "_source": "card_editor_inject",
        }
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 100,
            "current_node": node_id,
            "message": f"卡片编辑器出图完成（{actual_count} 张）",
        })
        await emit_node_event(workflow_id, node_id, "node_completed", output)
        return {
            "current_node": node_id,
            "node_statuses": {node_id: NodeStatus.COMPLETED.value},
            "node_outputs": {node_id: output},
        }

    # 没有注入图片：报错（正常不应走到这里，因为 interrupt 在 image_gen 前）
    err_msg = "image_gen 未收到前端注入的图片，请确认卡片编辑器已生成图片"
    logger.error(f"[{workflow_id}] {node_id} {err_msg}")
    await sse_bus.publish(workflow_id, "workflow_error", {
        "workflow_id": workflow_id,
        "node_id": node_id,
        "error_type": "no_injected_images",
        "message": err_msg,
        "suggestion": "在工作区卡片编辑器中调整文案后，点击「生成图片」按钮",
    })
    output = {
        "images_base64": [],
        "image_count": 0,
        "image_details": [],
        "image_prompts": [],
        "style": "",
        "is_card_editor_mode": True,
        "_model_used": "card_editor_inject",
        "_error": err_msg,
        "_duration_ms": int((time.time() - start_time) * 1000),
        "_source": "no_injected_images",
    }
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "error"})
    await emit_node_event(workflow_id, node_id, "node_error", output)
    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.ERROR.value},
        "node_outputs": {node_id: output},
    }


async def image_review_node(state: WorkflowState) -> dict:
    """Image review node: 人工审核节点（通过/打回 blueprint 渲染结果）。

    工作机制：
    - interrupt_before=["image_review"] 让工作流在此节点前暂停
    - 用户通过 POST /api/workflows/{id}/review 提交审核结果
    - blueprint 模式：image_gen 已渲染 4 张卡，本节点只做通过/打回判定
    - 打回时回退到 image_gen（重新生成 blueprint 并渲染）

    路由：
    - passed → audit
    - rejected → image_gen（重新生成）
    """
    workflow_id = state["workflow_id"]
    node_id = "image_review"

    # 读取审核状态（submit_review reject 时通过 update_state 设为 rejected）
    review_status = state.get("node_statuses", {}).get(node_id, "pending")
    is_rejected = review_status == NodeStatus.REJECTED.value

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(
        f"[{workflow_id}] {node_id} resumed after human review "
        f"(status={review_status})"
    )

    # 读取 image_gen 输出（blueprint 模式下已含 images_base64）
    image_gen_output = state.get("node_outputs", {}).get("image_gen", {})
    images_base64 = image_gen_output.get("images_base64", [])
    image_details = image_gen_output.get("image_details", [])
    image_prompts = image_gen_output.get("image_prompts", [])
    style = image_gen_output.get("style", "")
    image_count = image_gen_output.get("image_count", len(images_base64))
    plan_context = image_gen_output.get("plan_context", {}) or {}
    card_draft_summary = image_gen_output.get("card_draft_summary", {}) or {}
    validation = image_gen_output.get("validation", {}) or {}

    _dlog(
        f"[{workflow_id}] {node_id} diagnose: "
        f"is_rejected={is_rejected}, "
        f"is_blueprint_mode={image_gen_output.get('is_blueprint_mode', False)}, "
        f"image_count={image_count}, "
        f"has_images_base64={bool(images_base64)}, "
        f"review_status={review_status}, "
        f"template={plan_context.get('template', '')}, "
        f"count_match={validation.get('count_match', 'N/A')}"
    )

    # 打包审核数据（供后续节点使用）
    review_data = {
        "image_count": image_count,
        "style": style,
        "image_details": image_details,
        "image_prompts": image_prompts,
        "prompt_source": image_gen_output.get("prompt_source", "blueprint"),
        "review_status": "rejected" if is_rejected else "passed",
        "feedback": "",
        "selected_indices": list(range(image_count)),  # 默认全部选中
        "is_blueprint_mode": image_gen_output.get("is_blueprint_mode", False),
        "blueprint": image_gen_output.get("blueprint"),
        "images_base64": images_base64,  # 透传渲染好的图片，供后续 publish 节点使用
        "plan_context": plan_context,     # 规划上下文：模板、强调色、页数、页类型
        "card_draft_summary": card_draft_summary,  # 规划对比：原始 vs 最终、是否改过模板
        "validation": validation,         # 校验结果：图片数量是否匹配
    }

    await emit_node_event(workflow_id, node_id, "node_completed", review_data)

    # rejected 时保持 rejected 状态，路由函数会走回退路径（→ image_gen）
    node_status = (
        NodeStatus.REJECTED.value if is_rejected else NodeStatus.PASSED.value
    )

    logger.info(
        f"[{workflow_id}] {node_id} "
        f"{'rejected (rollback to image_gen)' if is_rejected else 'passed'}: "
        f"image_count={image_count}, style={style[:40]}"
    )

    return {
        "current_node": node_id,
        "node_statuses": {node_id: node_status},
        "node_outputs": {node_id: review_data},
    }


async def copywrite_node(state: WorkflowState) -> dict:
    """Copywrite node: 基于分析洞察 + 图片描述生成小红书文案。

    流程：
    1. 从 analyze 节点取 insights（patterns, recommendations）
    2. 从 image_gen 节点取 image_details（图片描述）+ style
    3. 从 image_review 节点取审核反馈（如有）
    4. 用 LLM 生成 title + content + tags
    5. LLM 不可用时降级为模板生成

    成本控制：
    - 直接调 DeepSeek（不走完整 harness，减少抽象层开销）
    - max_tokens 由 DeepSeekAdapter 控制（默认 1500）
    - 单次调用约 0.012 元
    """
    import time

    workflow_id = state["workflow_id"]
    node_id = "copywrite"
    start_time = time.time()

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    topic = state.get("topic", "")

    # 用户在右侧工作区选择的模型/温度/文风配置
    model_settings = state.get("model_settings", {}) or {}
    user_temperature = model_settings.get("temperature")
    user_text_model = model_settings.get("text_model")
    user_writing_style = model_settings.get("writing_style", "")
    # 用户可直接指定 copywrite skill name（优先级高于 writing_style 中文名）
    copywrite_skill_name = model_settings.get("copywrite_skill")
    # 风格开关（来自右侧配置中心）：
    # - content_length: 用户期望的文案正文字数（100-500），覆盖 prompt 硬编码长度规则
    # - auto_emoji: False 时指示 LLM 不使用 emoji，覆盖风格 skill 默认
    # - auto_tags: False 时指示 LLM 不生成标签，返回空 tags 数组
    content_length = model_settings.get("content_length")
    auto_emoji = model_settings.get("auto_emoji", True)
    auto_tags = model_settings.get("auto_tags", True)

    # 选题池参考素材（从选题池"发起新工作流"时携带，注入 LLM prompt）
    reference = state.get("reference", {}) or {}

    # 用户级长期记忆（跨工作流，工作流启动时从 AgentMemory 加载）
    # 注入 LLM prompt 供 copywrite 参考历史选题/文案/偏好文风
    user_memory = state.get("user_memory", {}) or {}

    # ===== Step 1: 收集上游数据 =====
    node_outputs = state.get("node_outputs", {})
    analyze_output = node_outputs.get("analyze", {})
    # 修 bug：patterns 是 analyze_output 的顶层字段，不在 insights 里
    # 之前只取 insights 导致 Layer2 的标题钩子/内容结构/情绪触发点完全丢失
    patterns = analyze_output.get("patterns", {}) or {}
    insights = analyze_output.get("insights", {}) or {}

    # 提取 execution_brief：analyze Layer3 给下游的执行指令
    # 从 recommendations[0].execution_brief 取（取首条推荐方向的指令）
    execution_brief = {}
    recommendations = insights.get("recommendations") or []
    if recommendations and isinstance(recommendations[0], dict):
        brief = recommendations[0].get("execution_brief")
        if isinstance(brief, dict):
            execution_brief = brief

    image_gen_output = node_outputs.get("image_gen", {})
    image_details = image_gen_output.get("image_details", [])
    image_style = image_gen_output.get("style", "")

    image_review_output = node_outputs.get("image_review", {})
    review_feedback = image_review_output.get("feedback", "")

    logger.info(
        f"[{workflow_id}] {node_id} upstream: "
        f"patterns={'yes' if patterns else 'no'}, "
        f"insights={'yes' if insights else 'no'}, "
        f"execution_brief={'yes' if execution_brief else 'no'}, "
        f"image_details={len(image_details)}, "
        f"review_feedback={'yes' if review_feedback else 'no'}, "
        f"writing_style={user_writing_style or '(default)'}, "
        f"temperature={user_temperature if user_temperature is not None else '(default)'}, "
        f"reference={'yes' if reference else 'no'}"
    )

    # ===== Step 2: 调 LLM 生成文案 =====
    await emit_node_event(workflow_id, node_id, "progress_update", {
        "progress": 30,
        "step": "copywriting",
        "message": "LLM 生成小红书文案中...",
    })

    from app.agents.harnesses.factory import get_deepseek_llm
    from app.agents.skills.registry import get_skill_class
    # 触发内置 Skill 注册（import 即注册）
    import app.agents.skills.copywrite_builder  # noqa: F401
    from app.agents.skills.copywrite_builder import (
        CopywriteSkillBase,
        LivelyGirlCopywriteSkill,
        _WRITING_STYLE_TO_SKILL_NAME,
    )

    # 使用用户配置的温度+模型生成文案
    llm = get_deepseek_llm(temperature=user_temperature, model=user_text_model)

    # 通过 registry 加载 copywrite Skill（支持第三方插件）
    # 优先用 copywrite_skill，其次用 writing_style 中文名映射，最后用默认 lively_girl
    if not copywrite_skill_name and user_writing_style:
        copywrite_skill_name = _WRITING_STYLE_TO_SKILL_NAME.get(
            user_writing_style.strip(), "lively_girl"
        )
    copywrite_skill_cls = get_skill_class(
        "copywrite", copywrite_skill_name or "lively_girl"
    )
    if copywrite_skill_cls is None:
        logger.warning(
            f"[{workflow_id}] copywrite skill '{copywrite_skill_name}' not found, "
            f"falling back to LivelyGirlCopywriteSkill"
        )
        copywrite_skill_cls = LivelyGirlCopywriteSkill
    copywrite_skill = copywrite_skill_cls()
    logger.info(
        f"[{workflow_id}] copywrite using skill: {copywrite_skill.name} "
        f"({copywrite_skill.__class__.__name__})"
    )

    # 检测 DeepSeek 余额不足
    try:
        result = await copywrite_skill.execute({
            "llm": llm,
            "topic": topic,
            "insights": insights,
            "patterns": patterns,
            "execution_brief": execution_brief,
            "image_details": image_details,
            "image_style": image_style,
            "reference": reference,
            "user_memory": user_memory,
            "content_length": content_length,
            "auto_emoji": auto_emoji,
            "auto_tags": auto_tags,
        })
    except Exception as e:
        err_str = str(e)
        logger.exception(f"[{workflow_id}] {node_id} copywrite failed: {e}")

        # 检测 DeepSeek 余额不足（402）→ 推送前端通知
        if "402" in err_str or "Insufficient Balance" in err_str or "余额" in err_str:
            await sse_bus.publish(workflow_id, "model_arrearage", {
                "workflow_id": workflow_id,
                "node_id": node_id,
                "provider": "deepseek",
                "message": "DeepSeek 余额不足，文案生成降级为模板模式",
                "action_url": "https://platform.deepseek.com/usage",
                "action_text": "前往 DeepSeek 控制台充值",
            })

        # 降级为模板生成
        result = copywrite_skill.fallback(topic, insights, image_details)

    # ===== Step 3: 组装输出 =====
    output = {
        "title": result.get("title", ""),
        "content": result.get("content", ""),
        "tags": result.get("tags", []),
        "prompt_source": result.get("_source", "unknown"),
        "_model_used": "deepseek-chat" if llm else "none (fallback)",
        "_duration_ms": int((time.time() - start_time) * 1000),
        "_token_usage": {"prompt": 0, "completion": 0, "total": 0},
    }

    # 如果有审核反馈，附加到输出供前端展示
    if review_feedback:
        output["review_feedback"] = review_feedback

    elapsed = int((time.time() - start_time) * 1000)
    logger.info(
        f"[{workflow_id}] {node_id} completed: "
        f"source={output['prompt_source']}, "
        f"title={output['title'][:30]}, "
        f"content_len={len(output['content'])}, "
        f"tags={len(output['tags'])}, "
        f"elapsed={elapsed}ms"
    )

    await emit_node_event(workflow_id, node_id, "node_completed", output)

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }


async def audit_node(state: WorkflowState) -> dict:
    """Audit node: 用 LLM 审核文案合规性。

    审核维度：合规性、平台规则、内容质量、品牌安全。
    LLM 不可用时自动通过（不阻塞工作流）。

    可插拔：通过 SkillRegistry 加载 audit 节点的 Skill 子类，
    第三方可在 backend/skills/ 下注册自己的 AuditSkillBase 子类。

    成本控制：max_tokens 由 DeepSeekAdapter 控制（默认 1500）。
    """
    import time

    workflow_id = state["workflow_id"]
    node_id = "audit"
    start_time = time.time()

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    topic = state.get("topic", "")
    copywrite_output = state.get("node_outputs", {}).get("copywrite", {})

    # 用户在右侧工作区选择的 audit skill 配置
    model_settings = state.get("model_settings", {}) or {}
    audit_skill_name = model_settings.get("audit_skill") or "standard"

    # 通过 registry 加载 audit Skill（支持第三方插件）
    from app.agents.skills.registry import get_skill_class
    # 触发内置 Skill 注册（import 即注册）
    import app.agents.skills.audit_skill  # noqa: F401
    from app.agents.skills.audit_skill import StandardAuditSkill

    audit_skill_cls = get_skill_class("audit", audit_skill_name)
    if audit_skill_cls is None:
        logger.warning(
            f"[{workflow_id}] audit skill '{audit_skill_name}' not found, "
            f"falling back to StandardAuditSkill"
        )
        audit_skill_cls = StandardAuditSkill
    audit_skill = audit_skill_cls()
    logger.info(
        f"[{workflow_id}] audit using skill: {audit_skill.name} "
        f"({audit_skill.__class__.__name__})"
    )

    # audit 节点使用默认温度（审核需要稳定输出，不强行使用用户配置）
    from app.agents.harnesses.factory import get_deepseek_llm
    llm = get_deepseek_llm()

    await emit_node_event(workflow_id, node_id, "tool_call_start", {
        "tool": "audit_skill",
        "skill": audit_skill.name,
    })

    try:
        audit_result = await audit_skill.execute({
            "llm": llm,
            "topic": topic,
            "copywrite": copywrite_output,
        })
        output = {
            "passed": audit_result.get("passed", True),
            "issues": audit_result.get("issues", []),
            "suggestions": audit_result.get("suggestions", []),
            "audit_method": audit_result.get("audit_method", "unknown"),
            "_skill": audit_skill.name,
            "_model_used": "deepseek-chat" if llm is not None else "none",
            "_duration_ms": int((time.time() - start_time) * 1000),
        }
        await emit_node_event(workflow_id, node_id, "tool_call_end", {
            "tool": "audit_skill",
            "success": True,
            "passed": output["passed"],
        })
        logger.info(
            f"[{workflow_id}] {node_id} completed: passed={output['passed']}, "
            f"issues={len(output['issues'])}, skill={audit_skill.name}"
        )
    except Exception as e:
        logger.exception(f"[{workflow_id}] {node_id} audit skill failed: {e}")
        await emit_node_event(workflow_id, node_id, "tool_call_end", {
            "tool": "audit_skill",
            "success": False,
            "error": str(e),
        })
        output = {
            "passed": True,
            "issues": [],
            "suggestions": [],
            "audit_method": "fallback",
            "_skill": audit_skill.name,
            "_model_used": "none (fallback)",
            "_error": str(e),
            "_duration_ms": int((time.time() - start_time) * 1000),
        }

    await emit_node_event(workflow_id, node_id, "node_completed", output)

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }


async def final_review_node(state: WorkflowState) -> dict:
    """Final review node: 人工审核节点（通过或打回）。

    工作机制：
    - interrupt_before=["final_review"] 让工作流在此节点前暂停
    - 用户通过 POST /api/workflows/{id}/review 提交最终审核结果
    - 审核通过 → submit_review resume，节点读到 status=pending（默认），设为 passed
    - 审核打回 → submit_review 通过 update_state 设 status=rejected，节点读到后保持 rejected
    - 路由函数 route_after_final_review 根据 status 决定下一步：
      passed → publish，rejected → copywrite（重新生成文案）
    """
    workflow_id = state["workflow_id"]
    node_id = "final_review"

    # 读取审核状态（submit_review reject 时通过 update_state 设为 rejected）
    review_status = state.get("node_statuses", {}).get(node_id, "pending")
    is_rejected = review_status == NodeStatus.REJECTED.value

    _dlog(f"[{workflow_id}] ===== final_review_node ENTERED ===== review_status={review_status}, is_rejected={is_rejected}")

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(
        f"[{workflow_id}] {node_id} resumed after human review "
        f"(status={review_status})"
    )

    # 读取 copywrite 输出，透传给 publish
    copywrite_output = state.get("node_outputs", {}).get("copywrite", {})
    image_gen_output = state.get("node_outputs", {}).get("image_gen", {})
    image_review_output = state.get("node_outputs", {}).get("image_review", {})

    # 候选模式下完整套装在 image_review.images_base64，旧模式在 image_gen.images_base64
    final_images = (
        image_review_output.get("images_base64")
        or image_gen_output.get("images_base64")
        or []
    )

    review_data = {
        "title": copywrite_output.get("title", ""),
        "content": copywrite_output.get("content", ""),
        "tags": copywrite_output.get("tags", []),
        "images_base64": final_images,
        "review_status": "rejected" if is_rejected else "passed",
        "feedback": "",
    }

    await emit_node_event(workflow_id, node_id, "node_completed", review_data)

    # rejected 时保持 rejected 状态，路由函数会走回退路径（→ copywrite）
    node_status = (
        NodeStatus.REJECTED.value if is_rejected else NodeStatus.PASSED.value
    )

    logger.info(
        f"[{workflow_id}] {node_id} "
        f"{'rejected (rollback to copywrite)' if is_rejected else 'passed'}: "
        f"title={review_data['title'][:30]}"
    )

    return {
        "current_node": node_id,
        "node_statuses": {node_id: node_status},
        "node_outputs": {node_id: review_data},
    }


async def publish_node(state: WorkflowState) -> dict:
    """Publish node: LoopExecutor + XhsPublishSkill via MCP."""
    workflow_id = state["workflow_id"]
    node_id = "publish"

    _dlog(f"[{workflow_id}] ===== publish_node ENTERED =====")
    _dlog(f"[{workflow_id}] publish_node state keys: {list(state.keys())}")
    _dlog(f"[{workflow_id}] publish_node node_statuses: {state.get('node_statuses', {})}")
    _dlog(f"[{workflow_id}] publish_node node_outputs keys: {list(state.get('node_outputs', {}).keys())}")

    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                           {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} started")

    # 从 upstream 节点产物里取要发布的字段
    final_review = state.get("node_outputs", {}).get("final_review", {})
    copywrite = state.get("node_outputs", {}).get("copywrite", {})
    image_gen = state.get("node_outputs", {}).get("image_gen", {})
    image_review = state.get("node_outputs", {}).get("image_review", {})
    harness_input = {
        "title": final_review.get("title") or copywrite.get("title", ""),
        "content": final_review.get("content") or copywrite.get("content", ""),
        # 候选模式下 image_gen.images_base64 为空，完整套装在 image_review.images_base64
        "images_base64": (
            final_review.get("images_base64")
            or image_review.get("images_base64")
            or image_gen.get("images_base64")
            or []
        ),
        "account_id": state.get("account_id", ""),
    }

    _dlog(f"[{workflow_id}] publish_node harness_input: title={harness_input['title'][:30]!r}, "
          f"content_len={len(harness_input['content'])}, images={len(harness_input['images_base64'])}")

    # 参数校验：title 和 content 不能为空
    if not harness_input["title"] or not harness_input["content"]:
        logger.warning(
            f"[{workflow_id}] {node_id} missing title or content, skip publish"
        )
        _dlog(f"[{workflow_id}] publish_node SKIP: missing title or content")
        output = {
            "post_id": "",
            "status": "failed",
            "message": "发布失败：缺少标题或正文（请检查 copywrite / final_review 节点输出）",
        }
    else:
        # 发布进度提示：发布流程涉及 Playwright 操作发布页，耗时 15-30s
        img_count = len(harness_input["images_base64"])
        await emit_node_event(workflow_id, node_id, "progress_update", {
            "progress": 10,
            "step": "publish_starting",
            "message": f"正在连接小红书发布页（{img_count} 张图片）...",
        })

        # 直接调用 XhsPublishSkill，不走 LLM Loop
        # 红线：发布是确定性动作（调 MCP → Worker Playwright），不需要 LLM 推理
        # LLM Loop 会导致 LLM 误判参数为占位符，拒绝调用工具
        from app.agents.skills.xhs_publish import XhsPublishSkill

        skill = XhsPublishSkill()
        _dlog(f"[{workflow_id}] publish_node calling XhsPublishSkill.execute()...")
        try:
            output = await skill.execute(harness_input)
            _dlog(f"[{workflow_id}] publish_node skill result: status={output.get('status')}, "
                  f"message={output.get('message', '')[:100]}")
        except Exception as e:
            logger.exception(f"[{workflow_id}] {node_id} publish skill failed: {e}")
            _dlog(f"[{workflow_id}] publish_node skill EXCEPTION: {type(e).__name__}: {e}")
            await emit_node_event(workflow_id, node_id, "node_error",
                                  {"error": str(e), "error_type": type(e).__name__})
            output = {
                "post_id": "",
                "status": "failed",
                "message": f"发布异常: {e}",
            }

    _dlog(f"[{workflow_id}] publish_node FINAL output: {output}")
    await emit_node_event(workflow_id, node_id, "node_completed", output)

    # 发布成功时记录用户级长期记忆（publish_history）
    # 失败不阻塞工作流，仅记日志
    if output.get("status") == "success" or output.get("post_id"):
        try:
            from app.services import agent_memory
            await agent_memory.record_publish(
                user_id=state.get("user_id", ""),
                workflow_id=workflow_id,
                topic=state.get("topic", ""),
                title=harness_input.get("title", ""),
                post_id=str(output.get("post_id", "")),
            )
        except Exception as mem_err:
            logger.warning(
                f"[{workflow_id}] record_publish failed: {mem_err}"
            )

    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }


# ---------------------------------------------------------------------------
# Quality Check Nodes (D14 distributed guards, soft semantic Layer2)
# ---------------------------------------------------------------------------


_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def _load_prompt(name: str) -> str:
    """加载 prompts 目录下的 md 模板。文件不存在时返回空串。"""
    p = _PROMPTS_DIR / name
    if not p.exists():
        logger.warning(f"prompt file not found: {p}")
        return ""
    return p.read_text(encoding="utf-8")


# 预加载 3 个软语义 prompt（模块级缓存，避免每次节点调用都读盘）
_QUALITY_CHECK_ANALYZE_PROMPT = _load_prompt("quality_check_analyze.md")
_QUALITY_CHECK_COPYWRITE_PROMPT = _load_prompt("quality_check_copywrite.md")
_QUALITY_CHECK_AUDIT_PROMPT = _load_prompt("quality_check_audit.md")


async def _run_soft_semantic_check(
    workflow_id: str,
    check_type: str,
    upstream_node: str,
    upstream_output: dict,
    topic: str,
    prompt_template: str,
) -> dict:
    """软语义判断统一入口（Layer2）。

    红线：
    - 只判质量，不做路由决策（路由由 conditional_edges 硬编码）
    - 不命令 Agent 重跑（建议权，用户拍板）
    - LLM 不可用或调用异常时默认放行（不阻塞工作流）

    Returns:
        {"quality_pass": bool, "reason": str, "suggestions": list[str], "severity": str}
    """
    from app.agents.harnesses.factory import get_deepseek_llm

    node_id = f"quality_check_{check_type}"
    await emit_node_event(workflow_id, node_id, "node_started")
    await emit_node_event(workflow_id, node_id, "node_status_changed",
                          {"status": "running"})

    logger.info(f"[{workflow_id}] {node_id} soft semantic check started")

    llm = get_deepseek_llm()
    if llm is None:
        logger.warning(
            f"[{workflow_id}] {node_id} LLM unavailable, auto-pass"
        )
        result: dict = {
            "quality_pass": True,
            "reason": "LLM 未配置，自动放行",
            "suggestions": [],
            "severity": "low",
        }
    elif not prompt_template:
        logger.warning(
            f"[{workflow_id}] {node_id} prompt template empty, auto-pass"
        )
        result = {
            "quality_pass": True,
            "reason": "软语义 prompt 未加载，自动放行",
            "suggestions": [],
            "severity": "low",
        }
    else:
        # 渲染 prompt：upstream_output 截断防止 token 超限
        upstream_str = json.dumps(
            upstream_output, ensure_ascii=False, default=str
        )[:3000]
        try:
            prompt = prompt_template.format(
                topic=topic,
                upstream_output=upstream_str,
            )
        except (KeyError, IndexError):
            prompt = prompt_template

        try:
            resp = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            content = (resp.get("content") or "").strip()
            # 容忍 markdown fence
            if content.startswith("```"):
                lines = content.splitlines()
                if lines and lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
            parsed = json.loads(content)
            result = {
                "quality_pass": bool(parsed.get("quality_pass", True)),
                "reason": str(parsed.get("reason", "")),
                "suggestions": list(parsed.get("suggestions", [])),
                "severity": str(parsed.get("severity", "low")),
            }
        except Exception as e:
            logger.warning(
                f"[{workflow_id}] {node_id} LLM call failed: {e}, auto-pass"
            )
            result = {
                "quality_pass": True,
                "reason": f"软语义判断异常: {e}",
                "suggestions": [],
                "severity": "low",
            }

    # 推送 quality_check_result 事件（前端执行详情面板展示）
    await sse_bus.publish(
        workflow_id,
        "quality_check_result",
        {
            "node_id": node_id,
            "upstream_node": upstream_node,
            **result,
        },
    )
    await emit_node_event(workflow_id, node_id, "node_completed", result)

    return result


def _build_pending_suggestion(
    check_type: str,
    target_node: str,
    result: dict,
) -> dict:
    """根据软语义失败结果构造 pending_suggestion 数据（待 WorkflowService 写 DB）。"""
    return {
        "suggestion_type": "structural",
        "target_node": target_node,
        "severity": result.get("severity", "medium"),
        "message": result.get("reason", "软语义判断未通过"),
        "suggestions": result.get("suggestions", []),
        "source_node": f"quality_check_{check_type}",
    }


async def analyze_quality_check_node(state: WorkflowState) -> dict:
    """软语义: analyze 后置判断（爆款因子是否符合主题调性）。"""
    workflow_id = state["workflow_id"]
    analyze_output = state.get("node_outputs", {}).get("analyze", {})

    result = await _run_soft_semantic_check(
        workflow_id=workflow_id,
        check_type="analyze",
        upstream_node="analyze",
        upstream_output=analyze_output,
        topic=state.get("topic", ""),
        prompt_template=_QUALITY_CHECK_ANALYZE_PROMPT,
    )

    node_outputs = {"quality_check_analyze": result}
    existing_suggestions = list(state.get("pending_suggestions", []))
    new_suggestions: list[dict] = []

    if not result.get("quality_pass", True):
        suggestion = _build_pending_suggestion("analyze", "analyze", result)
        # 推送 supervisor_suggestion 事件（前端弹确认框）
        await sse_bus.publish(
            workflow_id,
            "supervisor_suggestion",
            {
                "workflow_id": workflow_id,
                "node_id": "quality_check_analyze",
                **suggestion,
                "require_user_confirm": True,
            },
        )
        new_suggestions = [suggestion]

    return {
        "node_outputs": node_outputs,
        "pending_suggestions": existing_suggestions + new_suggestions,
    }


async def copywrite_quality_check_node(state: WorkflowState) -> dict:
    """软语义: copywrite 后置判断（文案是否空洞/调性不符/字数不达标）。"""
    workflow_id = state["workflow_id"]
    copywrite_output = state.get("node_outputs", {}).get("copywrite", {})

    result = await _run_soft_semantic_check(
        workflow_id=workflow_id,
        check_type="copywrite",
        upstream_node="copywrite",
        upstream_output=copywrite_output,
        topic=state.get("topic", ""),
        prompt_template=_QUALITY_CHECK_COPYWRITE_PROMPT,
    )

    node_outputs = {"quality_check_copywrite": result}
    existing_suggestions = list(state.get("pending_suggestions", []))
    new_suggestions: list[dict] = []

    if not result.get("quality_pass", True):
        suggestion = _build_pending_suggestion("copywrite", "copywrite", result)
        await sse_bus.publish(
            workflow_id,
            "supervisor_suggestion",
            {
                "workflow_id": workflow_id,
                "node_id": "quality_check_copywrite",
                **suggestion,
                "require_user_confirm": True,
            },
        )
        new_suggestions = [suggestion]

    return {
        "node_outputs": node_outputs,
        "pending_suggestions": existing_suggestions + new_suggestions,
    }


async def audit_quality_check_node(state: WorkflowState) -> dict:
    """软语义: audit 后置判断（审核是否到位，双重保险）。"""
    workflow_id = state["workflow_id"]
    audit_output = state.get("node_outputs", {}).get("audit", {})

    result = await _run_soft_semantic_check(
        workflow_id=workflow_id,
        check_type="audit",
        upstream_node="audit",
        upstream_output=audit_output,
        topic=state.get("topic", ""),
        prompt_template=_QUALITY_CHECK_AUDIT_PROMPT,
    )

    node_outputs = {"quality_check_audit": result}
    existing_suggestions = list(state.get("pending_suggestions", []))
    new_suggestions: list[dict] = []

    if not result.get("quality_pass", True):
        suggestion = _build_pending_suggestion("audit", "copywrite", result)
        await sse_bus.publish(
            workflow_id,
            "supervisor_suggestion",
            {
                "workflow_id": workflow_id,
                "node_id": "quality_check_audit",
                **suggestion,
                "require_user_confirm": True,
            },
        )
        new_suggestions = [suggestion]

    return {
        "node_outputs": node_outputs,
        "pending_suggestions": existing_suggestions + new_suggestions,
    }


# ---------------------------------------------------------------------------
# Routing Functions (hardcoded, no LLM)
# ---------------------------------------------------------------------------


def route_after_search(state: WorkflowState) -> str:
    """Route after search: success -> analyze, error/empty -> END.

    关键节点失败终止：search 空结果或异常时直接结束工作流，
    避免后续 analyze/image_gen 节点白跑浪费 LLM + 图片 token。
    """
    search_status = state.get("node_statuses", {}).get("search", "pending")
    if search_status == NodeStatus.ERROR.value:
        return "end"
    return "analyze"


def route_after_image_gen(state: WorkflowState) -> str:
    """Route after image_gen: success -> image_review, error -> END.

    图片生成全失败（欠费/认证失败/限流耗尽）时终止工作流，
    避免后续 image_review/copywrite 节点白跑。
    """
    ig_status = state.get("node_statuses", {}).get("image_gen", "pending")
    if ig_status == NodeStatus.ERROR.value:
        return "end"
    return "image_review"


def route_after_analyze(state: WorkflowState) -> str:
    """Route after quality_check_analyze: 始终继续到 copywrite。

    工作流顺序调整（v2）：copywrite 移到 image_gen 之前，
    让图片生成/卡片渲染能基于最终文案执行，而非选题方向。

    MVP 阶段：quality_check 仅作为建议权，不影响路由。
    """
    return "copywrite"


def route_after_copywrite(state: WorkflowState) -> str:
    """Route after quality_check_copywrite: 始终继续到 image_plan。

    工作流顺序（v3）：copywrite → image_plan → image_gen → image_review
    image_plan 先规划图片类型和模板数据，image_gen 根据规划渲染。

    MVP 阶段：quality_check 仅作为建议权，不影响路由。
    """
    return "image_plan"


def route_after_image_review(state: WorkflowState) -> str:
    """Route after image review: pass -> audit, reject -> image_gen.

    工作流顺序调整（v2）：图片审核通过后进入 audit（而非 copywrite），
    因为 copywrite 已经在 image_gen 之前执行完了。
    """
    review_status = state.get("node_statuses", {}).get("image_review", "pending")
    if review_status == NodeStatus.PASSED.value:
        return "audit"
    return "image_gen"


def route_after_final_review(state: WorkflowState) -> str:
    """Route after final review: pass -> publish, reject -> rollback."""
    review_status = state.get("node_statuses", {}).get("final_review", "pending")
    wf = state.get("workflow_id", "?")
    if review_status == NodeStatus.PASSED.value:
        _dlog(f"[{wf}] route_after_final_review: status={review_status} -> 'publish'")
        return "publish"
    _dlog(f"[{wf}] route_after_final_review: status={review_status} -> 'rollback'")
    return "rollback"


def route_after_audit(state: WorkflowState) -> str:
    """Route after quality_check_audit: 始终继续到 final_review。

    MVP 阶段：quality_check 仅作为建议权，不影响路由。
    软语义 fail 的 suggestion 会写入 DB 并推送给前端，
    用户在 final_review 审核时可参考 suggestion 决定是否通过。
    """
    return "final_review"


async def rollback_to_node(state: WorkflowState, target_node: str) -> dict:
    """Rollback to target node."""
    workflow_id = state["workflow_id"]
    logger.info(f"[{workflow_id}] Rolling back to {target_node}")
    
    # Reset target node and downstream nodes to pending
    # 工作流顺序（v3）：search → analyze → copywrite → image_plan → image_gen → image_review → audit → final_review → publish
    node_order = ["search", "analyze", "copywrite", "image_plan", "image_gen", "image_review", "audit", "final_review", "publish"]
    target_idx = node_order.index(target_node)
    
    new_statuses = {}
    for i, node in enumerate(node_order):
        if i >= target_idx:
            new_statuses[node] = NodeStatus.PENDING.value
    
    return {"node_statuses": new_statuses}


# ---------------------------------------------------------------------------
# Graph Builder (optional, requires LangGraph)
# ---------------------------------------------------------------------------


def build_workflow_graph(checkpointer=None):
    """Build the workflow graph with all nodes and edges.
    
    Returns None if LangGraph is not available.
    """
    if not LANGGRAPH_AVAILABLE:
        logger.warning("LangGraph not available, graph building disabled")
        return None
    
    graph = StateGraph(WorkflowState)

    # Add nodes
    graph.add_node("search", search_node)
    graph.add_node("analyze", analyze_node)
    graph.add_node("quality_check_analyze", analyze_quality_check_node)
    graph.add_node("image_plan", image_plan_node)
    graph.add_node("image_gen", image_gen_node)
    graph.add_node("image_review", image_review_node)
    graph.add_node("copywrite", copywrite_node)
    graph.add_node("quality_check_copywrite", copywrite_quality_check_node)
    graph.add_node("audit", audit_node)
    graph.add_node("quality_check_audit", audit_quality_check_node)
    graph.add_node("final_review", final_review_node)
    graph.add_node("publish", publish_node)

    # Set entry point
    graph.set_entry_point("search")

    # Add edges (hardcoded routing)
    # search 失败（空结果/异常）→ END，避免后续节点白跑
    graph.add_conditional_edges(
        "search",
        route_after_search,
        {"analyze": "analyze", "end": END},
    )
    graph.add_edge("analyze", "quality_check_analyze")
    # 工作流顺序调整（v2）：analyze → copywrite → image_gen → image_review → audit
    # 让图片生成/卡片渲染基于最终文案，而非选题方向
    graph.add_conditional_edges(
        "quality_check_analyze",
        route_after_analyze,
        {"copywrite": "copywrite", "suspend": END},
    )
    graph.add_edge("copywrite", "quality_check_copywrite")
    graph.add_conditional_edges(
        "quality_check_copywrite",
        route_after_copywrite,
        {"image_plan": "image_plan", "suspend": END},
    )
    # 第一期新增：image_plan 先规划图片类型+模板数据，再交给 image_gen 渲染
    graph.add_edge("image_plan", "image_gen")
    # image_gen 失败（欠费/认证/限流）→ END，避免后续 image_review/audit 白跑
    graph.add_conditional_edges(
        "image_gen",
        route_after_image_gen,
        {"image_review": "image_review", "end": END},
    )
    # 图片审核通过 → audit；拒绝 → 重做 image_gen
    graph.add_conditional_edges(
        "image_review",
        route_after_image_review,
        {"audit": "audit", "image_gen": "image_gen"},
    )
    graph.add_edge("audit", "quality_check_audit")
    graph.add_conditional_edges(
        "quality_check_audit",
        route_after_audit,
        {"final_review": "final_review", "suspend": END},
    )
    graph.add_conditional_edges(
        "final_review",
        route_after_final_review,
        {"publish": "publish", "rollback": "copywrite"},
    )
    graph.add_edge("publish", END)

    # Compile：使用 interrupt_before 在审核节点前暂停，等待人工审核
    # - 必须提供 checkpointer（SqliteSaver 单例），否则 interrupt 后无法 resume
    # - image_gen 前 interrupt：前端卡片编辑器出图后注入（html2canvas → inject 接口 → resume）
    # - image_review 前 interrupt：用户审核图片
    # - final_review 前 interrupt：用户审核最终文案
    # resume 机制：调用方使用相同 thread_id 调 graph.astream(None, config)
    if checkpointer is None:
        checkpointer = get_global_checkpointer()

    compile_kwargs: dict = {
        "interrupt_before": ["image_gen", "image_review", "final_review", "publish"],
        # publish 前 interrupt：auto_publish=True 时自动 resume（用户无感），
        # auto_publish=False 时等待用户手动点击"发布"按钮（resume_workflow resume）
        "checkpointer": checkpointer,
    }

    return graph.compile(**compile_kwargs)