"""
微信机器人 API 路由

提供RESTful接口用于控制微信机器人:
- 启动/停止服务
- 查询状态
- 获取二维码
- 发送消息

所有接口需要 JWT 认证，按平台用户ID隔离。

路由前缀: /api/wechat
"""

import asyncio
import base64
import logging
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.rpa.wechat_bot_engine import WeChatBotEngine, BotStatus, get_wechat_engine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wechat", tags=["WeChat Bot"])


# ==================== 请求/响应模型 ====================

class StartRequest(BaseModel):
    """启动请求（预留扩展）"""
    pass


class StopRequest(BaseModel):
    """停止请求"""
    pass


class SendMessageRequest(BaseModel):
    """发送消息请求"""
    to_user_id: str = Field(..., description="目标微信用户ID", min_length=1)
    content: str = Field(..., description="消息内容", min_length=1)
    context_token: str = Field("", description="会话令牌(可选，不传则从缓存获取)")


class PushContentRequest(BaseModel):
    """推送内容请求"""
    to_user_id: str = Field(..., description="目标微信用户ID")
    title: str = Field("", description="标题(可选)")
    text: str = Field("", description="正文内容")
    image_urls: list[str] = Field(default_factory=list, description="图片URL列表(可选)")
    images_base64: list[str] = Field(default_factory=list, description="图片base64列表(可选)")
    context_token: str = Field("", description="会话令牌(可选)")


# ==================== RESTful API 接口 ====================

@router.post("/start")
async def start_service(
    request: StartRequest = None,
    user_id: str = Depends(get_current_user),
):
    """
    启动微信机器人服务

    按当前登录用户ID隔离，每个用户有独立的引擎实例。
    """
    try:
        engine = get_wechat_engine(user_id)

        if engine.is_running:
            return {
                "success": True,
                "data": engine.state.to_dict(),
                "message": "服务已在运行中"
            }

        await engine.start()

        return {
            "success": True,
            "data": engine.state.to_dict(),
            "message": "服务已启动，等待扫码"
        }

    except Exception as e:
        logger.error(f"[API] 启动服务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_service(
    request: StopRequest = None,
    user_id: str = Depends(get_current_user),
):
    """停止微信机器人服务"""
    try:
        engine = get_wechat_engine(user_id)

        if not engine.is_running:
            return {
                "success": True,
                "data": engine.state.to_dict(),
                "message": "服务未运行"
            }

        await engine.stop()

        return {
            "success": True,
            "data": engine.state.to_dict(),
            "message": "服务已停止"
        }

    except Exception as e:
        logger.error(f"[API] 停止服务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status(user_id: str = Depends(get_current_user)):
    """查询当前用户的机器人状态"""
    try:
        engine = get_wechat_engine(user_id)
        state_data = engine.state.to_dict()
        state_data["is_running"] = engine.is_running

        return {
            "success": True,
            "data": state_data
        }

    except Exception as e:
        logger.error(f"[API] 查询状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/qrcode")
async def get_qrcode(user_id: str = Depends(get_current_user)):
    """获取登录二维码"""
    try:
        engine = get_wechat_engine(user_id)

        logger.info(f"[API] get_qrcode - user={user_id}, running: {engine.is_running}, status: {engine.state.status.value}")

        qr_info = await engine.get_qrcode()

        result = {
            "success": True,
            "data": {
                "qrcode": qr_info.get("qrcode", ""),
                "status": qr_info.get("status", ""),
                "expires_in": qr_info.get("expires_in", 120)
            },
            "message": qr_info.get("message")
        }

        return result

    except Exception as e:
        logger.error(f"[API] 获取二维码失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send")
async def send_message(
    request: SendMessageRequest,
    user_id: str = Depends(get_current_user),
):
    """发送文本消息到微信用户"""
    try:
        if not request.to_user_id or not request.to_user_id.strip():
            raise HTTPException(status_code=400, detail="to_user_id 不能为空")

        if not request.content or not request.content.strip():
            raise HTTPException(status_code=400, detail="content 不能为空")

        engine = get_wechat_engine(user_id)

        if not engine.is_logged_in:
            raise HTTPException(status_code=400, detail="机器人未登录，无法发送消息")

        context_token = request.context_token
        if not context_token:
            context_token = engine._client.get_context_token(request.to_user_id) if engine._client else None

        if not context_token:
            raise HTTPException(status_code=400, detail="缺少 context_token，请先让对方发一条消息")

        success = await engine.send_text(
            to_user_id=request.to_user_id.strip(),
            context_token=context_token,
            text=request.content.strip()
        )

        if success:
            return {
                "success": True,
                "data": {"sent": True},
                "message": "消息发送成功"
            }
        else:
            raise HTTPException(status_code=500, detail="消息发送失败")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 发送消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages")
async def get_messages(
    limit: int = 20,
    user_id: str = Depends(get_current_user),
):
    """获取最近的消息列表"""
    try:
        engine = get_wechat_engine(user_id)
        messages = engine.get_recent_messages(limit=limit)

        return {
            "success": True,
            "data": {
                "messages": messages,
                "total": len(messages)
            }
        }

    except Exception as e:
        logger.error(f"[API] 获取消息列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/push")
async def push_content(
    request: PushContentRequest,
    user_id: str = Depends(get_current_user),
):
    """推送内容到微信（文本+图片）"""
    try:
        engine = get_wechat_engine(user_id)

        if not engine.is_logged_in:
            raise HTTPException(status_code=400, detail="机器人未登录")

        context_token = request.context_token
        if not context_token and engine._client:
            context_token = engine._client.get_context_token(request.to_user_id)

        if not context_token:
            raise HTTPException(status_code=400, detail="缺少 context_token，请先让对方发一条消息")

        results = {"text_sent": False, "images_sent": 0, "images_failed": 0}

        # 1. 发送文本
        content_parts = []
        if request.title:
            content_parts.append(f"📌 {request.title}")
        if request.text:
            content_parts.append(request.text)

        if content_parts:
            full_text = "\n\n".join(content_parts)
            if len(full_text) > 4000:
                full_text = full_text[:3997] + "..."

            success = await engine.send_text(
                to_user_id=request.to_user_id,
                context_token=context_token,
                text=full_text
            )
            results["text_sent"] = success

            if not success:
                raise HTTPException(status_code=500, detail="文本发送失败")

        # 2. 发送 URL 图片
        if request.image_urls:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                for url in request.image_urls:
                    try:
                        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                            if resp.status != 200:
                                logger.warning(f"[API] 下载图片失败: {url}, status={resp.status}")
                                results["images_failed"] += 1
                                continue

                            image_data = await resp.read()

                            ct = resp.headers.get("Content-Type", "")
                            if "jpeg" in ct or "jpg" in ct:
                                ext = "jpg"
                            elif "gif" in ct:
                                ext = "gif"
                            else:
                                ext = "png"

                            img_success = await engine.send_image(
                                to_user_id=request.to_user_id,
                                context_token=context_token,
                                image_data=image_data,
                                file_ext=ext
                            )
                            if img_success:
                                results["images_sent"] += 1
                            else:
                                results["images_failed"] += 1

                            await asyncio.sleep(0.5)

                    except Exception as e:
                        logger.error(f"[API] 发送图片异常: {url}, {e}")
                        results["images_failed"] += 1

        # 3. 发送 base64 图片
        if request.images_base64:
            for i, b64 in enumerate(request.images_base64):
                try:
                    raw = b64
                    if "," in b64:
                        prefix, raw = b64.split(",", 1)
                        if "jpeg" in prefix or "jpg" in prefix:
                            ext = "jpg"
                        elif "gif" in prefix:
                            ext = "gif"
                        else:
                            ext = "png"
                    else:
                        ext = "png"

                    image_data = base64.b64decode(raw)
                    logger.info(f"[API] 发送base64图片 {i+1}/{len(request.images_base64)}, size={len(image_data)}bytes")

                    img_success = await engine.send_image(
                        to_user_id=request.to_user_id,
                        context_token=context_token,
                        image_data=image_data,
                        file_ext=ext
                    )
                    if img_success:
                        results["images_sent"] += 1
                    else:
                        results["images_failed"] += 1

                    await asyncio.sleep(0.5)

                except Exception as e:
                    logger.error(f"[API] 发送base64图片异常: {i}, {e}")
                    results["images_failed"] += 1

        if not content_parts and not request.image_urls and not request.images_base64:
            raise HTTPException(status_code=400, detail="无内容可推送")

        return {
            "success": True,
            "data": results,
            "message": f"推送完成: 文本={'✅' if results['text_sent'] else '❌'}, 图片={results['images_sent']}张成功{results['images_failed']}张失败"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API] 推送内容失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== WebSocket 接口 ====================

@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """
    WebSocket 实时推送状态变化

    连接时需在 query 参数中携带 token:
      ws://host/api/wechat/ws/status?token=<jwt>
    """
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    try:
        from app.security import decode_user_id
        user_id = decode_user_id(token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await websocket.accept()
    logger.info(f"[WS] WebSocket客户端已连接 (user={user_id})")

    engine = get_wechat_engine(user_id)

    async def status_callback(state):
        try:
            message = {
                "type": "status_change",
                "data": state.to_dict(),
                "timestamp": datetime.now().isoformat()
            }
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"[WS] 推送消息失败: {e}")

    engine.on_status_change(status_callback)

    try:
        current_state = {
            "type": "initial_status",
            "data": engine.state.to_dict(),
            "timestamp": datetime.now().isoformat()
        }
        await websocket.send_json(current_state)

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        logger.info(f"[WS] WebSocket客户端断开连接 (user={user_id})")
    except Exception as e:
        logger.error(f"[WS] WebSocket错误: {e}")
    finally:
        pass


# ==================== 健康检查 ====================

@router.get("/health")
async def health_check(user_id: str = Depends(get_current_user)):
    """健康检查端点"""
    try:
        engine = get_wechat_engine(user_id)

        if engine.is_logged_in:
            status = "healthy"
        elif engine.is_running:
            status = "degraded"
        else:
            status = "stopped"

        uptime = 0
        if engine.state.start_time:
            uptime = int((datetime.now() - engine.state.start_time).total_seconds())

        return {
            "status": status,
            "uptime": uptime,
            "bot_status": engine.state.status.value
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


# ==================== 注册路由到应用 ====================

def register_routes(app):
    """
    将路由注册到FastAPI应用

    在 main.py 中调用:
        from app.api.routers.wechat_bot import register_routes
        register_routes(app)
    """