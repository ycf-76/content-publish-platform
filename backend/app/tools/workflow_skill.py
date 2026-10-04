"""StartWorkflowSkill: 让 LLM 能触发 DAG 全流程工作流。

当 LLM 判断用户需要「从选题到发布全搞定」时，调用此 Skill 启动 LangGraph DAG。
"""

from __future__ import annotations

import re

from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import Skill
from app.tools.registry import register


class StartWorkflowInput(BaseModel):
    topic: str = Field(..., description="工作流主题，如 AI教育")
    search_keyword: str | None = Field(
        default=None,
        description="搜索关键词，留空则用 topic",
    )
    creative_brief: str = Field(
        default="",
        description="创作方向/风格要求，如 轻松幽默风格",
    )
    model_settings: dict[str, Any] = Field(
        default_factory=dict,
        description="模型设置，如 enable_card_gen, enable_wechat_push, enable_feishu_push, card_style, wechat_target_user_id, feishu_chat_id",
    )


@register
class StartWorkflowSkill(Skill):
    """启动完整工作流：从选题到发布全流程。"""

    node_type = "workflow"
    name = "start_workflow"
    description = (
        "启动完整工作流：从选题到发布全流程。"
        "输入 topic（和可选 search_keyword、creative_brief、model_settings），返回 workflow_id。"
        "当用户要求发微信/飞书时，在 model_settings 中设置 enable_wechat_push=true / enable_feishu_push=true。"
    )
    input_schema = StartWorkflowInput

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        in_ = StartWorkflowInput.model_validate(inputs)

        _context = inputs.get("_context", {})
        _db_session = inputs.get("_db_session")

        user_id = getattr(_context, "user_id", "") if hasattr(_context, "user_id") else _context.get("user_id", "")
        account_id = getattr(_context, "account_id", "") if hasattr(_context, "account_id") else _context.get("account_id", "")

        if not _db_session:
            return {"ok": False, "error": "no db session available"}

        model_settings = dict(in_.model_settings)

        _auto_inject_push_flags(model_settings, inputs)

        try:
            from app.services.workflow import get_workflow_service

            service = get_workflow_service(_db_session)
            workflow = await service.start_workflow(
                user_id=user_id,
                account_id=account_id,
                topic=in_.topic,
                search_keyword=in_.search_keyword or in_.topic,
                creative_brief=in_.creative_brief,
                model_settings=model_settings,
                reference={},
                source="chat_agent",
            )
            return {
                "ok": True,
                "_workflow_started": True,
                "workflow_id": workflow.id,
                "topic": in_.topic,
                "message": f"工作流已启动: {workflow.id}",
            }
        except Exception as e:
            return {"ok": False, "error": f"启动工作流失败: {e}"}


def _auto_inject_push_flags(model_settings: dict, inputs: dict[str, Any]) -> None:
    """Chat 驱动时，LLM 通常不会主动传 enable_card_gen / enable_wechat_push 等开关。

    此函数根据三个信号源自动补全推送开关：
    1. context.extra["model_settings"] — 前端配置面板传入的设置（最高优先级）
    2. context.extra["intent_tools"] — Loop executor 注入的本轮 LLM 工具选择
    3. 用户原始消息关键词匹配 — 兜底，防止意图解析遗漏

    规则：
    - 前端已配置的设置优先使用，不覆盖
    - wechat_push / feishu_push / card_gen → 自动开启 card_gen
    - wechat_push → 自动开启 enable_wechat_push
    - feishu_push → 自动开启 enable_feishu_push
    """
    _context = inputs.get("_context", {})
    intent_tools: list[str] = []

    if hasattr(_context, "extra"):
        intent_tools = _context.extra.get("intent_tools", [])
        frontend_settings = _context.extra.get("model_settings", {})
        if frontend_settings:
            logger.info(f"[workflow_skill] merging frontend model_settings: {list(frontend_settings.keys())}")
            for key in ("enable_wechat_push", "wechat_target_user_id", "enable_feishu_push", "feishu_chat_id", "enable_card_gen"):
                if key in frontend_settings and key not in model_settings:
                    model_settings[key] = frontend_settings[key]
                    logger.info(f"[workflow_skill] applied frontend setting: {key}={frontend_settings[key]}")
    elif isinstance(_context, dict):
        intent_tools = _context.get("extra", {}).get("intent_tools", [])
        frontend_settings = _context.get("extra", {}).get("model_settings", {})
        if frontend_settings:
            logger.info(f"[workflow_skill] merging frontend model_settings (dict): {list(frontend_settings.keys())}")
            for key in ("enable_wechat_push", "wechat_target_user_id", "enable_feishu_push", "feishu_chat_id", "enable_card_gen"):
                if key in frontend_settings and key not in model_settings:
                    model_settings[key] = frontend_settings[key]

    tool_set = set(intent_tools)

    # 兜底：从用户原始消息关键词推断
    topic = str(inputs.get("topic", "") or "")
    if topic:
        if re.search(r"发.*微信|推.*微信|送.*微信", topic):
            tool_set.add("wechat_push")
        if re.search(r"发.*飞书|推.*飞书|送.*飞书|发到飞书", topic):
            tool_set.add("feishu_push")
        if re.search(r"卡片|图文", topic):
            tool_set.add("card_gen")

    if not tool_set:
        return

    needs_card = any(t in tool_set for t in ("wechat_push", "feishu_push", "card_gen"))
    if needs_card and "enable_card_gen" not in model_settings:
        model_settings["enable_card_gen"] = True

    if "wechat_push" in tool_set and "enable_wechat_push" not in model_settings:
        model_settings["enable_wechat_push"] = True

    if "feishu_push" in tool_set and "enable_feishu_push" not in model_settings:
        model_settings["enable_feishu_push"] = True