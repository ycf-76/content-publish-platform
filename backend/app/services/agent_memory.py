"""用户级智能体记忆服务。

跨工作流的长期记忆持久化与注入：
- load_for_workflow(user_id)：工作流启动时加载，返回精简 dict 供注入 state
- record_workflow_result(...)：工作流完成时记录 topic_history + copywrite_history
- record_publish(...)：发布成功时记录 publish_history
- update_preferences(user_id, key, value)：用户显式设置偏好

记忆注入策略（控制 token 成本）：
- 偏好文风：返回最近最常选择的文风名称（如"活泼少女"）
- 偏好主题：返回偏好/避免的主题类别列表
- 历史选题：返回最近 N 条 topic 字符串列表
- 历史文案：返回最近 3 条文案的 title 摘要

红线：
- 记录用规则统计（不调 LLM，避免 token 消耗）
- 注入用精简摘要（不塞完整内容，控制 prompt 长度）
- 工作流推断的偏好可被用户显式设置覆盖
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentMemory, MemoryType
from app.db.session import AsyncSessionLocal, is_mysql, is_sqlite

logger = logging.getLogger(__name__)

# 历史记录保留上限（避免无限增长）
_MAX_TOPIC_HISTORY = 50
_MAX_COPYWRITE_HISTORY = 20
_MAX_PUBLISH_HISTORY = 50
# 注入 prompt 的历史条数（控制 token）
_INJECT_TOPIC_LIMIT = 10
_INJECT_COPYWRITE_LIMIT = 3


def _upsert_stmt(memory: AgentMemory) -> Any:
    """构造 upsert 语句（MySQL / SQLite 兼容）。

    同一 (user_id, memory_type, memory_key) 存在则更新 memory_value / source / updated_at。
    """
    values = {
        "user_id": memory.user_id,
        "memory_type": memory.memory_type,
        "memory_key": memory.memory_key,
        "memory_value": memory.memory_value,
        "source": memory.source,
        "workflow_id": memory.workflow_id,
        "importance": memory.importance,
        "updated_at": datetime.now(UTC),
    }
    if is_mysql:
        stmt = mysql_insert(AgentMemory).values(**values)
        return stmt.on_duplicate_key_update(
            memory_value=stmt.inserted.memory_value,
            source=stmt.inserted.source,
            workflow_id=stmt.inserted.workflow_id,
            importance=stmt.inserted.importance,
            updated_at=stmt.inserted.updated_at,
        )
    if is_sqlite:
        stmt = sqlite_insert(AgentMemory).values(**values)
        return stmt.on_conflict_do_update(
            index_elements=[AgentMemory.user_id, AgentMemory.memory_type, AgentMemory.memory_key],
            set_={
                "memory_value": stmt.excluded.memory_value,
                "source": stmt.excluded.source,
                "workflow_id": stmt.excluded.workflow_id,
                "importance": stmt.excluded.importance,
                "updated_at": stmt.excluded.updated_at,
            },
        )
    # PostgreSQL（fallback，非主路径）
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    stmt = pg_insert(AgentMemory).values(**values)
    return stmt.on_conflict_do_update(
        index_elements=[AgentMemory.user_id, AgentMemory.memory_type, AgentMemory.memory_key],
        set_={
            "memory_value": stmt.excluded.memory_value,
            "source": stmt.excluded.source,
            "workflow_id": stmt.excluded.workflow_id,
            "importance": stmt.excluded.importance,
            "updated_at": stmt.excluded.updated_at,
        },
    )


async def _get_memory(
    db: AsyncSession, user_id: str, memory_type: MemoryType, memory_key: str
) -> AgentMemory | None:
    """读取单条记忆。"""
    stmt = select(AgentMemory).where(
        AgentMemory.user_id == user_id,
        AgentMemory.memory_type == memory_type,
        AgentMemory.memory_key == memory_key,
    )
    return await db.scalar(stmt)


async def _list_memory(
    db: AsyncSession, user_id: str, memory_type: MemoryType, limit: int = 100
) -> list[AgentMemory]:
    """读取某类型全部记忆（按更新时间倒序）。"""
    stmt = (
        select(AgentMemory)
        .where(
            AgentMemory.user_id == user_id,
            AgentMemory.memory_type == memory_type,
        )
        .order_by(desc(AgentMemory.updated_at))
        .limit(limit)
    )
    result = await db.scalars(stmt)
    return list(result.all())


async def _save_memory(
    db: AsyncSession,
    user_id: str,
    memory_type: MemoryType,
    memory_key: str,
    memory_value: dict,
    source: str = "workflow_inferred",
    workflow_id: str | None = None,
    importance: float = 0.5,
) -> None:
    """upsert 单条记忆。"""
    memory = AgentMemory(
        user_id=user_id,
        memory_type=memory_type,
        memory_key=memory_key,
        memory_value=memory_value,
        source=source,
        workflow_id=workflow_id,
        importance=importance,
    )
    stmt = _upsert_stmt(memory)
    await db.execute(stmt)
    await db.commit()


# ============================================================================
# 工作流集成：加载 + 记录
# ============================================================================


async def load_for_workflow(user_id: str) -> dict[str, Any]:
    """工作流启动时加载用户记忆，返回精简 dict 供注入 WorkflowState。

    返回结构：
        {
            "writing_style": "活泼少女",          # 最近最常用文风（无则空串）
            "image_style": "minimal_white",       # 最近最常用图片风格
            "preferred_topics": ["穿搭", "美妆"],  # 偏好主题类别
            "avoided_topics": [],                  # 避免的主题
            "recent_topics": ["topic1", "topic2"], # 最近 10 条选题
            "recent_copywrites": [                 # 最近 3 条文案摘要
                {"title": "...", "topic": "..."}
            ],
        }
    """
    result: dict[str, Any] = {
        "writing_style": "",
        "image_style": "",
        "preferred_topics": [],
        "avoided_topics": [],
        "recent_topics": [],
        "recent_copywrites": [],
    }

    try:
        async with AsyncSessionLocal() as db:
            # 偏好：文风
            pref_style = await _get_memory(db, user_id, MemoryType.PREFERENCES, "writing_style")
            if pref_style and pref_style.memory_value:
                result["writing_style"] = str(pref_style.memory_value.get("value", ""))

            # 偏好：图片风格
            pref_img = await _get_memory(db, user_id, MemoryType.PREFERENCES, "image_style")
            if pref_img and pref_img.memory_value:
                result["image_style"] = str(pref_img.memory_value.get("value", ""))

            # 偏好：偏好主题
            pref_topics = await _get_memory(db, user_id, MemoryType.PREFERENCES, "preferred_topics")
            if pref_topics and pref_topics.memory_value:
                result["preferred_topics"] = list(pref_topics.memory_value.get("items", []))

            # 偏好：避免主题
            avoid_topics = await _get_memory(db, user_id, MemoryType.PREFERENCES, "avoided_topics")
            if avoid_topics and avoid_topics.memory_value:
                result["avoided_topics"] = list(avoid_topics.memory_value.get("items", []))

            # 历史选题（按更新时间倒序，取前 N 条）
            topic_items = await _list_memory(db, user_id, MemoryType.TOPIC_HISTORY, _INJECT_TOPIC_LIMIT)
            result["recent_topics"] = [
                str(t.memory_value.get("topic", ""))
                for t in topic_items
                if t.memory_value.get("topic")
            ]

            # 历史文案（取前 N 条摘要）
            copy_items = await _list_memory(db, user_id, MemoryType.COPYWRITE_HISTORY, _INJECT_COPYWRITE_LIMIT)
            result["recent_copywrites"] = [
                {
                    "title": str(c.memory_value.get("title", ""))[:40],
                    "topic": str(c.memory_value.get("topic", ""))[:30],
                }
                for c in copy_items
                if c.memory_value.get("title")
            ]

        logger.info(
            f"[memory] loaded for user {user_id}: "
            f"style={result['writing_style'] or '(none)'}, "
            f"recent_topics={len(result['recent_topics'])}, "
            f"recent_copywrites={len(result['recent_copywrites'])}"
        )
    except Exception as e:
        logger.warning(f"[memory] load failed for user {user_id}: {e}")

    return result


async def record_workflow_result(
    user_id: str,
    workflow_id: str,
    topic: str,
    copywrite_output: dict | None = None,
    model_settings: dict | None = None,
) -> None:
    """工作流完成时记录结果到记忆库。

    - topic_history：记录选题（带时间戳，按更新时间倒序读取即得最近）
    - copywrite_history：记录文案 title + topic 摘要
    - preferences（推断）：更新文风/图片风格的选择计数
    """
    if not topic:
        return

    try:
        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC).isoformat()

            # 1. 记录选题历史（key 用 topic 哈希避免特殊字符，value 存完整 topic + 时间）
            # 同一 topic 重复创作时 upsert 更新时间（让最近创作的排前面）
            topic_key = f"topic_{abs(hash(topic)) % 100000}"
            await _save_memory(
                db, user_id, MemoryType.TOPIC_HISTORY, topic_key,
                {"topic": topic, "workflow_id": workflow_id, "created_at": now},
                source="workflow_inferred",
                workflow_id=workflow_id,
                importance=0.6,
            )

            # 2. 记录文案历史
            if copywrite_output and copywrite_output.get("title"):
                title = str(copywrite_output.get("title", ""))[:100]
                content = str(copywrite_output.get("content", ""))
                # 摘要：取正文前 120 字（控制存储 + prompt token）
                content_summary = content[:120] if content else ""
                copy_key = f"copy_{abs(hash(title)) % 100000}"
                await _save_memory(
                    db, user_id, MemoryType.COPYWRITE_HISTORY, copy_key,
                    {
                        "title": title,
                        "topic": topic[:60],
                        "content_summary": content_summary,
                        "workflow_id": workflow_id,
                        "created_at": now,
                    },
                    source="workflow_inferred",
                    workflow_id=workflow_id,
                    importance=0.7,
                )

            # 3. 推断偏好：从 model_settings 统计文风/图片风格选择
            if model_settings:
                settings = model_settings or {}
                writing_style = str(settings.get("writing_style", "")).strip()
                if writing_style:
                    await _increment_preference_counter(
                        db, user_id, "writing_style", writing_style, workflow_id
                    )
                image_style = str(settings.get("image_style", "")).strip()
                if image_style:
                    await _increment_preference_counter(
                        db, user_id, "image_style", image_style, workflow_id
                    )

            # 清理过期历史（保留最近 N 条）
            await _trim_history(db, user_id, MemoryType.TOPIC_HISTORY, _MAX_TOPIC_HISTORY)
            await _trim_history(db, user_id, MemoryType.COPYWRITE_HISTORY, _MAX_COPYWRITE_HISTORY)

        logger.info(
            f"[memory] recorded workflow result: user={user_id}, "
            f"workflow={workflow_id}, topic={topic[:30]}"
        )
    except Exception as e:
        logger.warning(f"[memory] record_workflow_result failed: {e}")


async def record_publish(
    user_id: str,
    workflow_id: str,
    topic: str,
    title: str,
    post_id: str = "",
) -> None:
    """发布成功时记录发布历史。"""
    if not title:
        return

    try:
        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC).isoformat()
            pub_key = f"pub_{abs(hash(title + workflow_id)) % 100000}"
            await _save_memory(
                db, user_id, MemoryType.PUBLISH_HISTORY, pub_key,
                {
                    "title": title[:100],
                    "topic": topic[:60],
                    "post_id": post_id,
                    "workflow_id": workflow_id,
                    "published_at": now,
                },
                source="publish_feedback",
                workflow_id=workflow_id,
                importance=0.9,
            )
            await _trim_history(db, user_id, MemoryType.PUBLISH_HISTORY, _MAX_PUBLISH_HISTORY)

        logger.info(
            f"[memory] recorded publish: user={user_id}, "
            f"workflow={workflow_id}, title={title[:30]}"
        )
    except Exception as e:
        logger.warning(f"[memory] record_publish failed: {e}")


async def update_preferences(
    user_id: str,
    writing_style: str | None = None,
    image_style: str | None = None,
    preferred_topics: list[str] | None = None,
    avoided_topics: list[str] | None = None,
) -> None:
    """用户显式设置偏好（覆盖工作流推断）。"""
    try:
        async with AsyncSessionLocal() as db:
            if writing_style is not None and writing_style.strip():
                await _save_memory(
                    db, user_id, MemoryType.PREFERENCES, "writing_style",
                    {"value": writing_style.strip()},
                    source="user_explicit",
                    importance=1.0,
                )
            if image_style is not None and image_style.strip():
                await _save_memory(
                    db, user_id, MemoryType.PREFERENCES, "image_style",
                    {"value": image_style.strip()},
                    source="user_explicit",
                    importance=1.0,
                )
            if preferred_topics is not None:
                await _save_memory(
                    db, user_id, MemoryType.PREFERENCES, "preferred_topics",
                    {"items": [t.strip() for t in preferred_topics if t.strip()][:20]},
                    source="user_explicit",
                    importance=1.0,
                )
            if avoided_topics is not None:
                await _save_memory(
                    db, user_id, MemoryType.PREFERENCES, "avoided_topics",
                    {"items": [t.strip() for t in avoided_topics if t.strip()][:20]},
                    source="user_explicit",
                    importance=1.0,
                )
        logger.info(f"[memory] preferences updated: user={user_id}")
    except Exception as e:
        logger.warning(f"[memory] update_preferences failed: {e}")


async def get_user_memory_overview(user_id: str) -> dict[str, Any]:
    """返回用户记忆概览（供 API 查询）。"""
    overview: dict[str, Any] = {
        "preferences": {},
        "stats": {
            "topic_history_count": 0,
            "copywrite_history_count": 0,
            "publish_history_count": 0,
        },
        "recent_topics": [],
        "recent_publishes": [],
    }

    try:
        async with AsyncSessionLocal() as db:
            # 偏好
            for key in ("writing_style", "image_style", "preferred_topics", "avoided_topics"):
                pref = await _get_memory(db, user_id, MemoryType.PREFERENCES, key)
                if pref and pref.memory_value:
                    if key in ("preferred_topics", "avoided_topics"):
                        overview["preferences"][key] = list(pref.memory_value.get("items", []))
                    else:
                        overview["preferences"][key] = str(pref.memory_value.get("value", ""))
                else:
                    overview["preferences"][key] = [] if key.endswith("topics") else ""

            # 统计
            for mtype, stat_key in [
                (MemoryType.TOPIC_HISTORY, "topic_history_count"),
                (MemoryType.COPYWRITE_HISTORY, "copywrite_history_count"),
                (MemoryType.PUBLISH_HISTORY, "publish_history_count"),
            ]:
                items = await _list_memory(db, user_id, mtype, 1000)
                overview["stats"][stat_key] = len(items)

            # 最近选题
            topic_items = await _list_memory(db, user_id, MemoryType.TOPIC_HISTORY, 10)
            overview["recent_topics"] = [
                {
                    "topic": str(t.memory_value.get("topic", "")),
                    "created_at": str(t.memory_value.get("created_at", "")),
                }
                for t in topic_items
            ]

            # 最近发布
            pub_items = await _list_memory(db, user_id, MemoryType.PUBLISH_HISTORY, 10)
            overview["recent_publishes"] = [
                {
                    "title": str(p.memory_value.get("title", "")),
                    "topic": str(p.memory_value.get("topic", "")),
                    "published_at": str(p.memory_value.get("published_at", "")),
                }
                for p in pub_items
            ]
    except Exception as e:
        logger.warning(f"[memory] get_overview failed: {e}")

    return overview


# ============================================================================
# 内部辅助
# ============================================================================


async def _increment_preference_counter(
    db: AsyncSession,
    user_id: str,
    key: str,
    value: str,
    workflow_id: str,
) -> None:
    """更新偏好计数：统计每个文风/图片风格被选择的次数，供 load 时取最高频。

    memory_value 结构：{"counts": {"活泼少女": 3, "知性优雅": 1}, "last_value": "活泼少女"}
    load 时取 counts 中最高频的 value 作为偏好返回。
    """
    existing = await _get_memory(db, user_id, MemoryType.PREFERENCES, key)
    if existing and existing.memory_value:
        counts = dict(existing.memory_value.get("counts", {}))
        counts[value] = counts.get(value, 0) + 1
        new_value = {
            "counts": counts,
            "last_value": value,
            # 显式记录最高频，load 时直接读
            "value": max(counts, key=counts.get) if counts else value,
        }
        source = existing.source  # 保留原 source（user_explicit 优先级高）
    else:
        new_value = {
            "counts": {value: 1},
            "last_value": value,
            "value": value,
        }
        source = "workflow_inferred"

    await _save_memory(
        db, user_id, MemoryType.PREFERENCES, key, new_value,
        source=source,
        workflow_id=workflow_id,
        importance=0.8,
    )


async def _trim_history(
    db: AsyncSession,
    user_id: str,
    memory_type: MemoryType,
    keep: int,
) -> None:
    """清理过期历史，只保留最近 keep 条。

    按 updated_at 倒序，删除超出 keep 的旧记录。
    """
    stmt = (
        select(AgentMemory.id)
        .where(
            AgentMemory.user_id == user_id,
            AgentMemory.memory_type == memory_type,
        )
        .order_by(desc(AgentMemory.updated_at))
        .offset(keep)
    )
    result = await db.scalars(stmt)
    ids_to_delete = list(result.all())
    if not ids_to_delete:
        return
    await db.execute(
        AgentMemory.__table__.delete().where(AgentMemory.id.in_(ids_to_delete))
    )
    await db.commit()
    logger.debug(
        f"[memory] trimmed {len(ids_to_delete)} old {memory_type.value} records "
        f"for user {user_id}"
    )


# ============================================================================
# 搜索关键词偏好记忆
# ============================================================================

_MAX_SEARCH_KEYWORDS = 30


async def record_search_keyword(user_id: str, keyword: str, weight: int = 1) -> None:
    """记录用户搜索过的关键词到偏好记忆。

    memory_type = MemoryType.PREFERENCES
    memory_key = "search_keywords"
    memory_value 结构: {"items": [{"keyword": str, "count": int, "last_at": ISO8601}]}

    同一 keyword 存在则 count += weight 并更新 last_at；
    不存在则追加新元素；items 最多保留 30 条（按 count+时间排序淘汰）。
    """
    if not user_id or not keyword or not keyword.strip():
        return

    try:
        async with AsyncSessionLocal() as db:
            now = datetime.now(UTC).isoformat()
            existing = await _get_memory(db, user_id, MemoryType.PREFERENCES, "search_keywords")

            items: list[dict] = []
            if existing and existing.memory_value:
                items = list(existing.memory_value.get("items", []))

            kw = keyword.strip()
            found = False
            for it in items:
                if it.get("keyword") == kw:
                    it["count"] = int(it.get("count", 0)) + weight
                    it["last_at"] = now
                    found = True
                    break

            if not found:
                items.append({"keyword": kw, "count": weight, "last_at": now})

            def _sort_key(it: dict) -> tuple:
                return (-int(it.get("count", 0)), it.get("last_at", ""))

            items.sort(key=_sort_key)
            items = items[:_MAX_SEARCH_KEYWORDS]

            await _save_memory(
                db, user_id, MemoryType.PREFERENCES, "search_keywords",
                {"items": items},
                source="search_history",
                importance=0.7,
            )

        logger.debug(
            f"[memory] recorded search keyword: user={user_id}, "
            f"keyword={kw!r}, weight={weight}"
        )
    except Exception as e:
        logger.warning(f"[memory] record_search_keyword failed: {e}")


async def get_search_keywords(user_id: str, limit: int = 5) -> list[str]:
    """从搜索关键词记忆中按 count 降序、last_at 降序取前 limit 个 keyword。

    无记忆或无匹配则返回空 list。
    """
    if not user_id:
        return []

    try:
        async with AsyncSessionLocal() as db:
            existing = await _get_memory(db, user_id, MemoryType.PREFERENCES, "search_keywords")
            if not existing or not existing.memory_value:
                return []

            items = list(existing.memory_value.get("items", []))

            def _sort_key(it: dict) -> tuple:
                return (-int(it.get("count", 0)), it.get("last_at", ""))

            items.sort(key=_sort_key)
            result: list[str] = []
            for it in items[:limit]:
                kw = it.get("keyword")
                if kw:
                    result.append(str(kw))
            return result
    except Exception as e:
        logger.warning(f"[memory] get_search_keywords failed: {e}")
        return []
