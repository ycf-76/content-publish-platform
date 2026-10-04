"""Chat Session / Message 持久化服务。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select

from app.db.models import ChatMessage, ChatSession, User
from app.db.session import AsyncSessionLocal


def _session_to_dict(session: ChatSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "user_id": session.user_id,
        "work_id": session.work_id,
        "folder_id": session.folder_id or "",
        "title": session.title,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


def _message_to_dict(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "session_id": message.session_id,
        "role": message.role,
        "content": message.content,
        "agent_meta": message.agent_meta,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


async def get_session(session_id: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        return _session_to_dict(session) if session else None


async def create_session(user_id: str, title: str = "新会话", work_id: str | None = None, folder_id: str | None = None) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        if user is None:
            user = User(id=user_id, nickname=f"user_{user_id[:8]}")
            db.add(user)
            await db.flush()
        session = ChatSession(user_id=user_id, title=title or "新会话", work_id=work_id, folder_id=folder_id or "")
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return _session_to_dict(session)


async def ensure_session(session_id: str, user_id: str, title: str = "新会话", work_id: str | None = None, folder_id: str | None = None) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            user = await db.get(User, user_id)
            if user is None:
                user = User(id=user_id, nickname=f"user_{user_id[:8]}")
                db.add(user)
                await db.flush()
            session = ChatSession(id=session_id, user_id=user_id, title=title or "新会话", work_id=work_id, folder_id=folder_id or "")
            db.add(session)
            await db.commit()
            await db.refresh(session)
        return _session_to_dict(session)


async def list_sessions(user_id: str, limit: int = 50, work_id: str | None = None) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        stmt = select(ChatSession).where(ChatSession.user_id == user_id)
        if work_id is not None:
            stmt = stmt.where(ChatSession.work_id == work_id)
        stmt = stmt.order_by(desc(ChatSession.updated_at)).limit(limit)
        result = await db.scalars(stmt)
        return [_session_to_dict(s) for s in result.all()]


async def add_message(
    session_id: str,
    role: str,
    content: str,
    agent_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            user = await db.get(User, "system")
            if user is None:
                user = User(id="system", nickname="system")
                db.add(user)
                await db.flush()
            session = ChatSession(id=session_id, user_id="system", title="新会话")
            db.add(session)
            await db.flush()

        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            agent_meta=agent_meta,
        )
        db.add(message)

        session.updated_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(message)
        return _message_to_dict(message)


async def mark_clarification_resolved(session_id: str) -> int:
    """把该会话中所有 workflow_status=awaiting_clarification 的 assistant 消息标记为 completed。

    用户提交澄清后调用，防止刷新页面时旧澄清卡片重新出现。
    返回受影响行数。
    """
    async with AsyncSessionLocal() as db:
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
            )
            .order_by(ChatMessage.created_at)
        )
        result = await db.scalars(stmt)
        count = 0
        for msg in result.all():
            meta = msg.agent_meta
            if isinstance(meta, dict) and meta.get("workflow_status") == "awaiting_clarification":
                meta["workflow_status"] = "completed"
                msg.agent_meta = meta
                count += 1
        if count:
            await db.commit()
        return count


async def list_messages(session_id: str, limit: int = 200) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at)
            .limit(limit)
        )
        result = await db.scalars(stmt)
        return [_message_to_dict(m) for m in result.all()]


async def get_last_workflow_id(session_id: str) -> str | None:
    """从上一条 assistant 消息的 agent_meta.workflow_id 取，供多轮追问注入上游输出。"""
    async with AsyncSessionLocal() as db:
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == "assistant",
            )
            .order_by(desc(ChatMessage.created_at))
            .limit(1)
        )
        message = await db.scalar(stmt)
        if message and message.agent_meta:
            return message.agent_meta.get("workflow_id")
        return None


async def get_recent_messages(
    session_id: str, limit: int = 6, offset: int = 0,
) -> list[dict[str, Any]]:
    """取最近 N 条消息（倒序取+反转），支持 offset 跳过最新消息。

    用于 _agentic_loop 的会话历史注入。offset=1 时跳过最新一条
    （避免重复注入当前消息——路由层在调用 process 之前已写入）。
    """
    async with AsyncSessionLocal() as db:
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(desc(ChatMessage.created_at))
            .limit(limit)
            .offset(offset)
        )
        result = await db.scalars(stmt)
        messages = [_message_to_dict(m) for m in result.all()]
        messages.reverse()
        return messages


async def get_last_workflow_topic(session_id: str) -> str | None:
    """取会话最近一次工作流的 topic，供追问「换个风格」时重跑。"""
    workflow_id = await get_last_workflow_id(session_id)
    if not workflow_id:
        return None

    from app.db.models import Workflow

    async with AsyncSessionLocal() as db:
        workflow = await db.get(Workflow, workflow_id)
        return workflow.topic if workflow else None


async def update_session(session_id: str, title: str | None = None) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            return None
        if title is not None:
            session.title = title
        session.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(session)
        return _session_to_dict(session)


async def get_creative_state(session_id: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            return None
        return session.creative_state


async def update_creative_state(session_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            return None
        current = session.creative_state or {}
        current.update(updates)
        session.creative_state = current
        session.updated_at = datetime.now(UTC)
        await db.commit()
        await db.refresh(session)
        return session.creative_state


async def delete_session(session_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        session = await db.get(ChatSession, session_id)
        if session is None:
            return {"deleted": False}
        await db.delete(session)
        await db.commit()
        return {"deleted": True, "id": session_id}


# ═══════════════════════════════════════════════════════════════
# 会话摘要：阈值触发 LLM 摘要，避免长对话上下文断裂
# ═══════════════════════════════════════════════════════════════

_SUMMARY_ROLE = "system"
_SUMMARY_META_KEY = "conversation_summary"


async def count_messages(session_id: str) -> int:
    """统计会话消息总数（不含 system/summary 消息）。"""
    async with AsyncSessionLocal() as db:
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role.in_(["user", "assistant"]),
            )
        )
        result = await db.scalars(stmt)
        return len(result.all())


async def get_session_summary(session_id: str) -> str | None:
    """取会话的缓存摘要（如果有的话）。"""
    async with AsyncSessionLocal() as db:
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == _SUMMARY_ROLE,
            )
            .order_by(desc(ChatMessage.created_at))
            .limit(1)
        )
        msg = await db.scalar(stmt)
        if msg and msg.agent_meta and msg.agent_meta.get(_SUMMARY_META_KEY):
            return msg.content
    return None


async def get_session_summary_meta(session_id: str) -> dict | None:
    """取会话摘要的元数据（包含 summarized_count）。"""
    async with AsyncSessionLocal() as db:
        stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == _SUMMARY_ROLE,
                ChatMessage.agent_meta[_SUMMARY_META_KEY].as_boolean().is_(True),
            )
            .order_by(desc(ChatMessage.created_at))
            .limit(1)
        )
        msg = await db.scalar(stmt)
        if msg and msg.agent_meta:
            return msg.agent_meta
    return None


async def save_session_summary(
    session_id: str, summary_text: str, summarized_count: int,
) -> None:
    """保存/更新会话摘要。summarized_count 记录本次摘要覆盖了多少条消息。"""
    async with AsyncSessionLocal() as db:
        existing_stmt = (
            select(ChatMessage)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == _SUMMARY_ROLE,
                ChatMessage.agent_meta[_SUMMARY_META_KEY].as_boolean().is_(True),
            )
            .order_by(desc(ChatMessage.created_at))
            .limit(1)
        )
        existing = await db.scalar(existing_stmt)

        if existing:
            existing.content = summary_text
            existing.agent_meta = {
                _SUMMARY_META_KEY: True,
                "summarized_count": summarized_count,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        else:
            msg = ChatMessage(
                session_id=session_id,
                role=_SUMMARY_ROLE,
                content=summary_text,
                agent_meta={
                    _SUMMARY_META_KEY: True,
                    "summarized_count": summarized_count,
                },
            )
            db.add(msg)

        session = await db.get(ChatSession, session_id)
        if session:
            session.updated_at = datetime.now(UTC)

        await db.commit()


async def get_messages_with_summary(
    session_id: str,
    recent_limit: int = 10,
    offset: int = 1,
) -> dict[str, Any]:
    """取会话历史，带摘要支持。

    返回:
        {
            "summary": str | None,   # 旧消息的摘要（如果有）
            "recent": list[dict],    # 最近 N 条完整消息
            "total_count": int,      # 会话总消息数
            "needs_summary": bool,   # 是否需要生成/更新摘要
        }
    """
    total = await count_messages(session_id)
    recent = await get_recent_messages(session_id, limit=recent_limit, offset=offset)
    summary = await get_session_summary(session_id)

    return {
        "summary": summary,
        "recent": recent,
        "total_count": total,
        "needs_summary": False,
    }