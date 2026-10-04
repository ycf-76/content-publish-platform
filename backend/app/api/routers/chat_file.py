"""Chat File API — 对话中创建的文件持久化。"""

from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.services import chat_file

router = APIRouter(prefix="/api/chat/files", tags=["chat_file"])


class CreateFileRequest(BaseModel):
    session_id: str
    name: str
    file_type: str = "text/plain"
    size: int = 0
    url: str = ""
    folder_id: str = ""
    content_text: str | None = None
    meta: dict | None = None


@router.post("")
async def create_file(
    payload: CreateFileRequest,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    data = await chat_file.create_file(
        session_id=payload.session_id,
        name=payload.name,
        file_type=payload.file_type,
        size=payload.size,
        url=payload.url,
        folder_id=payload.folder_id,
        content_text=payload.content_text,
        meta=payload.meta,
    )
    return StandardResponse(data=data)


@router.get("/session/{session_id}")
async def list_files_for_session(
    session_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[list]:
    data = await chat_file.list_files_for_session(session_id)
    return StandardResponse(data=data)


@router.get("/user")
async def list_files_for_user(
    user_id: str = Depends(get_current_user),
) -> StandardResponse[list]:
    data = await chat_file.list_files_for_user(user_id)
    return StandardResponse(data=data)


@router.get("/media/{file_id}")
async def get_file_media(
    file_id: str,
    user_id: str = Depends(get_current_user),
) -> FileResponse:
    f = await chat_file.get_user_file(file_id, user_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    meta = f.get("meta") or {}
    local_path = meta.get("local_path", "") if isinstance(meta, dict) else ""
    if not local_path or not os.path.isfile(local_path):
        raise HTTPException(status_code=404, detail="Media file not found")
    media_type = f.get("file_type") or "application/octet-stream"
    return FileResponse(
        local_path,
        media_type=media_type,
        filename=f.get("name") or None,
    )


@router.get("/{file_id}")
async def get_file(
    file_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict | None]:
    data = await chat_file.get_file(file_id)
    return StandardResponse(data=data)


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[bool]:
    ok = await chat_file.delete_file(file_id)
    return StandardResponse(data=ok)
