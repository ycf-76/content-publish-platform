"""SSE streaming router.

P0-1：SSE 鉴权 — JWT 校验 + 工作流归属校验。
前端使用 fetch + AbortController（非 EventSource），可携带 Authorization header。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.services.notification_bus import notification_bus
from app.services.sse_bus import sse_bus
from app.services.workflow import WorkflowService

router = APIRouter(prefix="/api/sse", tags=["sse"])


@router.get("/workflow/{workflow_id}")
async def subscribe_workflow(
    workflow_id: str,
    request: Request,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Subscribe to workflow events via SSE.

    P0-1 鉴权：JWT 校验 + 工作流归属校验。
    前端使用 fetch API（非 EventSource），可携带 Authorization header。
    同时保留 sse_token cookie 作为备用校验（向后兼容）。

    Headers:
        Authorization: Bearer <jwt>
        Accept: text/event-stream
        Last-Event-ID: <event_id> (optional, for continuation)
    """
    # 校验用户是否拥有该工作流
    service = WorkflowService(db)
    workflow = await service.get_workflow(workflow_id, user_id)
    if not workflow:
        raise HTTPException(status_code=403, detail="无权访问此工作流")

    last_event_id = request.headers.get("Last-Event-ID")

    async def event_stream():
        async for event_str in sse_bus.subscribe(workflow_id, last_event_id):
            if await request.is_disconnected():
                break
            yield event_str

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/notifications")
async def subscribe_notifications(
    request: Request,
    user_id: str = Depends(get_current_user),
) -> StreamingResponse:
    """订阅全局通知事件（选题池监控完成等）。

    需要登录（JWT 鉴权）。支持两种方式：
    - Authorization: Bearer <jwt>（推荐）
    - ?token=<jwt>（EventSource 不支持自定义 header 时的备选）
    """

    async def event_stream():
        async for event_str in notification_bus.subscribe():
            if await request.is_disconnected():
                break
            yield event_str

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )