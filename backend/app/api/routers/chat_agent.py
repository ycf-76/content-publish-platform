"""Agent Chat 适配层端点（端到端闭环）。

流程：获取/创建 Session → 写用户消息 → 守卫 → 意图解析 → 触发工作流 →
写 assistant 消息（带 workflow_id）→ 发 intent_parsed → 返回 workflow_id。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_agent import ChatAgent
from app.agents.core.schemas import WorkflowContext
from app.agents.input_rules import ChatInputRule
from app.agents.intent_parser import ActionType, ParsedIntent, RuleBasedIntentParser
from app.api.deps import get_current_user
from app.db.session import get_db
from app.services import chat_session
from app.services.sse_bus import EVENT_AGENT_CHAT_ERROR, EVENT_INTENT_PARSED, sse_bus
from app.services.workflow import get_workflow_service

router = APIRouter(prefix="/api/v1/chat", tags=["chat_agent"])

_intent_parser = RuleBasedIntentParser()
_input_rule = ChatInputRule()


class AgentChatRequest(BaseModel):
    message: str = Field(..., max_length=10000)
    mode: str = Field(default="auto", pattern="^(auto|full_pipeline|chat)$")
    account_id: str | None = None
    session_id: str | None = None


def _intent_to_dict(intent: ParsedIntent) -> dict:
    return {
        "action": intent.action.value,
        "params": intent.params,
        "confidence": intent.confidence,
        "needs_confirmation": intent.needs_confirmation,
        "confirmation_prompt": intent.confirmation_prompt,
    }


@router.post("/agent")
async def agent_chat(
    request: AgentChatRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # 1. 获取或创建 Session
    if request.session_id:
        existing = await chat_session.get_session(request.session_id)
        if existing is None or existing["user_id"] != user_id:
            raise HTTPException(status_code=404, detail="会话不存在")
        session_id = request.session_id
    else:
        session = await chat_session.create_session(user_id)
        session_id = session["id"]

    # 2. 写用户消息
    await chat_session.add_message(session_id, "user", request.message)

    # 3. 输入守卫
    context = WorkflowContext(
        workflow_id="",
        node_id="chat",
        user_id=user_id,
        account_id=request.account_id or "",
    )
    if not await _input_rule.check_pre({"message": request.message}, context):
        await chat_session.add_message(
            session_id, "assistant", "输入未通过安全校验", {"workflow_status": "error"}
        )
        return {"session_id": session_id, "status": "blocked", "message": "输入未通过安全校验"}

    # 4. 意图解析
    intent = await _intent_parser.parse(request.message)

    # 5. 纯聊天兜底：不在这里回静态文本，前端拿到 status=chat 后走 /chat/completions（SSE）
    if intent.action == ActionType.CHAT:
        return {
            "session_id": session_id,
            "status": "chat",
            "intent": _intent_to_dict(intent),
            "fallback": "chat_completions",
        }

    # 5.5 单步/探索：search_only / analyze_only / explore → ChatAgent（LoopExecutor）
    if intent.action in (ActionType.SEARCH_ONLY, ActionType.ANALYZE_ONLY, ActionType.EXPLORE):
        agent = ChatAgent()
        result = await agent.process(request.message, session_id, user_id)
        await chat_session.add_message(
            session_id,
            "assistant",
            result.message,
            {
                "intent": _intent_to_dict(intent),
                "workflow_status": "completed" if result.output else "error",
            },
        )
        return {
            "session_id": session_id,
            "status": result.status,
            "intent": _intent_to_dict(intent),
            "output": result.output.output if result.output else None,
        }

    # 5.6 追问：换个风格/主题 → 读上次 topic 重跑
    if intent.action == ActionType.FOLLOW_UP:
        last_topic = await chat_session.get_last_workflow_topic(session_id)
        if not last_topic:
            await chat_session.add_message(
                session_id,
                "assistant",
                "当前会话没有可继续的工作流",
                {"intent": _intent_to_dict(intent)},
            )
            return {
                "session_id": session_id,
                "status": "follow_up",
                "intent": _intent_to_dict(intent),
                "message": "当前会话没有可继续的工作流",
            }

        workflow = await get_workflow_service(db).start_workflow(
            user_id=user_id,
            account_id=request.account_id or "",
            topic=last_topic,
            search_keyword=last_topic,
            creative_brief=intent.params.get("modifier", ""),
            model_settings={},
            reference={},
        )
        await chat_session.add_message(
            session_id,
            "assistant",
            "",
            {
                "workflow_id": workflow.id,
                "intent": _intent_to_dict(intent),
                "workflow_status": "running",
            },
        )
        await sse_bus.publish(
            workflow.id,
            EVENT_INTENT_PARSED,
            {
                "action": intent.action.value,
                "params": intent.params,
                "confidence": intent.confidence,
                "workflow_id": workflow.id,
            },
        )
        return {
            "session_id": session_id,
            "workflow_id": workflow.id,
            "status": "follow_up",
            "intent": _intent_to_dict(intent),
        }

    # 6. 全流程：触发现有 DAG，得到 workflow_id
    topic = str(intent.params.get("topic", request.message))
    try:
        service = get_workflow_service(db)
        workflow = await service.start_workflow(
            user_id=user_id,
            account_id=request.account_id or "",
            topic=topic,
            search_keyword=topic,
            creative_brief="",
            model_settings={},
            reference={},
        )
    except Exception as exc:
        # 并发超限等适配层错误
        await sse_bus.publish(
            "chat_agent",
            EVENT_AGENT_CHAT_ERROR,
            {"error_code": "start_workflow_failed", "message": str(exc), "recoverable": False},
        )
        raise HTTPException(status_code=500, detail=str(exc))

    workflow_id = workflow.id

    # 7. 写 assistant 消息（关联 workflow_id）
    agent_meta = {
        "workflow_id": workflow_id,
        "intent": _intent_to_dict(intent),
        "workflow_status": "running",
    }
    await chat_session.add_message(session_id, "assistant", "", agent_meta)

    # 8. 发 intent_parsed
    await sse_bus.publish(
        workflow_id,
        EVENT_INTENT_PARSED,
        {
            "action": intent.action.value,
            "params": intent.params,
            "confidence": intent.confidence,
            "workflow_id": workflow_id,
        },
    )

    # 9. 返回
    return {
        "session_id": session_id,
        "workflow_id": workflow_id,
        "status": "agent_output",
        "intent": _intent_to_dict(intent),
    }