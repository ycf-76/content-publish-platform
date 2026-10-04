"""Chat Agent：用户消息 → 守卫 → ReAct Loop。

ReAct 模式：LLM 自己看工具列表、自己决定调什么、自己观察结果、自己决定是否继续。
不再有 TopPlanner 预先决定工具链——LLM 有完全的选择权和信任。
正则 fallback 只在 LLM 完全不可用时使用。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from app.engine.schemas import AgentOutput, LLMProtocol, WorkflowContext
from app.agents.input_rules import ChatInputRule
from app.agents.top_planner import ActionType, ParsedIntent, plan_to_action_type, plan_to_parsed_intent, _keyword_fallback
from app.agents.registry import AgentRegistry
from app.tools.context_vars import current_db_session

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    status: str
    intent: ParsedIntent | None = None
    output: AgentOutput | None = None
    message: str = ""
    card_draft: dict[str, Any] | None = None


class ChatAgent:
    """编排 Chat 请求：守卫 → ReAct Loop。"""

    def __init__(
        self,
        registry: AgentRegistry | None = None,
        input_rule: ChatInputRule | None = None,
        llm: LLMProtocol | None = None,
        emit_callback: Any = None,
    ) -> None:
        self._registry = registry or AgentRegistry()
        self._input_rule = input_rule or ChatInputRule()
        self._llm = llm
        self._emit_callback = emit_callback

    async def process(
        self,
        message: str,
        session_id: str,
        user_id: str,
        account_id: str = "",
        db: Any = None,
        workflow_id: str | None = None,
        agent_id: str | None = None,
        creation_type: str | None = None,
        extra_system_prompt: str | None = None,
        max_iterations: int | None = None,
        work_context: dict[str, Any] | None = None,
        auto_approve: bool = True,
    ) -> ChatResult:
        context = WorkflowContext(
            workflow_id=workflow_id or session_id,
            node_id="chat",
            user_id=user_id,
            account_id=account_id,
        )

        if not await self._input_rule.check_pre({"message": message}, context):
            return ChatResult(status="blocked", message="输入未通过安全校验")

        target_agent = agent_id or "chat_agent"
        try:
            harness = self._registry.build_harness(target_agent, workflow_id=workflow_id, creation_type=creation_type)
        except KeyError:
            if target_agent != "chat_agent":
                logger.warning(f"[ChatAgent] agent '{target_agent}' not found, falling back to chat_agent")
                try:
                    harness = self._registry.build_harness("chat_agent", workflow_id=workflow_id, creation_type=creation_type)
                except KeyError:
                    return await self._fallback_intent_route(message, context, workflow_id)
            else:
                return await self._fallback_intent_route(message, context, workflow_id)

        if self._llm is not None:
            harness.llm = self._llm

        if self._emit_callback is not None:
            from app.engine.harness.observer.observer import Observer
            harness.observer = Observer(emit_callback=self._emit_callback)
            logger.info("[ChatAgent] observer injected with real SSE emit callback")

        if not auto_approve:
            for tool_name, policy in harness.guardian._policies.items():
                if policy.needs_confirmation:
                    continue
                policy.auto_allow = False
                policy.needs_confirmation = True
            logger.info(f"[ChatAgent] auto_approve=False, all non-high-risk tools set to needs_confirm")

        if hasattr(context, "extra"):
            context.extra["auto_approve"] = auto_approve

        if max_iterations is not None:
            executor = getattr(harness, "executor", None)
            if executor is not None and hasattr(executor, "max_iterations"):
                executor.max_iterations = int(max_iterations)

        if harness.llm is not None:
            guidance = extra_system_prompt or ""
            return await self._agentic_loop(
                message, session_id, harness, context, db,
                plan_guidance=guidance,
            )

        return await self._fallback_intent_route(message, context, workflow_id)

    async def _generate_session_summary(
        self,
        session_id: str,
        recent_limit: int = 10,
        llm_override: Any = None,
    ) -> str | None:
        _llm = llm_override or self._llm
        if _llm is None:
            try:
                from app.agents.registry import AgentRegistry
                _harness = AgentRegistry().build_harness("chat_agent")
                _llm = _harness.llm
            except Exception:
                pass
        if _llm is None:
            logger.warning("[ChatAgent] no LLM available for summary generation")
            return None
        try:
            from app.services import chat_session
            all_messages = await chat_session.list_messages(session_id, limit=200)
            user_assistant_msgs = [
                m for m in all_messages
                if m["role"] in ("user", "assistant")
            ]
            if len(user_assistant_msgs) <= recent_limit:
                return None
            old_msgs = user_assistant_msgs[:-recent_limit]
            history_lines = []
            for m in old_msgs:
                role = "用户" if m["role"] == "user" else "助手"
                content = m["content"][:500]
                history_lines.append(f"{role}：{content}")
            history_text = "\n".join(history_lines)
            if not history_text.strip():
                return None
            summary_prompt = (
                "请将以下对话历史压缩为简洁但完整的摘要。必须保留：\n"
                "1. 用户的核心需求（要写什么主题、什么风格、什么平台）\n"
                "2. 关键决策和修改指令（用户要求改了什么、调整了什么）\n"
                "3. 已产出的文案标题和关键内容\n"
                "4. 用户的偏好和反馈（喜欢什么、不喜欢什么）\n"
                "不要丢失任何重要信息，但可以省略过程细节。\n"
                "摘要长度控制在 300-500 字。"
            )
            result = await _llm.chat(
                [
                    {"role": "system", "content": summary_prompt},
                    {"role": "user", "content": f"对话历史：\n{history_text}"},
                ],
                response_format=None,
            )
            summary = result.get("content", "").strip()
            if summary and len(summary) >= 20:
                return summary
        except Exception as e:
            logger.warning(f"[ChatAgent] session summary generation failed: {e}")
        return None

    async def _agentic_loop(
        self,
        message: str,
        session_id: str,
        harness: Any,
        context: WorkflowContext,
        db: Any,
        plan_guidance: str = "",
    ) -> ChatResult:
        """LLM 自主决策循环：思考 → 调 Skill → 观察 → 再思考 → 完成。"""

        token = current_db_session.set(db) if db is not None else None
        try:
            input_data = {"topic": message}

            _work_content = ""
            _other_guidance = ""
            if plan_guidance:
                if "【重要】当前用户正在查看以下作品" in plan_guidance:
                    _work_marker = plan_guidance.find("【重要】当前用户正在查看以下作品")
                    _work_content = plan_guidance[_work_marker:]
                    _other_guidance = plan_guidance[:_work_marker].strip()
                else:
                    _other_guidance = plan_guidance

            if _work_content:
                input_data["work_context_prompt"] = _work_content

            if _other_guidance:
                input_data["topic"] = f"用户请求：{message}\n\n执行计划与纪律：\n{_other_guidance}"

            if db is not None:
                # D18 创作者画像软注入：LLM 层（自由回复/追问也带画像调性）。
                # 读失败/无画像静默跳过，不拦 chat；走 profile_service TTL 缓存。
                try:
                    from app.services.profile_service import get_profile_cached

                    _profile = await get_profile_cached(db, context.user_id)
                    if _profile is not None:
                        input_data["profile_prompt"] = (
                            "[创作者画像 — 你作为该创作者 AI 搭档的身份与约束]\n"
                            + _profile.to_prompt_context()
                        )
                        logger.info(
                            f"[ChatAgent] profile injected: "
                            f"domain={_profile.primary_domain.value}"
                        )
                except Exception as _profile_err:
                    logger.debug(
                        f"[ChatAgent] profile soft-inject skipped: {_profile_err}"
                    )

                try:
                    from app.services import chat_session

                    creative_state = await chat_session.get_creative_state(session_id)
                    if creative_state:
                        _cs_parts = [f"[当前创作状态]"]
                        _phase = creative_state.get("phase", "idle")
                        _cs_parts.append(f"阶段: {_phase}")
                        _cr = creative_state.get("copywrite_result")
                        if _cr:
                            _cs_parts.append(
                                f"已有文案（可直接引用，无需重新生成）:\n"
                                f"  标题: {_cr.get('title', '')}\n"
                                f"  正文: {_cr.get('content', '')[:500]}\n"
                                f"  标签: {_cr.get('tags', [])}"
                            )
                            _ai_copywrite = (
                                f"【当前创作文案（以此为准，不要用原始作品正文）】\n"
                                f"标题: {_cr.get('title', '')}\n"
                                f"正文: {_cr.get('content', '')}\n"
                                f"标签: {', '.join(_cr.get('tags', []))}"
                            )
                            _existing_work_prompt = input_data.get("work_context_prompt", "")
                            input_data["work_context_prompt"] = (
                                f"{_existing_work_prompt}\n\n{_ai_copywrite}".strip()
                                if _existing_work_prompt
                                else _ai_copywrite
                            )
                        _cd = creative_state.get("card_draft")
                        if _cd:
                            _cs_parts.append(
                                f"已有图文草稿: {len(_cd.get('pages', []))}页"
                            )
                        input_data["creative_state_prompt"] = "\n".join(_cs_parts)
                        logger.info(f"[ChatAgent] creative_state loaded: phase={_phase}")

                    RECENT_LIMIT = 2

                    total_count = await chat_session.count_messages(session_id)
                    recent = await chat_session.get_recent_messages(
                        session_id, limit=RECENT_LIMIT, offset=1
                    )

                    summary_text = await chat_session.get_session_summary(session_id)
                    if summary_text:
                        logger.info(f"[ChatAgent] loaded summary ({len(summary_text)} chars) for session={session_id}")

                    if recent:
                        history_parts = []
                        if summary_text:
                            history_parts.append(f"[早期对话摘要]\n{summary_text}\n[摘要结束]")
                        for m in recent:
                            if m["role"] == "system":
                                pass
                            elif m["role"] == "user":
                                history_parts.append(f"用户：{m['content']}")
                            else:
                                _assistant_content = m['content']
                                history_parts.append(f"助手：{_assistant_content}")
                        history = "\n".join(history_parts)

                        if _other_guidance:
                            input_data["topic"] = f"用户请求：{message}\n\n执行计划与纪律：\n{_other_guidance}\n\n之前的对话：\n{history}"
                        else:
                            input_data["topic"] = f"之前的对话：\n{history}\n\n最新消息：{message}"

                    last_topic = await chat_session.get_last_workflow_topic(session_id)
                    if last_topic:
                        input_data["last_topic"] = last_topic
                except Exception as _ctx_err:
                    logger.warning(f"[ChatAgent._agentic_loop] context injection error: {_ctx_err}")

            start = time.time()
            output = await harness.run(input_data, context)
            duration_ms = int((time.time() - start) * 1000)
            output.duration_ms = duration_ms

            output_data = output.output or {}
            if output_data.get("_awaiting_clarification"):
                return ChatResult(
                    status="awaiting_clarification",
                    output=output,
                    message=output_data.get("_clarification_prompt", "需要确认创作偏好"),
                )
            if output_data.get("_awaiting_confirmation"):
                return ChatResult(
                    status="awaiting_confirmation",
                    output=output,
                    message=output_data.get("_confirmation_prompt", "需要确认操作"),
                )
            if output_data.get("workflow_id") or output_data.get("_workflow_started"):
                return ChatResult(
                    status="workflow_started",
                    output=output,
                    message=f"工作流已启动: {output_data.get('workflow_id', '')}",
                )
            return ChatResult(status="agent_output", output=output)

        except Exception as e:
            logger.warning(f"[ChatAgent] agentic loop failed, falling back to regex: {e}")
            return await self._fallback_intent_route(message, context, None)
        finally:
            try:
                await harness.shutdown()
            except Exception:
                pass
            if token is not None:
                current_db_session.reset(token)

    async def _fallback_intent_route(
        self,
        message: str,
        context: WorkflowContext,
        workflow_id: str | None = None,
    ) -> ChatResult:
        """LLM 不可用时的 fallback：正则意图 → 固定分支。"""

        plan = _keyword_fallback(message)
        intent = plan_to_parsed_intent(plan)
        action = plan_to_action_type(plan)

        if action == ActionType.CHAT:
            return ChatResult(status="chat", intent=intent)

        return ChatResult(
            status="chat", intent=intent,
            message="该操作需要 LLM 支持，当前 LLM 服务不可用，请稍后重试。",
        )