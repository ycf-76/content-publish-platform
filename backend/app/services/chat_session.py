"""Chat Session / Message 持久化服务。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select

from app.db.models import ChatMessage, ChatSession
from app.db.session import AsyncSessionLocal


def _session_to_dict(session: ChatSession) -> dict[str, Any]:
    return {
        "id": session.id,
        "user_id": session.user_id,
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


async def create_session(user_id: str, title: str = "新会话") -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        session = ChatSession(user_id=user_id, title=title or "新会话")
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return _session_to_dict(session)


async def list_sessions(user_id: str, limit: int = 50) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(desc(ChatSession.updated_at))
            .limit(limit)
        )
        result = await db.scalars(stmt)
        return [_session_to_dict(s) for s in result.all()]


async def add_message(
    session_id: str,
    role: str,
    content: str,
    agent_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            agent_meta=agent_meta,
        )
        db.add(message)

        # touch session.updated_at（新增消息时刷新会话排序时间）
        session = await db.get(ChatSession, session_id)
        if session is not None:
            session.updated_at = datetime.now(UTC)

        await db.commit()
        await db.refresh(message)
        return _message_to_dict(message)


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


async def get_last_workflow_topic(session_id: str) -> str | None:
    """取会话最近一次工作流的 topic，供追问「换个风格」时重跑。"""
    workflow_id = await get_last_workflow_id(session_id)
    if not workflow_id:
        return None

    from app.db.models import Workflow

    async with AsyncSessionLocal() as db:
        workflow = await db.get(Workflow, workflow_id)
        return workflow.topic if workflow else None
