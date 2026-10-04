"""ChatFile 持久化服务。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select

from app.db.models import ChatFile
from app.db.session import AsyncSessionLocal


def _file_to_dict(f: ChatFile, include_local_path: bool = False) -> dict[str, Any]:
    meta = f.meta
    if not include_local_path and isinstance(meta, dict) and "local_path" in meta:
        meta = {k: v for k, v in meta.items() if k != "local_path"}
    return {
        "id": f.id,
        "session_id": f.session_id,
        "name": f.name,
        "file_type": f.file_type,
        "size": f.size,
        "url": f.url,
        "folder_id": f.folder_id,
        "content_text": f.content_text,
        "meta": meta,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


async def create_file(
    session_id: str,
    name: str,
    file_type: str = "text/plain",
    size: int = 0,
    url: str = "",
    folder_id: str = "",
    content_text: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        f = ChatFile(
            session_id=session_id,
            name=name,
            file_type=file_type,
            size=size,
            url=url,
            folder_id=folder_id,
            content_text=content_text,
            meta=meta,
        )
        db.add(f)
        await db.commit()
        await db.refresh(f)
        return _file_to_dict(f)


async def list_files_for_session(session_id: str) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        stmt = (
            select(ChatFile)
            .where(ChatFile.session_id == session_id)
            .order_by(ChatFile.created_at)
        )
        result = await db.scalars(stmt)
        return [_file_to_dict(f) for f in result.all()]


async def list_files_for_user(user_id: str, limit: int = 200) -> list[dict[str, Any]]:
    async with AsyncSessionLocal() as db:
        from app.db.models import ChatSession
        stmt = (
            select(ChatFile)
            .join(ChatSession, ChatFile.session_id == ChatSession.id)
            .where(ChatSession.user_id == user_id)
            .order_by(desc(ChatFile.created_at))
            .limit(limit)
        )
        result = await db.scalars(stmt)
        return [_file_to_dict(f) for f in result.all()]


async def get_latest_copywrite(
    user_id: str, session_id: str | None = None,
) -> dict[str, Any] | None:
    """返回用户最近一条可发送的完整文案。

    新代码会把全文写入 agent_memories；旧代码只写了摘要，
    完整内容实际保存在 chat_files，因此这里做两层回退。
    Web 会话指定 session_id 时只认当前会话，避免发到其它会话的旧文。
    """
    memory_latest = None
    try:
        from app.services import agent_memory
        memory_latest = await agent_memory.get_latest_copywrite(user_id)
        if memory_latest and memory_latest.get("content"):
            if not session_id or memory_latest.get("workflow_id") == session_id:
                return memory_latest
    except Exception:
        pass

    async with AsyncSessionLocal() as db:
        from app.db.models import ChatSession

        def _latest_from_row(f: ChatFile) -> dict[str, Any] | None:
            meta = f.meta or {}
            if meta.get("source") != "copywrite" or not f.content_text:
                return None
            title = str(meta.get("title") or (f.name or "").removesuffix(".md"))
            content = str(f.content_text)
            prefix = f"# {title}"
            if content.startswith(prefix):
                content = content[len(prefix):].lstrip()
            return {
                "title": title,
                "topic": str(meta.get("topic", "")),
                "content": content,
                "tags": meta.get("tags") or [],
                "workflow_id": f.session_id,
                "created_at": f.created_at.isoformat() if f.created_at else "",
            }

        async def _query(sid: str) -> dict[str, Any] | None:
            stmt = (
                select(ChatFile)
                .where(ChatFile.session_id == sid)
                .order_by(desc(ChatFile.created_at))
                .limit(50)
            )
            result = await db.scalars(stmt)
            for f in result.all():
                latest = _latest_from_row(f)
                if latest:
                    return latest
            return None

        if session_id:
            return await _query(session_id)

        memory_session = str((memory_latest or {}).get("workflow_id", ""))
        if memory_session:
            session_latest = await _query(memory_session)
            if session_latest:
                return session_latest

        stmt = (
            select(ChatFile)
            .join(ChatSession, ChatFile.session_id == ChatSession.id)
            .where(ChatSession.user_id == user_id)
            .order_by(desc(ChatFile.created_at))
            .limit(100)
        )
        result = await db.scalars(stmt)
        for f in result.all():
            latest = _latest_from_row(f)
            if latest:
                return latest

    return memory_latest if memory_latest else None


async def get_file(file_id: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        f = await db.get(ChatFile, file_id)
        return _file_to_dict(f) if f else None


async def get_user_file(file_id: str, user_id: str) -> dict[str, Any] | None:
    async with AsyncSessionLocal() as db:
        from app.db.models import ChatSession
        stmt = (
            select(ChatFile)
            .join(ChatSession, ChatFile.session_id == ChatSession.id)
            .where(ChatFile.id == file_id, ChatSession.user_id == user_id)
        )
        f = await db.scalar(stmt)
        return _file_to_dict(f, include_local_path=True) if f else None


async def delete_file(file_id: str) -> bool:
    async with AsyncSessionLocal() as db:
        f = await db.get(ChatFile, file_id)
        if not f:
            return False
        await db.delete(f)
        await db.commit()
        return True
