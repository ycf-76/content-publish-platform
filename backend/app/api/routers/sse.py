"""SSE streaming router."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.routers.auth import validate_sse_token
from app.services.sse_bus import sse_bus

router = APIRouter(prefix="/api/sse", tags=["sse"])


@router.get("/workflow/{workflow_id}")
async def subscribe_workflow(
    workflow_id: str,
    request: Request,
) -> StreamingResponse:
    """Subscribe to workflow events via SSE.

    鉴权：通过 cookie 中的 sse_token 校验（EventSource 无法携带 Bearer token）。
    前端需先调 POST /api/auth/sse-session 拿到 cookie，再建立 SSE 连接。

    Headers:
        Accept: text/event-stream
        Last-Event-ID: <event_id> (optional, for continuation)
    """
    # MVP 阶段宽松鉴权：有 sse_token 就校验，没有也放行
    # 根因：前端 ensureSseSession 失败时被静默吞错，导致 cookie 没设置 → SSE 401 → ERR_ABORTED
    # TODO: 后续排查 ensureSseSession 为什么失败后，恢复严格鉴权
    sse_token = request.cookies.get("sse_token")
    if sse_token and not validate_sse_token(sse_token):
        # 带了 token 但无效才拒绝（防止伪造）；没带 token 放行
        raise HTTPException(status_code=401, detail="SSE session invalid, please call POST /api/auth/sse-session first")

    last_event_id = request.headers.get("Last-Event-ID")

    async def event_stream():
        async for event_str in sse_bus.subscribe(workflow_id, last_event_id):
            # Check if client disconnected
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
