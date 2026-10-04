"""飞书机器人 API 路由

提供RESTful接口用于控制飞书机器人:
- 启动/停止服务
- 查询状态
- 发送消息
- 导入文档
- 导出到多维表格
- Webhook 回调（飞书事件订阅推送）

所有接口（除 webhook 外）需要 JWT 认证，按平台用户ID隔离。

路由前缀: /api/feishu
"""

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.rpa.feishu_bot import FeishuBotEngine, get_feishu_engine, remove_feishu_engine
from app.rpa.feishu_agent_bridge import get_or_create_bridge, remove_bridge
from app.adapters.feishu import FeishuAPIError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/feishu", tags=["Feishu Bot"])


# ==================== 请求/响应模型 ====================

class StartRequest(BaseModel):
    pass


class StopRequest(BaseModel):
    pass


class SendMessageRequest(BaseModel):
    receive_id: str = Field(..., description="接收者ID（群chat_id或用户open_id）", min_length=1)
    content: str = Field(..., description="消息内容", min_length=1)
    receive_id_type: str = Field(default="chat_id", description="receive_id类型: chat_id | open_id")


class ImportDocumentRequest(BaseModel):
    document_id: str = Field(..., description="飞书文档ID或链接", min_length=1)


class ExportToBitableRequest(BaseModel):
    records: list[dict[str, Any]] = Field(..., description="要导出的记录列表", min_length=1)
    app_token: str = Field(default="", description="多维表格App Token（留空用默认）")
    table_id: str = Field(default="", description="多维表格Table ID（留空用默认）")


# ==================== Webhook 回调 ====================

async def _process_task_plan_card_action(value: dict[str, Any]) -> None:
    """后台执行任务清单卡片确认（resume/终止工作流可能耗时，不能阻塞回调响应）。"""
    try:
        from app.db.session import AsyncSessionLocal
        from app.services.task_plan import TaskPlanService

        async with AsyncSessionLocal() as db:
            svc = TaskPlanService(db)
            result = await svc.handle_card_action(value)
        if not result.get("success"):
            logger.warning(f"[FeishuWebhook] task_plan card action rejected: {result.get('message')}")
    except Exception as e:
        logger.exception(f"[FeishuWebhook] task_plan card action failed: {e}")


async def _handle_card_action(event: dict[str, Any]) -> dict[str, Any]:
    """处理卡片按钮回调（card.action.trigger），按 value.biz 路由。

    目前支持：biz="task_plan"（任务清单人工确认，见 services/task_plan.py）。
    其余 biz 忽略并返回 code 0（避免飞书重试推送）。

    飞书要求 3 秒内响应，而确认动作会 resume 工作流（可能执行发布等重节点），
    故先回 toast、后台任务执行实际处理；重复推送由 handle_card_action 幂等挡住。
    """
    action_payload = event.get("action", {}) or {}
    value = action_payload.get("value")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    if not isinstance(value, dict):
        value = {}

    biz = str(value.get("biz", ""))
    if biz != "task_plan":
        logger.info(f"[FeishuWebhook] Ignored card action: biz={biz!r}")
        return {"code": 0}

    asyncio.create_task(_process_task_plan_card_action(value))

    toast_content = {
        "approve": "已确认，任务继续执行",
        "regenerate": "已打回，即将重新生成",
        "skip": "已跳过本条",
    }.get(str(value.get("action", "")), "已收到")
    return {"code": 0, "toast": {"type": "success", "content": toast_content}}


@router.post("/webhook")
async def feishu_webhook(request: Request):
    """飞书事件订阅回调端点。

    飞书开放平台推送事件到此端点。
    处理两种请求：
    1. URL 验证（首次配置时飞书发送 challenge）
    2. 事件推送（消息接收等）
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    import json as _json
    logger.info(f"[FeishuWebhook] RAW body: {_json.dumps(body, ensure_ascii=False)[:500]}")

    schema = body.get("schema", "")
    header = body.get("header", {})
    event = body.get("event", {})

    # URL 验证：飞书首次配置事件订阅时发送 challenge
    challenge = body.get("challenge")
    if challenge:
        logger.info("[FeishuWebhook] URL verification challenge received")
        from fastapi.responses import JSONResponse
        return JSONResponse(content={"challenge": challenge})

    # 事件推送处理
    event_type = header.get("event_type", "") or body.get("type", "")
    token = header.get("token", "")
    logger.info(f"[FeishuWebhook] event_type={event_type}, token={token[:8] if token else 'empty'}")

    from app.config import get_settings
    settings = get_settings()

    if settings.feishu_verification_token and token != settings.feishu_verification_token:
        logger.warning(f"[FeishuWebhook] Invalid verification token")
        raise HTTPException(status_code=403, detail="Invalid verification token")

    # 卡片按钮回调（card.action.trigger）：按 value.biz 路由，不走引擎消息分发
    if event_type == "card.action.trigger":
        return await _handle_card_action(event)

    from app.rpa.feishu_bot import _engine_registry, get_feishu_engine

    results = []
    active_engines = [(uid, eng) for uid, eng in _engine_registry.items() if eng.is_running]

    if not active_engines:
        default_user_id = "feishu_default"
        try:
            engine = get_feishu_engine(default_user_id)
            if not engine.is_running:
                await engine.start()
                from app.rpa.feishu_agent_bridge import get_or_create_bridge
                get_or_create_bridge(default_user_id)
                logger.info("[FeishuWebhook] Auto-started default engine for incoming event")
            active_engines = [(default_user_id, engine)]
        except Exception as e:
            logger.error(f"[FeishuWebhook] Failed to auto-start default engine: {e}")

    for user_id, engine in active_engines:
        try:
            result = await engine.handle_event(body)
            results.append({"user_id": user_id, "result": result})
        except Exception as e:
            logger.error(f"[FeishuWebhook] Event handling failed for user={user_id}: {e}")
            results.append({"user_id": user_id, "error": str(e)})

    return {"code": 0, "msg": "ok", "processed": len(results)}


# ==================== 控制接口 ====================

@router.post("/start")
async def start_service(
    request: StartRequest = None,
    user_id: str = Depends(get_current_user),
):
    """启动飞书机器人服务。"""
    try:
        engine = get_feishu_engine(user_id)

        if engine.is_running:
            return {
                "success": True,
                "data": engine.state.to_dict(),
                "message": "服务已在运行中",
            }

        await engine.start()

        get_or_create_bridge(user_id)

        return {
            "success": True,
            "data": engine.state.to_dict(),
            "message": "服务已启动",
        }

    except Exception as e:
        logger.error(f"[FeishuAPI] 启动服务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop")
async def stop_service(
    request: StopRequest = None,
    user_id: str = Depends(get_current_user),
):
    """停止飞书机器人服务。"""
    try:
        remove_bridge(user_id)

        engine = get_feishu_engine(user_id)
        await engine.stop()
        remove_feishu_engine(user_id)

        return {
            "success": True,
            "data": {"status": "stopped"},
            "message": "服务已停止",
        }

    except Exception as e:
        logger.error(f"[FeishuAPI] 停止服务失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
async def get_status(
    user_id: str = Depends(get_current_user),
):
    """查询飞书机器人状态。"""
    try:
        engine = get_feishu_engine(user_id)
        return {
            "success": True,
            "data": engine.state.to_dict(),
        }
    except Exception as e:
        logger.error(f"[FeishuAPI] 查询状态失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/send-message")
async def send_message(
    request: SendMessageRequest,
    user_id: str = Depends(get_current_user),
):
    """发送消息到飞书。"""
    try:
        engine = get_feishu_engine(user_id)

        if not engine.is_running:
            raise HTTPException(status_code=400, detail="服务未启动，请先调用 /start")

        result = await engine._client.send_text(
            receive_id=request.receive_id,
            text=request.content,
            receive_id_type=request.receive_id_type,
        )

        return {
            "success": True,
            "data": result,
            "message": "消息发送成功",
        }

    except FeishuAPIError as e:
        raise HTTPException(status_code=400, detail=f"飞书API调用失败[code={e.code}]: {e.msg}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FeishuAPI] 发送消息失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-document")
async def import_document(
    request: ImportDocumentRequest,
    user_id: str = Depends(get_current_user),
):
    """手动导入飞书文档到平台。"""
    try:
        engine = get_feishu_engine(user_id)

        if not engine.is_running:
            raise HTTPException(status_code=400, detail="服务未启动，请先调用 /start")

        result = await engine.import_document(request.document_id)

        return {
            "success": result.get("success", True),
            "data": result,
        }

    except FeishuAPIError as e:
        raise HTTPException(status_code=400, detail=f"飞书API调用失败[code={e.code}]: {e.msg}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FeishuAPI] 导入文档失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export-to-bitable")
async def export_to_bitable(
    request: ExportToBitableRequest,
    user_id: str = Depends(get_current_user),
):
    """手动导出数据到飞书多维表格。"""
    try:
        engine = get_feishu_engine(user_id)

        if not engine.is_running:
            raise HTTPException(status_code=400, detail="服务未启动，请先调用 /start")

        result = await engine.export_to_bitable(
            data=request.records,
            app_token=request.app_token,
            table_id=request.table_id,
        )

        return {
            "success": result.get("success", True),
            "data": result,
        }

    except FeishuAPIError as e:
        raise HTTPException(status_code=400, detail=f"飞书API调用失败[code={e.code}]: {e.msg}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[FeishuAPI] 导出到多维表格失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))