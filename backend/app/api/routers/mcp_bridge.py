"""MCP 桥接路由。

后端无法直接调浏览器扩展（MV3 service worker 不监听 HTTP 端口）。
通过桥接页面作为中间层：
1. 后端 PluginMCPClient 把请求存入内存队列（pending_calls）
2. 桥接页面通过 SSE 接收请求
3. 桥接页面调 chrome.runtime.sendMessage 转发给扩展
4. 扩展返回结果后，桥接页面 POST 回后端

桥接页面通过 /api/mcp/bridge/register 注册自己在线状态。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas.common import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mcp/bridge", tags=["mcp-bridge"])


# ============ 桥接状态 ============

class _BridgeState:
    """桥接页面状态：在线状态 + 待处理请求队列 + 结果回传。"""

    def __init__(self) -> None:
        self.online = False
        self.last_heartbeat: datetime | None = None
        # 待处理的 MCP 请求：call_id -> { event, future }
        self._pending: dict[str, dict[str, Any]] = {}
        # SSE 订阅的 asyncio.Queue（每个 SSE 连接一个）
        self._subscribers: list[asyncio.Queue] = []
        self._results: dict[str, Any] = {}  # call_id -> result（暂存回传结果）
        self._lock = asyncio.Lock()

    async def call_extension(self, action: str, payload: dict) -> dict[str, Any]:
        """后端调用扩展（通过桥接页面转发）。"""
        # 快速失败：没有订阅者时直接返回
        if not self._subscribers:
            logger.warning(f"[bridge] call_extension {action}: no subscribers (bridge page not connected)")
            return {
                "success": False,
                "message": "桥接页面未订阅（请访问 /mcp-bridge 并保持标签页打开）",
            }

        # 发布流程需要打开页面+上传图片+填表单+点按钮+等跳转，给 120 秒
        # 搜索需要可能新建小红书标签页（最长 15s）+ 等加载 + 签名 + API 请求，给 60 秒
        if action == "publish_note":
            timeout = 120.0
        elif action == "search_notes":
            timeout = 60.0
        else:
            timeout = 30.0

        call_id = "call_" + uuid.uuid4().hex[:16]
        future: asyncio.Future = asyncio.get_event_loop().create_future()

        async with self._lock:
            self._pending[call_id] = {
                "action": action,
                "payload": payload,
                "future": future,
                "created_at": datetime.now(timezone.utc),
            }

        # 推给所有订阅的桥接页面
        request_msg = {
            "call_id": call_id,
            "action": action,
            "payload": payload,
        }
        delivered = False
        for sub in list(self._subscribers):
            try:
                sub.put_nowait(request_msg)
                delivered = True
            except asyncio.QueueFull:
                logger.warning(f"bridge subscriber queue full, dropping call {call_id}")
        if not delivered:
            async with self._lock:
                self._pending.pop(call_id, None)
            return {"success": False, "message": "桥接页面订阅队列已满"}

        # 等结果（超时按 action 区分）
        logger.info(f"[bridge] call_extension {action} call_id={call_id} waiting (timeout={timeout}s, subscribers={len(self._subscribers)})")
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            logger.info(f"[bridge] call_extension {action} call_id={call_id} got result: success={result.get('success')}")
            return result
        except asyncio.TimeoutError:
            logger.warning(f"[bridge] call_extension {action} call_id={call_id} TIMEOUT ({timeout}s)")
            return {"success": False, "message": f"桥接页面未响应（{int(timeout)}s 超时），请确认桥接页面在前台且扩展已重新加载"}
        finally:
            async with self._lock:
                self._pending.pop(call_id, None)
                self._results.pop(call_id, None)

    async def submit_result(self, call_id: str, result: dict[str, Any]) -> None:
        """桥接页面回传结果。"""
        async with self._lock:
            pending = self._pending.get(call_id)
            if pending and not pending["future"].done():
                pending["future"].set_result(result)
            else:
                # future 已取消或不存在，缓存一会儿防丢失
                self._results[call_id] = result

    def subscribe(self) -> asyncio.Queue:
        """SSE 订阅：返回一个 Queue，桥接页面通过 SSE 接收推送的请求。"""
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)


bridge_state = _BridgeState()


# ============ 路由 ============

@router.post("/register")
async def register_bridge(payload: dict | None = None) -> StandardResponse[dict]:
    """桥接页面注册自己在线（心跳）。"""
    bridge_state.online = True
    bridge_state.last_heartbeat = datetime.now(timezone.utc)
    return StandardResponse(data={"online": True})


@router.get("/pending")
async def get_pending() -> StandardResponse[list[dict]]:
    """桥接页面拉取待处理请求（轮询兜底，主要走 SSE）。"""
    async with bridge_state._lock:
        pending = [
            {"call_id": cid, "action": p["action"], "payload": p["payload"]}
            for cid, p in bridge_state._pending.items()
        ]
    return StandardResponse(data=pending)


@router.post("/result/{call_id}")
async def submit_result(call_id: str, payload: dict) -> StandardResponse[dict]:
    """桥接页面回传 MCP 调用结果。"""
    await bridge_state.submit_result(call_id, payload)
    return StandardResponse(data={"received": True})


@router.get("/stream")
async def stream_requests() -> StreamingResponse:
    """SSE 流：推送待处理的 MCP 请求给桥接页面。"""
    q = bridge_state.subscribe()

    async def event_stream():
        try:
            # 先发个 hello 让连接建立
            yield f"data: {__import__('json').dumps({'type': 'hello', 'message': 'connected'})}\n\n"
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {__import__('json').dumps({'type': 'request', **msg})}\n\n"
                except asyncio.TimeoutError:
                    # 心跳
                    yield f": ping\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            bridge_state.unsubscribe(q)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/health")
async def bridge_health() -> StandardResponse[dict]:
    """桥接页面健康状态（供后端 PluginMCPClient 检测）。"""
    return StandardResponse(data={
        "bridge_online": bridge_state.online,
        "last_heartbeat": bridge_state.last_heartbeat.isoformat() if bridge_state.last_heartbeat else None,
        "pending_calls": len(bridge_state._pending),
    })


@router.get("/debug/capture-headers")
async def debug_capture_headers() -> StandardResponse[dict]:
    """诊断接口：通过桥接页面调扩展的 capture_real_headers action。"""
    result = await bridge_state.call_extension("capture_real_headers", {})
    return StandardResponse(data=result)


@router.get("/debug/extension-health")
async def debug_extension_health() -> StandardResponse[dict]:
    """诊断接口：通过桥接页面调扩展的 health action，测试扩展是否响应。

    用法：浏览器访问 http://localhost:8000/api/mcp/bridge/debug/extension-health
    返回扩展健康状态（online/logged_in/cookies_count）。
    如果超时，说明扩展 service worker 没运行或桥接页面没转发。
    """
    result = await bridge_state.call_extension("health", {})
    return StandardResponse(data=result)


@router.get("/check-account")
async def check_current_account() -> StandardResponse[dict]:
    """查询当前小红书登录账号信息。

    通过桥接页面调扩展的 get_user_info action，
    从小红书页面的 __NEXT_DATA__ 或 /user/me 接口获取当前登录用户。
    """
    result = await bridge_state.call_extension("get_user_info", {})
    return StandardResponse(data=result)
