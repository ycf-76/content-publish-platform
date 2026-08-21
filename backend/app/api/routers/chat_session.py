"""Chat Session / Message API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.services import chat_session

router = APIRouter(prefix="/api/chat/sessions", tags=["chat_session"])


class CreateSessionRequest(BaseModel):
    title: str = "新会话"


class AddMessageRequest(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system)$")
    content: str = ""
    agent_meta: dict | None = None


@router.post("")
async def create_session(
    payload: CreateSessionRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    data = await chat_session.create_session(user_id, payload.title)
    return StandardResponse(data=data)


@router.get("")
async def list_sessions(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[list]:
    data = await chat_session.list_sessions(user_id)
    return StandardResponse(data=data)


@router.get("/{session_id}/messages")
async def list_messages(
    session_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[list]:
    data = await chat_session.list_messages(session_id)
    return StandardResponse(data=data)


@router.post("/{session_id}/messages")
async def add_message(
    session_id: str,
    payload: AddMessageRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    data = await chat_session.add_message(
        session_id,
        payload.role,
        payload.content,
        payload.agent_meta,
    )
    return StandardResponse(data=data)
