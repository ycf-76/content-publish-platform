"""Loop executor (ReAct-style).

对应架构文档 4.3。与 SingleShotExecutor 相对：
- SingleShot：一次 LLM 调用 + 一次 Skills 集中执行，简单粗暴。
- Loop：多轮 LLM ↔ Tool 交替，LLM 自主决定下一步调哪个 Skill。
  每轮：build prompt → stream LLM → 解析 tool_calls → 权限门控 → 调 Skill
        → 把 observation 拼回对话 → 直到 LLM 给 final=true 或达 max_iterations。

红线：
- max_iterations 上限硬编码（默认 20，硬上限 80），防止 LLM 死循环。
- 每次调 Skill 前必须经过 permission_gate，被拒时把错误作为 observation 喂回 LLM，
  让 LLM 有机会改路子，而不是直接崩。
- 不直接调 MCP / LLM，所有外部能力经 Skill，所有 LLM 经 harness.llm。
- 不 import langgraph / fastapi。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from app.engine.harness.executor.base import ExecutorBase
from app.engine.governance.stream_retry import StreamRetryState, RetryAction
from app.engine.governance.token_budget import BudgetAction
from app.engine.governance.thread_store import ThreadEventType
from app.engine.governance.hooks import (
    EVENT_GOVERNANCE_BUDGET_WARNING,
    EVENT_GOVERNANCE_COMPACTION,
    EVENT_GOVERNANCE_CONTEXT_WINDOW,
    EVENT_GOVERNANCE_RETRY,
)
from app.engine.schemas import PermissionDeniedError
from app.engine.collab.agent_manager import AgentHandle, AgentStatus

if TYPE_CHECKING:
    from app.engine.harness.runtime import AgentHarness
    from app.engine.schemas import WorkflowContext

logger = logging.getLogger(__name__)


# 默认上限：覆盖「搜→分析→文案→审核→图片规划→图片生成→发布」等复杂场景。
_DEFAULT_MAX_ITER = 20
_MAX_ITER_HARD_CAP = 80
# loop 整体时间预算（秒）：LLM 慢或工具慢时防止请求无限拖。
# 旧值 110s 是为了抢在"客户端 120s 绝对超时"之前收尾，但前端已改为
# 空闲超时（有数据就续期），这个约束不再成立——110s 会把正常的长回复
# 多轮对话掐断（实测：GitHub 工具推荐这类长列表回复生成到一半被截断）。
_DEFAULT_TOTAL_TIMEOUT = 600.0

# 单次 LLM 调用（含队列排队等待）的总时长上限——仅用于非流式调用。
# 流式调用走 _STREAM_IDLE_TIMEOUT（有 chunk 就续期），这个上限只是绝对兜底。
_LLM_CALL_TIMEOUT = 180.0
# 流式调用的空闲超时：连续 N 秒无任何 chunk 才判定 LLM 挂死。
# 长回复只要还在吐字就不许掐——否则就是「输出到一半自动停止」。
_STREAM_IDLE_TIMEOUT = 180.0
# 流式调用的绝对上限（含排队 + 完整生成），防御性兜底
_LLM_STREAM_CEILING = 1800.0
_MONITORED_TOOLS = (
    "lively_girl",
    "elegant",
    "professional",
    "trending_search",
    "xhs_search",
    "viral_analysis",
    "content_audit",
    "image_plan",
    "image_gen",
    "file_read",
    "file_write",
)
_CLARIFY_TRIGGER_NODE_TYPES = {"produce", "create", "design", "generate", "copywrite", "card_design"}


class ThinkingTagDetector:
    """流式 <thinking>...</thinking> 标签检测器。

    状态机：outside → inside_thinking → outside
    - outside 状态：文本走 agent_message_delta
    - inside_thinking 状态：文本走 reasoning_delta
    - 跨状态边界：缓冲部分匹配的标签字符，确认后路由到正确通道

    用法：
        detector = ThinkingTagDetector()
        for chunk_text in stream:
            reasoning, content = detector.feed(chunk_text)
            if reasoning: emit_reasoning_delta(reasoning)
            if content: emit_agent_message_delta(content)
        reasoning, content = detector.flush()
        if reasoning: emit_reasoning_delta(reasoning)
        if content: emit_agent_message_delta(content)
    """

    OPEN_TAG = "<thinking>"
    CLOSE_TAG = "</thinking>"

    def __init__(self) -> None:
        self._inside = False
        self._buf = ""

    def feed(self, text: str) -> tuple[str, str]:
        """喂入一段流式文本，返回 (reasoning_text, content_text)。"""
        if self._buf:
            text = self._buf + text
            self._buf = ""

        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        i = 0
        n = len(text)

        while i < n:
            if self._inside:
                close_idx = text.find(self.CLOSE_TAG, i)
                if close_idx >= 0:
                    reasoning_parts.append(text[i:close_idx])
                    i = close_idx + len(self.CLOSE_TAG)
                    self._inside = False
                else:
                    partial_len = self._partial_match(text, i, self.CLOSE_TAG)
                    if partial_len > 0:
                        reasoning_parts.append(text[i:n - partial_len])
                        self._buf = text[n - partial_len:]
                        break
                    else:
                        reasoning_parts.append(text[i:])
                        break
            else:
                open_idx = text.find(self.OPEN_TAG, i)
                if open_idx >= 0:
                    content_parts.append(text[i:open_idx])
                    i = open_idx + len(self.OPEN_TAG)
                    self._inside = True
                else:
                    partial_len = self._partial_match(text, i, self.OPEN_TAG)
                    if partial_len > 0:
                        content_parts.append(text[i:n - partial_len])
                        self._buf = text[n - partial_len:]
                        break
                    else:
                        content_parts.append(text[i:])
                        break

        return "".join(reasoning_parts), "".join(content_parts)

    def flush(self) -> tuple[str, str]:
        """流结束时冲刷缓冲区中残留的部分匹配。

        关键：如果 _inside=False 且 buf 是 OPEN_TAG 的部分前缀
        （如 '<', '<t', '<thin' 等），说明 LLM 输出了一个不完整的
        <thinking> 标签——这不是用户想看到的内容，直接丢弃。
        """
        buf = self._buf
        self._buf = ""
        if not buf:
            return "", ""
        if self._inside:
            return buf, ""
        else:
            if buf and self.OPEN_TAG.startswith(buf):
                return "", ""
            return "", buf

    @staticmethod
    def _partial_match(text: str, start: int, tag: str) -> int:
        """检查 text[start:] 是否以 tag 的前缀结尾（跨 chunk 部分匹配）。

        返回部分匹配的长度（>0 表示有部分匹配，需要缓冲）。
        """
        remaining = text[start:]
        tlen = len(tag)
        rlen = len(remaining)
        for length in range(min(tlen - 1, rlen), 0, -1):
            if remaining[rlen - length:] == tag[:length]:
                return length
        return 0


class ClarificationTagDetector:
    """流式 <needs_clarification>...</needs_clarification> 标签检测器。

    同构 ThinkingTagDetector 的状态机方案。
    仅在 outside_thinking 状态下激活（thinking 内部的标签不触发澄清）。

    状态机：IDLE → PARTIAL_OPEN → TAG_OPEN → PARTIAL_CLOSE → TAG_CLOSE → IDLE

    TAG_CLOSE 时解析标签内结构化内容（question + options），
    组装 ClarificationBatch 供 LoopExecutor break + save + SSE 推送。

    用法：
        detector = ClarificationTagDetector()
        for chunk_text in stream:
            content, tag_content = detector.feed(chunk_text, is_inside_thinking=False)
            if content: emit_agent_message_delta(content)
            if tag_content: handle_clarification_tag(tag_content)
        content, tag_content = detector.flush()
    """

    OPEN_TAG = "<needs_clarification>"
    CLOSE_TAG = "</needs_clarification>"

    def __init__(self) -> None:
        self._inside = False
        self._buf = ""

    def feed(self, text: str, is_inside_thinking: bool = False) -> tuple[str, str]:
        """喂入一段流式文本，返回 (content_text, clarification_tag_content)。

        is_inside_thinking=True 时，所有文本作为 content 输出，不检测标签。
        """
        if is_inside_thinking:
            return text, ""

        if self._buf:
            text = self._buf + text
            self._buf = ""

        content_parts: list[str] = []
        tag_parts: list[str] = []
        i = 0
        n = len(text)

        while i < n:
            if self._inside:
                close_idx = text.find(self.CLOSE_TAG, i)
                if close_idx >= 0:
                    tag_parts.append(text[i:close_idx])
                    i = close_idx + len(self.CLOSE_TAG)
                    self._inside = False
                else:
                    partial_len = ThinkingTagDetector._partial_match(text, i, self.CLOSE_TAG)
                    if partial_len > 0:
                        tag_parts.append(text[i:n - partial_len])
                        self._buf = text[n - partial_len:]
                        break
                    else:
                        tag_parts.append(text[i:])
                        break
            else:
                open_idx = text.find(self.OPEN_TAG, i)
                if open_idx >= 0:
                    content_parts.append(text[i:open_idx])
                    i = open_idx + len(self.OPEN_TAG)
                    self._inside = True
                else:
                    partial_len = ThinkingTagDetector._partial_match(text, i, self.OPEN_TAG)
                    if partial_len > 0:
                        content_parts.append(text[i:n - partial_len])
                        self._buf = text[n - partial_len:]
                        break
                    else:
                        content_parts.append(text[i:])
                        break

        return "".join(content_parts), "".join(tag_parts)

    def flush(self) -> tuple[str, str]:
        """流结束时冲刷缓冲区中残留的部分匹配。

        如果 _inside=False 且 buf 是 OPEN_TAG 的部分前缀，丢弃。
        """
        buf = self._buf
        self._buf = ""
        if not buf:
            return "", ""
        if self._inside:
            return "", buf
        else:
            if buf and self.OPEN_TAG.startswith(buf):
                return "", ""
            return buf, ""

    @property
    def inside(self) -> bool:
        return self._inside


_AMBIGUOUS_L1_KEYWORDS = frozenset({
    "帮我做", "帮我写", "帮我生成", "帮我创作",
    "随便", "都行", "无所谓", "你看着办",
    "搞一个", "来一个", "整一个",
})


def _is_ambiguous(
    field_name: str,
    arguments: dict[str, Any],
    already_clarified: dict[str, Any],
) -> bool:
    """Ambiguous 判定（§2.3.1）：L1 关键词 + L2 字段缺失。

    L3 LLM 辅助判定留为可扩展接口（_is_ambiguous_llm），
    当前仅用 L1/L2 规则，延迟 0ms。
    """
    if field_name in already_clarified:
        return False

    field_value = arguments.get(field_name)
    if field_value and isinstance(field_value, str) and field_value.strip():
        for kw in _AMBIGUOUS_L1_KEYWORDS:
            if kw in field_value:
                return True
        if len(field_value.strip()) < 10:
            return True
        return False

    return True


class LoopExecutor(ExecutorBase):
    """ReAct 风格的循环执行器。

    期望 LLM 输出 JSON，结构：
      {
        "thought": "我需要先搜小红书",
        "tool_calls": [{"name": "xhs_search", "arguments": {...}}],
        "final": false
      }
    或最终：
      {
        "thought": "已经够了",
        "final": true,
        "output": {...最终节点输出...}
      }

    Skill 调用结果以 observation 形式回喂给 LLM：
      {role: "user", content: "[observation] xhs_search -> {json}"}
    """

    def __init__(self, max_iterations: int = _DEFAULT_MAX_ITER, total_timeout: float | None = None) -> None:
        self.max_iterations = min(_MAX_ITER_HARD_CAP, max(1, int(max_iterations)))
        self.total_timeout = total_timeout
        # 工具连续失败计数（单次请求生命周期内），用于连续失败熔断
        self._tool_fail_counts: dict[str, int] = {}
        self._pending_confirmation: dict[str, Any] | None = None
        self._pending_clarification: dict[str, Any] | None = None
        self._confirmation_state_path: str | None = None
        # Skill 智能路由：三层策略（分类路由 + trigger预筛 + 分组加载）
        from app.tools.skill_router import SkillRouter
        self._skill_router = SkillRouter(max_tools=self._MAX_TOOLS_FOR_LLM)
        self._selected_skills: list[Any] | None = None
        self._routing_result: Any | None = None

    async def execute(
        self,
        harness: AgentHarness,
        input: dict[str, Any],
        context: WorkflowContext,
        resume_messages: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if resume_messages is not None:
            messages = resume_messages
        else:
            _profile_prompt = (input or {}).get("profile_prompt", "")
            _main_system = self._system_prompt(harness, input, context)
            if _profile_prompt:
                _main_system += "\n\n" + _profile_prompt
            messages: list[dict[str, Any]] = [
                {"role": "system", "content": _main_system},
            ]
            _work_ctx_prompt = (input or {}).get("work_context_prompt", "")
            if _work_ctx_prompt:
                messages.append({"role": "system", "content": _work_ctx_prompt})
            _creative_state_prompt = (input or {}).get("creative_state_prompt", "")
            if _creative_state_prompt:
                messages.append({"role": "system", "content": _creative_state_prompt})
            _fork_context = (input or {}).get("fork_context", "")
            if _fork_context:
                messages.append({"role": "system", "content": _fork_context})
            messages.append({"role": "user", "content": self._initial_user_prompt(harness, input, context)})

        _active_skills_for_map = self._selected_skills or harness.skills
        skill_map = {getattr(s, "name", ""): s for s in _active_skills_for_map}
        total_token_usage = 0
        last_thought = ""
        final_output: dict[str, Any] | None = None
        _reasoning_pushed = False
        raw_topic = (input or {}).get("topic", "")
        called_tools = self._check_tools_already_called(messages, _MONITORED_TOOLS)

        # 整体时间预算：防止 LLM 慢/工具慢把请求无限拖到客户端超时
        _total_timeout = (
            self.total_timeout
            if self.total_timeout is not None
            else _DEFAULT_TOTAL_TIMEOUT
        )
        _deadline = time.monotonic() + _total_timeout

        # ThreadStore: record session start and create initial checkpoint
        # Ref: Codex thread.rs — every session starts with a checkpoint
        harness.thread_store.record(
            ThreadEventType.USER_INPUT,
            {"input": input, "role": harness.role},
        )
        await harness.thread_store.persist_checkpoint("session_start", messages)

        _max_iter = self.max_iterations

        for iteration in range(1, _max_iter + 1):
            # 时间预算检查：超限即停止，用已有进度兜底，避免请求被客户端超时掐断
            if time.monotonic() > _deadline:
                logger.warning(
                    f"[{context.node_id}] LoopExecutor exceeded total timeout "
                    f"({_total_timeout:.0f}s) at iteration {iteration}, stopping"
                )
                final_output = final_output or self._output_from_last_observation(messages)
                if not isinstance(final_output, dict) or final_output.get("error"):
                    # observation 是错误信息时不外泄，改用友好文案
                    final_output = {}
                final_output.setdefault("_loop_truncated", True)
                final_output.setdefault(
                    "summary",
                    f"任务执行超过 {_total_timeout:.0f} 秒时间预算，已停止。"
                    "以上是目前已完成的进度，如需继续请重新发送。",
                )
                break

            if iteration > 1 and (iteration % 5 == 0 or iteration == 2):
                await harness.observer.emit_progress(
                    context.node_id,
                    current=iteration,
                    total=_max_iter,
                    label=f"第 {iteration}/{_max_iter} 轮",
                )

            # Check inter-agent messages from sub-agents
            if hasattr(harness, "message_bus") and hasattr(harness, "agent_id"):
                try:
                    pending = await harness.message_bus.drain(harness.agent_id, limit=5)
                    for msg in pending:
                        if msg.get("message_type") == "result":
                            agent_name = msg.get("sender_id", "sub-agent")
                            content_msg = msg.get("content", "")
                            messages.append({
                                "role": "user",
                                "content": f"[sub-agent {agent_name} result] {content_msg}",
                            })
                except Exception:
                    pass

            # 方案C: 提醒LLM有子agent仍在运行，防止过早final=true
            _active_sub_pre = self._get_active_sub_agents(harness)
            if _active_sub_pre:
                _sub_names = [f"{h.name}(id={h.agent_id[:8]})" for h in _active_sub_pre]
                messages.append({
                    "role": "user",
                    "content": (
                        f"[coordination] 你有 {len(_active_sub_pre)} 个子任务仍在运行中"
                        f"（{_sub_names}）。"
                        f"请等待它们完成（调用 wait_agent）后再给出最终结论，"
                        f"不要在子任务结果到达之前返回 final=true。"
                    ),
                })

            try:
                content, token_usage, api_tool_calls, _reasoning_pushed, _clarify_tag_full = await self._call_llm_streaming(harness, messages, context, emit_delta=True)
            except Exception as _llm_err:
                _err_str = str(_llm_err).lower()
                _unrecoverable = any(kw in _err_str for kw in ["402", "401", "403", "payment", "insufficient balance", "unauthorized", "invalid api key"])
                if _unrecoverable:
                    logger.error(f"[{context.node_id}] Unrecoverable LLM error, terminating loop: {_llm_err}")
                    await harness.observer.emit(
                        context.node_id,
                        "agent_error",
                        {"error": str(_llm_err)[:500], "unrecoverable": True},
                    )
                    final_output = {
                        "error": str(_llm_err)[:500],
                        "unrecoverable": True,
                        "hint": "LLM 服务不可用（余额不足或认证失败），请检查 API 配置",
                    }
                    final_output["_token_usage"] = total_token_usage
                    final_output.setdefault("_last_thought", "")
                    final_output.setdefault("_iterations", iteration)
                    return final_output
                raise
            total_token_usage += token_usage or 0

            # ---- LLM 自主澄清：检测 <needs_clarification> 标签 ----
            if _clarify_tag_full:
                try:
                    _llm_clarify_data = self._parse_clarification_tag(_clarify_tag_full)
                    if _llm_clarify_data:
                        _llm_clarify_question = _llm_clarify_data.get("question", "LLM 请求进一步澄清")
                        _llm_clarify_options = _llm_clarify_data.get("options", [])
                        from app.agents.clarification_schema import ClarificationQuestion, ClarificationBatch, ClarifyOption, QuestionType
                        _llm_clarify_opts = [
                            ClarifyOption(label=str(o), value=str(o))
                            for o in _llm_clarify_options
                        ] if _llm_clarify_options else []
                        _llm_clarify_batch = ClarificationBatch(
                            batch_id=f"llm_clarify_{iteration}",
                            batch_index=0,
                            total_batches=1,
                            title=_llm_clarify_question,
                            description="LLM 在创作过程中请求进一步澄清",
                            questions=[
                                ClarificationQuestion(
                                    id=f"llm_q_{iteration}",
                                    source_skill="llm_autonomous",
                                    question=_llm_clarify_question,
                                    type=QuestionType.single_choice if _llm_clarify_opts else QuestionType.text_input,
                                    options=_llm_clarify_opts,
                                )
                            ],
                        )
                        state = {
                            "messages": [self._serialize_msg(m) for m in messages],
                            "iteration": iteration,
                            "max_iterations": self.max_iterations,
                            "pending_clarification": {
                                "_type": "clarification",
                                "name": "llm_autonomous",
                                "arguments": {},
                                "_clarification_batches": [_llm_clarify_batch.model_dump()],
                                "_clarification_prompt": _llm_clarify_question,
                            },
                            "skill_map_keys": list(skill_map.keys()),
                            "context_snapshot": {
                                "workflow_id": context.workflow_id,
                                "node_id": context.node_id,
                                "user_id": context.user_id,
                                "account_id": context.account_id,
                                "extra": getattr(context, "extra", {}),
                            },
                            "total_token_usage": total_token_usage,
                        }
                        _clarify_state_path = save_loop_state(
                            context.workflow_id or "chat",
                            state,
                            max_iterations=self.max_iterations,
                        )
                        final_output = {
                            "_awaiting_clarification": True,
                            "_clarification_prompt": _llm_clarify_question,
                            "_clarification_skill": "llm_autonomous",
                            "_clarification_arguments": {},
                            "_clarification_batches": [_llm_clarify_batch.model_dump()],
                            "_loop_state_path": _clarify_state_path,
                        }
                        try:
                            await harness.observer.emit(context.node_id, "agent_clarification_required", {
                                "clarification_prompt": _llm_clarify_question,
                                "clarification_skill": "llm_autonomous",
                                "clarification_batches": [_llm_clarify_batch.model_dump()],
                                "loop_state_path": _clarify_state_path,
                            })
                        except Exception:
                            logger.exception("[clarify] LLM 自主澄清 SSE 推送失败")
                        break
                except Exception as _clarify_parse_err:
                    logger.warning(f"[loop] LLM 自主澄清标签解析失败，当作普通文本: {_clarify_parse_err}")

            harness.thread_store.record(
                ThreadEventType.LLM_RESPONSE,
                {"iteration": iteration, "token_usage": token_usage},
            )

            if content:
                _parsed_for_thought = self._parse_step(content)
                if isinstance(_parsed_for_thought, dict):
                    _thought_text = _parsed_for_thought.get("thought", "")
                    if _thought_text and isinstance(_thought_text, str) and _thought_text.strip():
                        logger.info(f"[loop] iter={iteration} extracted thought from content (len={len(_thought_text.strip())}), emitting as reasoning_delta")
                        try:
                            await harness.observer.emit_reasoning_delta(context.node_id, _thought_text.strip())
                            _reasoning_pushed = True
                        except Exception:
                            pass

            tool_calls = []
            if api_tool_calls:
                for tc in api_tool_calls:
                    func = tc.get("function", {})
                    name = func.get("name", "")
                    try:
                        arguments = json.loads(func.get("arguments", "{}"))
                    except json.JSONDecodeError:
                        arguments = {}
                    tool_calls.append({"name": name, "arguments": arguments})
            elif content:
                # 兜底：模型把 tool_calls 写在正文 JSON 里（本 loop 自己的文档协议），
                # 而不是走 function calling。旧实现只认 api_tool_calls，
                # 导致"模型说要调工具，但没有任何人去执行"——流水线静默停摆。
                tool_calls = self._tool_calls_from_text(content)

            _tc_names = [tc.get('name') for tc in tool_calls]
            logger.info(
                f"[loop] iter={iteration} content={content[:120]} "
                f"tool_calls={_tc_names} "
                f"api_tool_calls_count={len(api_tool_calls)}"
            )

            if content and not tool_calls:
                last_thought = content

            if not tool_calls and content:
                _looks_like_plan = self._looks_like_plan_or_meta(content, tool_calls)

                parsed_step = self._parse_step(content)
                if isinstance(parsed_step, dict) and parsed_step.get("final") is True:
                    _active_sub = self._get_active_sub_agents(harness)
                    if _active_sub and iteration < _max_iter:
                        logger.warning(
                            f"[{context.node_id}] LLM returned final=true but "
                            f"{len(_active_sub)} sub-agents still active, "
                            f"waiting and injecting results before allowing exit"
                        )
                        await self._wait_and_inject_sub_agent_results(
                            harness, _active_sub, messages, timeout=60.0
                        )
                        continue
                    final_output = parsed_step.get("output")
                    if not isinstance(final_output, dict):
                        final_output = {"summary": str(final_output or "任务已完成")}
                    last_thought = str(parsed_step.get("thought") or "").strip()
                    break

                _summary_text = self._strip_internal_tags(content) if content else ""
                if _looks_like_plan:
                    if iteration < _max_iter:
                        required_tools = self._detect_required_tools(
                            self._latest_user_request(raw_topic or "")
                        )
                        retry_prompt = self._tool_retry_prompt(required_tools)
                        messages.append({"role": "assistant", "content": content})
                        messages.append({"role": "user", "content": retry_prompt})
                        continue
                    _summary_text = "任务已完成。"
                if not _summary_text:
                    _summary_text = "处理完成。"
                _summary_text = self._fix_card_html_markers(_summary_text)
                _active_sub = self._get_active_sub_agents(harness)
                if _active_sub and iteration < _max_iter:
                    logger.warning(
                        f"[{context.node_id}] LLM produced direct output but "
                        f"{len(_active_sub)} sub-agents still active, "
                        f"waiting and injecting results"
                    )
                    await self._wait_and_inject_sub_agent_results(
                        harness, _active_sub, messages, timeout=60.0
                    )
                    continue
                try:
                    await harness.observer.emit_agent_message_completed(context.node_id, _summary_text)
                except Exception:
                    pass
                final_output = {"summary": _summary_text}
                break

            if not tool_calls:
                if iteration < _max_iter:
                    messages.append({"role": "user", "content": "[system] 上一步返回为空。请检查已有工具结果，若任务已完成则提供总结，若需继续则调用工具。"})
                    continue
                final_output = {"raw_text": self._strip_internal_tags(content)}
                final_output = self._ensure_readable_output(final_output, last_thought)
                break

            # 原生 function calling 时 content 为空：把 tool_call 以 JSON 文本记入
            # 历史，否则确认恢复（resume_messages）后 LLM 看不到自己调过什么工具，
            # 只能重新发起同一调用 → 确认死循环。
            if content or not tool_calls:
                _clean_content = self._strip_internal_tags(content) if content else ""
                messages.append({"role": "assistant", "content": _clean_content or content})
            else:
                messages.append({
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "tool_calls": [
                                {
                                    "name": str(c.get("name") or ""),
                                    "arguments": c.get("arguments", {}),
                                }
                                for c in tool_calls
                            ]
                        },
                        ensure_ascii=False,
                    ),
                })

            # 把本轮 LLM 选择的工具名列表注入 context.extra，
            # 供 StartWorkflowSkill._auto_inject_push_flags 读取
            _round_tool_names = [str(c.get("name", "")).strip() for c in tool_calls if c.get("name")]
            if hasattr(context, "extra"):
                context.extra["intent_tools"] = _round_tool_names

            for call in tool_calls:
                tool_name = str(call.get("name") or "").strip()
                confirmation = None
                # 连续失败熔断：同一工具已连续失败 >= 3 次，直接拦截不再执行
                if self._tool_fail_counts.get(tool_name, 0) >= 3:
                    logger.warning(
                        f"[{context.node_id}] tool {tool_name} blocked after "
                        f"{self._tool_fail_counts[tool_name]} consecutive failures"
                    )
                    obs = json.dumps(
                        {
                            "error": "tool_blocked",
                            "tool": tool_name,
                            "permanent": True,
                            "message": (
                                f"工具 {tool_name} 已连续失败 3 次（疑似环境故障），"
                                "本次调用已被拦截。请改用其他工具完成任务，"
                                "或基于已有结果直接给出最终总结（final=true）。"
                            ),
                        },
                        ensure_ascii=False,
                    )
                else:
                    obs, confirmation = await self._execute_tool_call(
                        harness, context, skill_map, call
                    )
                    if confirmation is not None:
                        called_tools.add(tool_name)
                    elif not self._observation_is_error(obs):
                        called_tools.add(tool_name)
                        self._tool_fail_counts.pop(tool_name, None)  # 成功即清零
                    else:
                        _fail_n = self._tool_fail_counts.get(tool_name, 0) + 1
                        self._tool_fail_counts[tool_name] = _fail_n
                        if _fail_n >= 2:
                            # 注入 permanent 提示，阻止 LLM 继续换参数重试同一失败工具
                            try:
                                payload = json.loads(obs)
                                if isinstance(payload, dict):
                                    payload["permanent"] = True
                                    payload["hint"] = (
                                        f"工具 {tool_name} 已连续失败 {_fail_n} 次，"
                                        "不要再重试它。请改用其他工具，"
                                        "或基于已有结果直接给出最终总结（final=true）。"
                                    )
                                    obs = json.dumps(payload, ensure_ascii=False)
                            except (json.JSONDecodeError, TypeError):
                                pass
                # 回喂 LLM 前对错误 observation 脱敏：
                # 剔除 stdout/cmd/returncode 等内部细节，防止被复述进最终回复
                messages.append(
                    {
                        "role": "user",
                        "content": f"[observation] {self._sanitize_error_observation(obs)}",
                    }
                )
                if confirmation:
                    # Save loop state and break
                    from app.engine.harness.executor.loop_state import save_loop_state

                    _is_clarification = confirmation.get("_type") == "clarification"

                    state = {
                        "messages": messages,
                        "iteration": iteration,
                        "max_iterations": self.max_iterations,
                        "pending_skill_call": confirmation,
                        "skill_map_keys": list(skill_map.keys()),
                        "context_snapshot": {
                            "workflow_id": context.workflow_id,
                            "node_id": context.node_id,
                            "user_id": context.user_id,
                            "account_id": context.account_id,
                            "extra": getattr(context, "extra", {}),
                        },
                        "total_token_usage": total_token_usage,
                    }

                    if _is_clarification:
                        state["pending_clarification"] = confirmation
                        self._pending_clarification = confirmation

                    self._pending_confirmation = confirmation
                    self._confirmation_state_path = save_loop_state(
                        context.workflow_id or "chat",
                        state,
                        max_iterations=self.max_iterations,
                    )

                    if _is_clarification:
                        final_output = {
                            "_awaiting_clarification": True,
                            "_clarification_prompt": confirmation.get("_clarification_prompt", ""),
                            "_clarification_skill": confirmation.get("name", ""),
                            "_clarification_arguments": confirmation.get("arguments", {}),
                            "_clarification_batches": confirmation.get("_clarification_batches", []),
                            "_loop_state_path": self._confirmation_state_path,
                        }
                        try:
                            await harness.observer.emit(context.node_id, "agent_clarification_required", {
                                "clarification_prompt": confirmation.get("_clarification_prompt", ""),
                                "clarification_skill": confirmation.get("name", ""),
                                "clarification_batches": confirmation.get("_clarification_batches", []),
                                "loop_state_path": self._confirmation_state_path,
                            })
                        except Exception:
                            logger.exception("[clarify] SSE 推送澄清请求失败（POST 响应仍在）")
                    else:
                        final_output = {
                            "_awaiting_confirmation": True,
                            "_confirmation_prompt": confirmation.get("_confirmation_prompt", ""),
                            "_confirmation_skill": confirmation.get("name", ""),
                            "_confirmation_arguments": confirmation.get("arguments", {}),
                            "_loop_state_path": self._confirmation_state_path,
                        }
                        try:
                            await harness.observer.emit(context.node_id, "agent_confirm_required", {
                                "confirmation_prompt": confirmation.get("_confirmation_prompt", ""),
                                "confirmation_skill": confirmation.get("name", ""),
                                "loop_state_path": self._confirmation_state_path,
                            })
                        except Exception:
                            logger.exception("[confirm] SSE 推送确认请求失败（POST 响应仍在）")
                    # Break both loops
                    break
            else:
                # No confirmation, continue to next iteration
                continue
            # Confirmation was triggered, break outer loop
            break
        else:
            # 跑满 max_iterations 仍未 final：用最后一个工具的 observation 兜底
            logger.warning(
                f"[{context.node_id}] LoopExecutor hit max_iterations={self.max_iterations}, "
                "falling back to last observation as output"
            )
            final_output = final_output or self._output_from_last_observation(messages)
            if not isinstance(final_output, dict) or final_output.get("error"):
                # observation 是错误信息时不外泄，改用友好文案
                final_output = {}
            final_output.setdefault("_loop_truncated", True)
            final_output.setdefault(
                "summary",
                f"任务已执行 {iteration} 轮，但未收到 final 信号。"
                f"最后状态：{last_thought or '无思考记录'}",
            )

        if not isinstance(final_output, dict):
            final_output = {"value": final_output}

        final_output["_token_usage"] = total_token_usage
        final_output.setdefault("_last_thought", last_thought)
        final_output.setdefault("_iterations", iteration)

        try:
            await harness.observer.emit_reasoning_completed(context.node_id, [last_thought] if last_thought else [])
        except Exception:
            pass

        return final_output

    # ------------------------------------------------------------------
    # sub-agent coordination guards (方案B + 方案C)
    # ------------------------------------------------------------------

    _SUB_AGENT_WAIT_TIMEOUT = 60.0

    @staticmethod
    def _get_active_sub_agents(harness: AgentHarness) -> list[AgentHandle]:
        """返回当前仍在运行或等待中的子agent列表。"""
        try:
            if not hasattr(harness, "agent_manager"):
                return []
            manager = harness.agent_manager
            return [
                h for h in manager.list_agents()
                if h.status in (AgentStatus.RUNNING, AgentStatus.PENDING)
                and h.agent_id != getattr(harness, "agent_id", "")
            ]
        except Exception:
            return []

    async def _wait_and_inject_sub_agent_results(
        self,
        harness: AgentHarness,
        active_agents: list[AgentHandle],
        messages: list[dict[str, Any]],
        timeout: float = 60.0,
    ) -> None:
        """等待活跃子agent完成，将结果回注到messages供LLM下一轮使用。

        这是方案B的核心：拦截final=true后，等待子agent结果，
        以observation形式注入对话历史，让LLM在下一轮看到完整数据后重新决策。
        """
        _timeout = max(5.0, min(120.0, timeout))
        logger.info(
            f"[sub-agent-guard] waiting for {len(active_agents)} active sub-agents "
            f"(timeout={_timeout}s)"
        )

        try:
            await harness.observer.emit_progress(
                getattr(harness, "agent_id", "loop"),
                current=0,
                total=len(active_agents),
                label=f"等待 {len(active_agents)} 个子任务完成...",
            )
        except Exception:
            pass

        wait_results = await asyncio.gather(
            *(
                asyncio.wait_for(h.wait(timeout=_timeout), timeout=_timeout + 5.0)
                for h in active_agents
            ),
            return_exceptions=True,
        )

        _completed = 0
        _timed_out = 0
        _errored = 0
        for agent, result in zip(active_agents, wait_results):
            if isinstance(result, Exception):
                _timed_out += 1
                logger.warning(
                    f"[sub-agent-guard] sub-agent {agent.name}({agent.agent_id[:8]}) "
                    f"wait failed: {result}"
                )
                messages.append({
                    "role": "user",
                    "content": (
                        f"[sub-agent {agent.name} timeout] "
                        f"子任务 '{agent.name}' 等待超时（{_timeout:.0f}s），"
                        f"其结果不可用。请基于已有信息继续。"
                    ),
                })
                continue

            if agent.status == AgentStatus.COMPLETED:
                _completed += 1
                _result_text = ""
                if isinstance(agent.result, dict):
                    try:
                        _result_text = json.dumps(agent.result, ensure_ascii=False)[:3000]
                    except Exception:
                        _result_text = str(agent.result)[:3000]
                elif agent.result is not None:
                    _result_text = str(agent.result)[:3000]
                messages.append({
                    "role": "user",
                    "content": (
                        f"[sub-agent {agent.name} completed] "
                        f"子任务 '{agent.name}' 已完成，结果如下：\n{_result_text}"
                    ),
                })
            elif agent.status == AgentStatus.ERROR:
                _errored += 1
                messages.append({
                    "role": "user",
                    "content": (
                        f"[sub-agent {agent.name} error] "
                        f"子任务 '{agent.name}' 执行出错：{agent.error or '未知错误'}。"
                        f"请基于已有信息继续。"
                    ),
                })
            else:
                _timed_out += 1
                messages.append({
                    "role": "user",
                    "content": (
                        f"[sub-agent {agent.name} still_running] "
                        f"子任务 '{agent.name}' 仍在运行（状态={agent.status.value}），"
                        f"等待超时。请基于已有信息继续。"
                    ),
                })

        logger.info(
            f"[sub-agent-guard] wait complete: "
            f"completed={_completed}, timed_out={_timed_out}, errored={_errored}"
        )

        messages.append({
            "role": "user",
            "content": (
                f"[coordination] 以上是 {len(active_agents)} 个子任务的执行结果。"
                f"请综合所有子任务结果和已有信息，重新给出你的最终结论。"
                f"如果还需要更多信息，可以继续调用工具；否则返回 final=true。"
            ),
        })

    # ------------------------------------------------------------------
    # prompt 构建
    # ------------------------------------------------------------------

    _BEHAVIOR_TEMPLATE_CACHE: str | None = None

    @classmethod
    def _load_behavior_template(cls) -> str:
        """Load BEHAVIOR.md once and cache for the process lifetime."""
        if cls._BEHAVIOR_TEMPLATE_CACHE is not None:
            return cls._BEHAVIOR_TEMPLATE_CACHE
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent.parent.parent / "agents" / "prompts" / "BEHAVIOR.md"
        if p.exists():
            cls._BEHAVIOR_TEMPLATE_CACHE = p.read_text(encoding="utf-8")
        else:
            logger.warning(f"[loop] BEHAVIOR.md not found at {p}, using inline fallback")
            cls._BEHAVIOR_TEMPLATE_CACHE = (
                "You are an AI assistant with access to tools.\n\n"
                "AVAILABLE TOOLS:\n{skill_lines}\n\n"
                "TOOL USE PHILOSOPHY — TRUST YOUR OWN JUDGMENT:\n"
                "- You decide whether to call a tool or respond directly.\n"
                "- If a tool clearly matches the user's need, call it. If no tool fits, respond directly.\n\n"
                "{skill_guidance_block}"
                "WHEN TO STOP:\n"
                "- If you have called the needed tools and got results, STOP and summarize.\n\n"
                "OUTPUT FORMAT:\n"
                "- Your final text response is shown DIRECTLY to the user.\n"
                "- If you need to reason before answering, put reasoning inside <thinking>...</thinking> tags.\n\n"
                "REMINDER (every turn):\n"
                "- Before responding, check the AVAILABLE TOOLS list above. If a tool matches the user's need, call it.\n"
            )
        return cls._BEHAVIOR_TEMPLATE_CACHE

    _NODE_TYPE_LABELS: dict[str, str] = {
        "copywrite": "文案创作",
        "image_gen": "图片生成",
        "topic_evaluator": "选题评估",
        "quality_gate": "质量审核",
        "trending_search": "热点搜索",
        "xhs_search": "小红书搜索",
        "analyze": "分析",
        "audit": "审核",
        "publish": "发布",
        "xhs_publish": "小红书发布",
        "wechat": "微信",
        "feishu": "飞书",
        "browser": "浏览器",
        "dev": "开发工具",
        "file": "文件操作",
        "workflow": "工作流",
    }

    @staticmethod
    def _build_skill_routing(skills: list[Any]) -> str:
        """从已注册 Skill 动态生成场景路由表（旧版，已被 SkillRouter 替代）。

        保留作为 fallback：当 SkillRouter 不可用时仍可使用此方法。
        """
        if not skills:
            return "- (当前无可用工具，直接回答用户问题)"

        grouped: dict[str, list[Any]] = {}
        for s in skills:
            nt = getattr(s, "node_type", "other") or "other"
            grouped.setdefault(nt, []).append(s)

        lines: list[str] = []
        for nt, group in sorted(grouped.items()):
            label = LoopExecutor._NODE_TYPE_LABELS.get(nt, nt)
            for s in group:
                name = getattr(s, "name", "?")
                display = getattr(s, "display_name", "") or name
                desc = getattr(s, "description", "") or ""
                triggers = getattr(s, "trigger_words", []) or []
                short_desc = desc[:80] + "…" if len(desc) > 80 else desc
                line = f"- **{display}** (`{name}`): {short_desc}"
                if triggers:
                    trigger_str = "、".join(f"「{t}」" for t in triggers[:5])
                    line += f"  — 触发词：{trigger_str}"
                lines.append(line)

        return "\n".join(lines)

    def _system_prompt(self, harness: AgentHarness, input: dict[str, Any] | None = None, context: WorkflowContext | None = None) -> str:
        def _skill_desc(s: Any) -> str:
            """Build a tool description line with parameter details."""
            base = f"- {s.name}: {s.description}"
            schema_cls = getattr(s, "input_schema", None)
            if schema_cls is None or schema_cls is BaseModel:
                return base
            try:
                schema = schema_cls.model_json_schema()
                props = schema.get("properties", {})
                required = set(schema.get("required", []))
                if not props:
                    return base
                param_parts = []
                for pname, pdef in props.items():
                    ptype = pdef.get("type", "any")
                    pdesc = pdef.get("description", "")
                    req_flag = " (required)" if pname in required else " (optional)"
                    if pdesc:
                        param_parts.append(f"    - {pname}: {ptype}{req_flag} — {pdesc}")
                    else:
                        param_parts.append(f"    - {pname}: {ptype}{req_flag}")
                return base + "\n" + "\n".join(param_parts)
            except Exception:
                return base

        skill_lines = "\n".join(_skill_desc(s) for s in harness.skills) or "- (no tools available)"
        role_block = ""
        if harness.prompt_template:
            tmpl = harness.prompt_template
            if input and context:
                try:
                    tmpl = tmpl.format(**{**input, **context.model_dump()})
                except (KeyError, IndexError) as _fmt_err:
                    logger.debug(
                        f"[{context.node_id}] prompt template format partial miss: {_fmt_err}"
                    )

            raw_topic_early = (input or {}).get("topic", "")
            user_msg_early = self._latest_user_request(raw_topic_early) or raw_topic_early

            self._routing_result = self._skill_router.select_skills(harness.skills, user_msg_early)
            self._selected_skills = self._routing_result.selected_skills

            _routing_hint = ""
            if self._routing_result.trigger_matched_skills:
                _matched_names = self._routing_result.trigger_matched_skills
                _routing_hint = (
                    f"\n> 当前请求可能涉及：{', '.join(f'`{n}`' for n in _matched_names)}"
                    f"（已在上方目录中标注，可优先考虑）"
                )
                logger.info(
                    f"[loop] skill_router: trigger_matched={self._routing_result.trigger_matched_skills}, "
                    f"categories={self._routing_result.trigger_matched_categories}, "
                    f"selected={self._routing_result.total_selected}/{self._routing_result.total_available}"
                )

            _callable_names = getattr(self, "_callable_skill_names", None)
            _compact_catalog = self._skill_router.build_compact_catalog(
                harness.skills, callable_names=_callable_names,
            )

            _skill_routing = _compact_catalog + _routing_hint
            _category_hint = self._routing_result.category_hint
            if _category_hint:
                _skill_routing = f"{_category_hint}\n\n{_skill_routing}"

            if "{skill_routing}" in tmpl:
                tmpl = tmpl.replace("{skill_routing}", _skill_routing)
            else:
                logger.warning(
                    f"[{context.node_id}] AGENTS.md missing {{skill_routing}} placeholder, "
                    f"dynamic tool routing not injected"
                )
            role_block = tmpl + "\n\n"

        raw_topic = (input or {}).get("topic", "")

        user_msg = self._latest_user_request(raw_topic) or raw_topic

        _skill_guidance_block = ""
        for s in harness.skills:
            guidance = getattr(s, "prompt_guidance", "") or ""
            if guidance:
                _skill_guidance_block += guidance + "\n\n"

        _behavior_template = self._load_behavior_template()
        behavior_block = (
            _behavior_template
            .replace("{skill_lines}", skill_lines)
            .replace("{skill_guidance_block}", _skill_guidance_block)
        )

        from app.agents.prompts.references.design_system_injector import build_design_system_block
        _creation_type = None
        if input and isinstance(input, dict):
            _creation_type = input.get("creation_type")
        _design_block = build_design_system_block(
            user_message=user_msg,
            creation_type=_creation_type,
            mode="summary",
        )

        return (
            f"{role_block}"
            f"{behavior_block}"
            f"{_design_block}\n\n"
            f"[USER REQUEST — DO NOT LOSE THIS]: {user_msg}\n"
        )

    def _initial_user_prompt(
        self,
        harness: AgentHarness,
        input: dict[str, Any],
        context: WorkflowContext,
    ) -> str:
        base = input.get("topic", json.dumps(input, ensure_ascii=False))
        if harness.memory:
            mem = harness.memory.to_dict()
            if mem:
                base += "\n\n[memory]\n" + json.dumps(mem, ensure_ascii=False, default=str)
        return base

    _MAX_TOOLS_FOR_LLM = 65

    def _build_tools_schema(self, harness: AgentHarness) -> list[dict[str, Any]]:
        """Convert skills to OpenAI function calling tools format.

        全量 skills 注入，按 triggered → hot → rest 排序，
        截断时按 priority 段硬截（cold 先丢，warm 次之），确保 catalog 与 tools 一致。
        """
        skills = harness.skills
        _collab_names_in_skills = [s.name for s in skills if s.name in ("spawn_agent", "wait_agent", "send_message", "interrupt_agent", "list_agents")]
        if _collab_names_in_skills:
            logger.info(f"[loop] collab tools registered in skills: {_collab_names_in_skills}")
        else:
            logger.warning(f"[loop] NO collab tools in skills! total_skills={len(skills)}, skill_names={[s.name for s in skills[:10]]}... collab_mode={getattr(harness, 'collab_mode', '?')}")
        tools = []
        for s in skills:
            schema_cls = getattr(s, "input_schema", None)
            parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
            if schema_cls is not None and schema_cls is not BaseModel:
                try:
                    schema = schema_cls.model_json_schema()
                    parameters = {
                        "type": "object",
                        "properties": schema.get("properties", {}),
                        "required": schema.get("required", []),
                    }
                except Exception:
                    pass
            tools.append({
                "type": "function",
                "function": {
                    "name": getattr(s, "name", ""),
                    "description": getattr(s, "description", ""),
                    "parameters": parameters,
                },
            })

        if len(tools) > self._MAX_TOOLS_FOR_LLM:
            from app.tools.skill_router import infer_priority, infer_category, SkillPriority, SkillCategory

            _triggered_names = set()
            if self._routing_result:
                _triggered_names = set(self._routing_result.trigger_matched_skills)

            _cold_names: set[str] = set()
            _warm_names: set[str] = set()
            _hot_names: set[str] = set()
            for s in skills:
                pri = infer_priority(s)
                name = getattr(s, "name", "")
                if pri == SkillPriority.COLD:
                    _cold_names.add(name)
                elif pri == SkillPriority.WARM:
                    _warm_names.add(name)
                else:
                    _hot_names.add(name)

            _triggered = [t for t in tools if t["function"]["name"] in _triggered_names]
            _hot = [t for t in tools if t["function"]["name"] in _hot_names and t["function"]["name"] not in _triggered_names]
            _warm = [t for t in tools if t["function"]["name"] in _warm_names and t["function"]["name"] not in _triggered_names]
            _cold = [t for t in tools if t["function"]["name"] in _cold_names]

            def _dedup_by_name(tool_list: list[dict]) -> list[dict]:
                seen: set[str] = set()
                out: list[dict] = []
                for t in tool_list:
                    n = t["function"]["name"]
                    if n not in seen:
                        seen.add(n)
                        out.append(t)
                return out

            tools = _dedup_by_name(_triggered + _hot + _warm + _cold)

            if len(tools) > self._MAX_TOOLS_FOR_LLM:
                _cold_budget = max(0, self._MAX_TOOLS_FOR_LLM - len(_triggered) - len(_hot) - len(_warm))
                if _cold_budget < len(_cold):
                    _cold = _cold[:_cold_budget]
                    tools = _dedup_by_name(_triggered + _hot + _warm + _cold)

                if len(tools) > self._MAX_TOOLS_FOR_LLM:
                    _warm_budget = max(0, self._MAX_TOOLS_FOR_LLM - len(_triggered) - len(_hot))
                    if _warm_budget < len(_warm):
                        _warm = _warm[:_warm_budget]
                        tools = _dedup_by_name(_triggered + _hot + _warm)

            logger.info(
                f"[loop] skill_router: tools_count={len(skills)} exceeds max={self._MAX_TOOLS_FOR_LLM}, "
                f"truncated to {len(tools)} (triggered→hot→warm→cold, cold/warm trimmed first)"
            )

        self._callable_skill_names = frozenset(t["function"]["name"] for t in tools)
        return tools

    @staticmethod
    def _latest_user_request(raw_topic: str) -> str:
        """Extract the latest user message from a ChatAgent-built topic string."""
        if not isinstance(raw_topic, str):
            return ""
        text = raw_topic.strip()

        if "最新消息：" in text:
            return text.split("最新消息：", 1)[1].strip()
        if "用户请求：" in text:
            tail = text.split("用户请求：", 1)[1]
            for marker in ("\n\n执行计划与纪律：", "\n\n之前的对话：", "\n\n执行计划与纪律", "\n\n之前的对话"):
                if marker in tail:
                    tail = tail.split(marker, 1)[0]
                    break
            return tail.strip()
        return text

    @staticmethod
    def _is_action_intent_text(text: str) -> bool:
        """Minimal safety rail: detect obvious action intent.

        Primary routing is done by LLM function calling + tool descriptions.
        This is only a fallback for when LLM returns content without tool_calls
        but the user clearly wanted an action.
        """
        if not isinstance(text, str) or not text.strip():
            return False
        import re
        stripped = text.strip()
        if re.search(r'(?:分析|拆解|点评|诊断|评估|评价|看看|能不能|行不行|试试|好的|不行)', stripped):
            return False
        return bool(re.search(
            r'^(?:重新|帮我|给我|请|来|出|做|写|改|调|搜|启动|生成|创建|完善|优化)'
            r'|/'
            r'|(?:图文|组图|发布|搜索|生成|出一[期篇]|来一[期篇])',
            stripped,
            re.IGNORECASE,
        ))

    @staticmethod
    def _is_action_intent(input: dict[str, Any]) -> bool:
        msg = (input or {}).get("topic", "")
        if not isinstance(msg, str):
            return False
        return LoopExecutor._is_action_intent_text(
            LoopExecutor._latest_user_request(msg)
        )

    @staticmethod
    def _required_tools_for_request(
        latest_request: str,
        raw_topic: str,
    ) -> set[str]:
        """Minimal safety rail: required tools when LLM forgot to call them.

        Primary routing is done by LLM function calling + tool descriptions.
        This is only a fallback for obvious cases where the LLM clearly
        should have called a tool but didn't.
        """
        import re
        latest = latest_request or ""
        context_text = f"{raw_topic}\n{latest}"

        if re.search(r'分析|拆解|点评|诊断|看看|能不能|行不行', latest):
            return set()

        if re.search(r'基于|按照|参照|根据|仿照|沿用|照着|参考', latest) and re.search(r'写|做|生成|出|来', latest):
            return set()

        if re.search(r'[搜找]热点|[搜找]趋势|[搜找]竞品', latest):
            return {"trending_search", "xhs_search", "viral_analysis"}

        return set()

    # 计划/过程性话术标记：短文本含其一才视为 plan/meta（纯结论句是合法总结）
    _PLAN_MARKERS = (
        "我来", "我会", "我将", "让我", "正在", "接下来",
        "计划", "准备", "步骤", "首先", "第一步", "我需要",
        "let me", "I will", "I'll", "I am going to", "now I",
        "next I", "first I", "step 1", "I need to",
    )

    @staticmethod
    def _strip_internal_tags(text: str) -> str:
        """清理 LLM 输出中的内部标签（thinking / needs_clarification）。

        这些标签的内容通过独立通道展示（reasoning 字段 / 澄清卡片），
        不应出现在最终消息正文或摘要中。
        """
        import re
        if not text:
            return ""
        # 保护代码块中的内容不被误删
        code_blocks: list[str] = []
        cleaned = text
        cleaned = re.sub(r'```[\s\S]*?```', lambda m: (
            code_blocks.append(m.group()) or f'\x00CB{len(code_blocks) - 1}\x00'
        ), cleaned)
        # <thinking> 标签
        cleaned = re.sub(r'<thinking>[\s\S]*?</thinking>', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<thinking>[\s\S]*$', '', cleaned, flags=re.IGNORECASE)
        # <needs_clarification> 标签
        cleaned = re.sub(r'<needs_clarification>[\s\S]*?</needs_clarification>', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<needs_clarification>[\s\S]*$', '', cleaned, flags=re.IGNORECASE)
        # 恢复代码块
        cleaned = re.sub(r'\x00CB(\d+)\x00', lambda m: code_blocks[int(m.group(1))], cleaned)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    @staticmethod
    def _fix_card_html_markers(text: str) -> str:
        """Auto-fix: if LLM wrapped card HTML in markdown code block instead of
        <!--card-html--> markers, convert it so the frontend can render cards.

        Handles patterns like:
          ```html ... <!DOCTYPE html>...</html> ... ```
          ``` ... <!DOCTYPE html>...</html> ... ```

        Also handles bare <!DOCTYPE html>...</html> without any wrapping.
        Processes ALL matches, not just the first one.
        """
        if "<!--card-html-->" in text:
            return text
        import re

        fixed = text
        pattern = re.compile(
            r"```(?:html)?\s*\n(.*?<!DOCTYPE\s+html>.*?</html>.*?)\n```",
            re.DOTALL | re.IGNORECASE,
        )
        matches = list(pattern.finditer(fixed))
        if matches:
            for match in reversed(matches):
                html_content = match.group(1).strip()
                replacement = f"<!--card-html-->\n{html_content}\n<!--/card-html-->"
                fixed = fixed[:match.start()] + replacement + fixed[match.end():]
            logger.info(f"[loop] auto-fixed: {len(matches)} markdown html code block(s) -> <!--card-html--> marker(s)")
            return fixed

        bare_pattern = re.compile(
            r"(<!DOCTYPE\s+html>.*?</html>)",
            re.DOTALL | re.IGNORECASE,
        )
        bare_matches = list(bare_pattern.finditer(fixed))
        if bare_matches:
            for match in reversed(bare_matches):
                html_content = match.group(1).strip()
                replacement = f"<!--card-html-->\n{html_content}\n<!--/card-html-->"
                fixed = fixed[:match.start()] + replacement + fixed[match.end():]
            logger.info(f"[loop] auto-fixed: {len(bare_matches)} bare HTML block(s) -> <!--card-html--> marker(s)")
            return fixed

        return text

    @staticmethod
    def _looks_like_plan_or_meta(text: str, tool_calls: list | None = None) -> bool:
        """Detect natural-language planning that should never be shown as a result.

        Codex approach: if LLM produced tool_calls, it's an action turn (not meta).
        If no tool_calls and content is not structured JSON, it's meta commentary.
        This replaces keyword-list matching with structural signals.

        补充：纯结构信号（短文本+非 JSON）会把"已为你重新生成…"这类结论句
        误判成 plan，导致合法总结被替换成"任务已完成。"。
        因此短文本还需命中过程性话术标记才算 plan。
        """
        if not isinstance(text, str) or not text.strip():
            return False
        if tool_calls:
            return False
        try:
            import json
            json.loads(text.strip())
            return False
        except (json.JSONDecodeError, ValueError):
            pass
        if text.strip().startswith(("#", "##", "- ", "* ")):
            return False
        if len(text.strip()) >= 120:
            return False
        return any(m in text for m in LoopExecutor._PLAN_MARKERS)

    @staticmethod
    def _tool_retry_prompt(required_tools: set[str]) -> str:
        if required_tools:
            target = "、".join(sorted(required_tools))
            return (
                "[system] 上一条回复只是计划文本，不是结果。"
                f"当前请求必须真正调用工具：{target}。"
                "不要输出“我来”“我会调用”“我直接写 brief”这类过程句，"
                "现在立即通过 function calling 调用对应工具，并传入完整参数。"
            )
        return (
            "[system] 上一条回复只是计划文本，不是结果。"
            "当前请求需要执行动作，不要只用文字回复。"
            "现在立即通过 function calling 调用对应工具，并传入完整参数。"
        )

    @staticmethod
    def _observation_is_error(observation: str) -> bool:
        """Return True when an observation is an explicit tool failure."""
        if not isinstance(observation, str) or not observation.strip():
            return False
        try:
            payload = json.loads(observation)
        except json.JSONDecodeError:
            return False
        if not isinstance(payload, dict):
            return False
        return bool(payload.get("error") or payload.get("tool_failed"))

    # 错误 observation 中只对排查有用的内部细节字段，回喂 LLM 前剔除
    # （含本地路径/进程输出，进入 LLM 上下文后容易被复述到最终回复）
    _OBS_INTERNAL_KEYS = ("stdout", "stderr", "cmd", "command", "returncode", "traceback", "stack", "detail")

    @classmethod
    def _sanitize_error_observation(cls, observation: str, max_err_len: int = 300) -> str:
        """错误 observation 脱敏：剔除内部细节字段，保留业务错误信息与 hint。

        - 保留：error / hint / message / tool / permanent 等业务字段（LLM 需要它们决定下一步）
        - 剔除：stdout / stderr / cmd / returncode / traceback 等内部细节（防泄漏 + 省上下文）
        - error 消息超长时截断（完整内容已进服务端日志）
        """
        if not isinstance(observation, str) or not observation.strip():
            return observation
        try:
            payload = json.loads(observation)
        except json.JSONDecodeError:
            return observation
        if not isinstance(payload, dict) or not (payload.get("error") or payload.get("tool_failed")):
            # 非错误 observation 原样返回
            return observation
        sanitized = {k: v for k, v in payload.items() if k not in cls._OBS_INTERNAL_KEYS}
        err = sanitized.get("error")
        if isinstance(err, str) and len(err) > max_err_len:
            sanitized["error"] = err[:max_err_len] + "…(截断，完整信息见服务端日志)"
        return json.dumps(sanitized, ensure_ascii=False, default=str)

    async def _persist_creative_state(
        self,
        harness: AgentHarness,
        context: WorkflowContext,
        tool_name: str,
        result: Any,
        arguments: dict[str, Any],
    ) -> None:
        """活文档：关键工具成功后，把产出持久化到 session 的 creative_state。

        同时对图文 produce Skill（card_xiaohongshu / xhs_note_creator 等），
        构建 _card_draft 并通过 SSE 推送 draft_patch 事件到前端渲染。
        """
        _COPYWRITE_TOOLS = {"lively_girl", "elegant", "professional"}
        _CARD_PRODUCE_TOOLS = {
            "card_xiaohongshu", "card_quote", "card_design",
            "infographic", "poster_hero", "comparison_card", "style_transfer",
            "xhs_note_creator", "copywriting",
        }

        if not isinstance(result, dict):
            return

        session_id = str(getattr(context, "workflow_id", "") or "")
        if not session_id:
            return

        updates: dict[str, Any] = {}

        if tool_name in _COPYWRITE_TOOLS and result.get("title"):
            updates["phase"] = "copywriting"
            updates["copywrite_result"] = {
                "title": result.get("title", ""),
                "content": result.get("content", ""),
                "tags": result.get("tags", []),
            }

        if tool_name in _CARD_PRODUCE_TOOLS:
            card_draft = result.get("card_draft")
            logger.info(f"[{context.node_id}] _persist_creative_state: tool={tool_name}, has_card_draft={card_draft is not None}, result_keys={list(result.keys()) if isinstance(result, dict) else type(result)}")
            if card_draft and isinstance(card_draft, dict):
                logger.info(f"[{context.node_id}] _persist_creative_state: card_draft keys={list(card_draft.keys())}, pages_count={len(card_draft.get('pages', []))}")
            if card_draft and isinstance(card_draft, dict) and card_draft.get("pages"):
                updates["phase"] = "card_produce"
                updates["_card_draft"] = card_draft
                await self._emit_draft_patch(harness, context, card_draft)
                await self._persist_artifact_to_disk(session_id, tool_name, result, card_draft)

        if not updates:
            return

        try:
            from app.services import chat_session
            await chat_session.update_creative_state(session_id, updates)
            logger.info(f"[{context.node_id}] creative_state persisted: {list(updates.keys())} from {tool_name}")
        except Exception as e:
            logger.warning(f"[{context.node_id}] creative_state persist failed: {e}")

    async def _emit_draft_patch(
        self,
        harness: AgentHarness,
        context: WorkflowContext,
        card_draft: dict[str, Any],
    ) -> None:
        """通过 SSE 推送 draft_patch 事件，将 _card_draft 传到前端渲染。"""
        try:
            from app.services.sse_bus import sse_bus, EVENT_DRAFT_PATCH

            workflow_id = getattr(context, "workflow_id", None)
            if not workflow_id:
                return

            draft_id = str(getattr(context, "workflow_id", "") or "")
            await sse_bus.publish(
                workflow_id,
                EVENT_DRAFT_PATCH,
                {
                    "draft_id": draft_id,
                    "updates": {"_card_draft": card_draft},
                },
            )
            logger.info(f"[{context.node_id}] draft_patch emitted: {len(card_draft.get('pages', []))} pages")
        except Exception as e:
            logger.warning(f"[{context.node_id}] draft_patch emit failed: {e}")

    async def _persist_artifact_to_disk(
        self,
        session_id: str,
        tool_name: str,
        result: dict[str, Any],
        card_draft: dict[str, Any],
    ) -> None:
        """将卡片产出持久化为 CreativeArtifact JSON 文件到磁盘。

        存储路径：backend/data/creative_artifacts/{artifact_id}.json
        确保作品不会因 session 过期而丢失。
        """
        try:
            from app.services.creative_artifact import build_artifact, save_artifact

            title = card_draft.get("title") or result.get("topic") or ""
            pages = card_draft.get("pages") or []
            template = card_draft.get("template") or tool_name

            artifact = build_artifact(
                card_draft={
                    "pages": pages,
                    "suggested_template": template,
                    "title": title,
                },
                brief={
                    "title": title,
                    "topic": result.get("topic", ""),
                    "goal": "小红书知识卡片",
                    "visual_direction": "叙事型",
                },
                source={
                    "session_id": session_id,
                    "platform": "xiaohongshu",
                },
            )
            save_artifact(artifact)
            logger.info(
                f"[{session_id}] artifact persisted to disk: "
                f"{artifact.artifact_id}, pages={len(pages)}"
            )
        except Exception as e:
            logger.warning(f"[{session_id}] artifact disk persist failed: {e}")

    # ------------------------------------------------------------------
    # LLM 调用（复用 SingleShotExecutor 的同款逻辑，但不带 response_format）
    # ------------------------------------------------------------------

    async def _call_llm_streaming(
        self,
        harness: AgentHarness,
        messages: list[dict[str, Any]],
        context: WorkflowContext,
        emit_delta: bool = True,
    ) -> tuple[str, int, list[dict[str, Any]], bool, str]:
        llm = harness.llm
        if llm is None:
            return '{"final": true, "output": {}}', 0, [], False, ""

        from app.engine.governance.llm_circuit import get_llm_circuit
        circuit = get_llm_circuit()
        if not circuit.allow_request():
            _reason = circuit.open_reason or "consecutive failures"
            logger.error(
                f"[{context.node_id}] LLM circuit OPEN, aborting call. "
                f"reason={_reason}"
            )
            raise RuntimeError(
                f"LLM 熔断器已开启（{_reason}），请检查 API 余额和配置后重试"
            )

        # Governance: TimeReminder — inject current time awareness
        # Ref: Codex time_reminder.rs — periodic time injection before LLM calls
        harness.time_reminder.inject_into_messages(messages)

        # Governance: ContextWindow — check precise window status
        # Ref: Codex context_window.rs — check before each LLM call
        cw_status = harness.context_window.get_status()
        if cw_status.token_limit_reached:
            logger.info(
                f"[{context.node_id}] context window limit reached "
                f"({cw_status.active_context_tokens}/{cw_status.full_context_window_limit}), "
                f"triggering compaction"
            )
            messages = await harness.compactor.compact(messages, llm)
            harness.context_window.reset_after_compaction()
            harness.thread_store.record(
                ThreadEventType.COMPACTION,
                {"reason": "context_window_limit", "messages_after": len(messages)},
            )
            await self._publish_governance_event(
                context, EVENT_GOVERNANCE_CONTEXT_WINDOW,
                reason="limit_reached",
                active_tokens=cw_status.active_context_tokens,
                limit=cw_status.full_context_window_limit,
            )
            await self._publish_governance_event(
                context, EVENT_GOVERNANCE_COMPACTION,
                reason="context_window_limit",
                messages_after=len(messages),
            )
        elif harness.compactor.should_compact(messages):
            logger.info(f"[{context.node_id}] proactive compaction before LLM call")
            messages = await harness.compactor.compact(messages, llm)
            harness.context_window.reset_after_compaction()
            await self._publish_governance_event(
                context, EVENT_GOVERNANCE_COMPACTION,
                reason="proactive",
                messages_after=len(messages),
            )

        # Governance: StreamRetry — intelligent retry with transport fallback
        # Ref: Codex responses_retry.rs — replaces manual retry loop
        retry_state = StreamRetryState(max_retries=3)
        use_stream = True

        while True:
            try:
                # 非流式：总时长上限（无法观测进度，只能限时）。
                # 流式：内部按 chunk 空闲超时看护（有数据就不掐），这里只留绝对兜底——
                # 旧实现 120s 硬掐整个调用，长回复生成到一半就被截断。
                _outer_timeout = _LLM_STREAM_CEILING if use_stream else _LLM_CALL_TIMEOUT
                content, token_usage, api_tool_calls, _reasoning_pushed_inner, _clarify_tag_full = await asyncio.wait_for(
                    harness.llm_queue.submit(
                        lambda: self._do_llm_call(harness, messages, context, use_stream=use_stream, emit_delta=emit_delta),
                        token_estimate=len(str(messages)) // 4,
                    ),
                    timeout=_outer_timeout,
                )

                # Governance: ContextWindow — record token usage
                harness.context_window.record_tokens(token_usage or 0)

                # Governance: TokenBudget — record and check budget
                action = harness.token_budget.record_usage(token_usage)
                if action == BudgetAction.HARD_STOP:
                    logger.error(
                        f"[{context.node_id}] token budget HARD STOP at "
                        f"{harness.token_budget.total_tokens}"
                    )
                    return '{"final": true, "output": {"_budget_exceeded": true}}', token_usage
                elif action == BudgetAction.COMPACT:
                    logger.info(f"[{context.node_id}] token budget triggers compaction")
                    messages = await harness.compactor.compact(messages, llm)
                    harness.context_window.reset_after_compaction()
                    harness.thread_store.record(
                        ThreadEventType.COMPACTION,
                        {"reason": "budget_compact", "messages_after": len(messages)},
                    )
                    await self._publish_governance_event(
                        context, EVENT_GOVERNANCE_COMPACTION,
                        reason="budget_exceeded",
                        messages_after=len(messages),
                    )
                elif action == BudgetAction.WARN:
                    logger.warning(
                        f"[{context.node_id}] token budget warning: "
                        f"{harness.token_budget.remaining_in_window()} remaining"
                    )
                    harness.thread_store.record(
                        ThreadEventType.BUDGET_WARNING,
                        {"remaining": harness.token_budget.remaining_in_window()},
                    )
                    await self._publish_governance_event(
                        context, EVENT_GOVERNANCE_BUDGET_WARNING,
                        remaining=harness.token_budget.remaining_in_window(),
                        total=harness.token_budget.total_tokens,
                    )

                return content, token_usage, api_tool_calls, _reasoning_pushed_inner, _clarify_tag_full

            except (asyncio.TimeoutError, TimeoutError) as _timeout_err:
                # 超时不走 retry：等待这么久仍无响应说明 LLM 不可用，
                # StreamRetryState 会把 timeout 归为连接错误重试最多 10 次，
                # 只会把整个 loop 的时间预算拖爆。直接上抛交给上层兜底。
                # 流式调用走到这里 = 空闲超时（连续无 chunk）；非流式 = 总时长超限。
                logger.error(
                    f"[{context.node_id}] LLM call abandoned "
                    f"(stream_idle={_STREAM_IDLE_TIMEOUT:g}s / total_ceiling="
                    f"{_LLM_STREAM_CEILING:g}s / nonstream={_LLM_CALL_TIMEOUT:g}s), giving up"
                )
                # str(TimeoutError()) 为空串，转成带信息的异常便于上层日志定位
                raise TimeoutError(
                    f"LLM call timed out (see loop timeout config)"
                ) from _timeout_err

            except Exception as e:
                action = retry_state.handle_error(e)

                if action == RetryAction.GIVE_UP:
                    raise

                if action == RetryAction.FALLBACK:
                    logger.info(f"[{context.node_id}] stream fallback to non-streaming")
                    use_stream = False
                    retry_state.retries = 0
                    await self._publish_governance_event(
                        context, EVENT_GOVERNANCE_RETRY,
                        action="fallback",
                        retries=retry_state.retries,
                        error=str(e),
                    )
                    continue

                if action == RetryAction.RETRY:
                    delay = retry_state.next_delay()
                    logger.warning(
                        f"[{context.node_id}] LLM call failed, retrying in {delay:.1f}s "
                        f"(retry={retry_state.retries}): {e}"
                    )
                    await self._publish_governance_event(
                        context, EVENT_GOVERNANCE_RETRY,
                        action="retry",
                        retries=retry_state.retries,
                        delay=delay,
                        error=str(e)[:200],
                    )
                    await asyncio.sleep(delay)
                    continue

        return '{"final": true, "output": {}}', 0, [], False

    async def _do_llm_call(
        self,
        harness: AgentHarness,
        messages: list[dict[str, Any]],
        context: WorkflowContext,
        use_stream: bool = True,
        emit_delta: bool = True,
    ) -> tuple[str, int, list[dict[str, Any]], bool, str]:
        """LLM call with function calling support.

        Returns: (content_text, token_usage, tool_calls, reasoning_pushed)
        - content_text: pure text from LLM (streamed to frontend as agent_message_delta)
        - tool_calls: structured tool calls from API (not parsed from JSON)
        - emit_delta: if False, suppress agent_message_delta emission (intermediate rounds
          where LLM is reasoning/deciding, not producing final answer for user)
        """
        from app.engine.governance.llm_circuit import get_llm_circuit

        llm = harness.llm
        content_parts: list[str] = []
        token_usage = 0
        tool_calls_result: list[dict[str, Any]] = []
        tools_schema = self._build_tools_schema(harness)
        try:
            stream_fn = getattr(llm, "stream_chat", None)
            _reasoning_pushed = False
            if use_stream and stream_fn is not None:
                logger.info(f"[loop] using streaming LLM call with tools, model={getattr(llm, 'model', '?')}, tools_count={len(tools_schema)}, emit_delta={emit_delta}")
                _content_stream_started = False
                _stream_buffer = ""
                _thinking_detector = ThinkingTagDetector()
                _clarify_detector = ClarificationTagDetector()
                _clarify_tag_content_parts: list[str] = []
                stream_iter = stream_fn(messages, tools=tools_schema if tools_schema else None).__aiter__()
                while True:
                    try:
                        chunk = await asyncio.wait_for(
                            stream_iter.__anext__(), timeout=_STREAM_IDLE_TIMEOUT
                        )
                    except StopAsyncIteration:
                        break
                    except (asyncio.TimeoutError, TimeoutError):
                        logger.error(
                            f"[{context.node_id}] LLM stream idle for "
                            f"{_STREAM_IDLE_TIMEOUT:g}s, aborting "
                            f"({len(content_parts)} chunks received so far)"
                        )
                        raise TimeoutError(
                            f"LLM stream idle timeout after {_STREAM_IDLE_TIMEOUT:g}s"
                        )
                    reasoning = chunk.get("reasoning_content")
                    text = chunk.get("content")
                    if reasoning:
                        await harness.observer.emit_llm_stream(context.node_id, {"reasoning_content": reasoning})
                        _reasoning_pushed = True
                    if text:
                        content_parts.append(text)
                        _stream_buffer += text
                        if emit_delta:
                            _thinking_reasoning, _thinking_content = _thinking_detector.feed(text)
                            if _thinking_reasoning:
                                await harness.observer.emit_reasoning_delta(context.node_id, _thinking_reasoning)
                                _reasoning_pushed = True
                            if _thinking_content:
                                _is_inside_thinking = _thinking_detector._inside
                                _clarify_content, _clarify_tag = _clarify_detector.feed(_thinking_content, is_inside_thinking=_is_inside_thinking)
                                if _clarify_tag:
                                    _clarify_tag_content_parts.append(_clarify_tag)
                                if _clarify_content:
                                    if not _content_stream_started:
                                        _content_stream_started = True
                                    await harness.observer.emit_agent_message_delta(context.node_id, _clarify_content)
                            elif _thinking_reasoning:
                                pass
                            elif _thinking_detector._buf:
                                pass
                            else:
                                if not _content_stream_started:
                                    _content_stream_started = True
                                await harness.observer.emit_agent_message_delta(context.node_id, text)
                    if chunk.get("is_final"):
                        token_usage = chunk.get("token_usage", 0) or token_usage
                        if chunk.get("tool_calls"):
                            tool_calls_result = chunk["tool_calls"]
                if emit_delta:
                    _flush_r, _flush_c = _thinking_detector.flush()
                    if _flush_r:
                        await harness.observer.emit_reasoning_delta(context.node_id, _flush_r)
                        _reasoning_pushed = True
                    if _flush_c:
                        _clarify_flush_c, _clarify_flush_tag = _clarify_detector.flush()
                        if _clarify_flush_tag:
                            _clarify_tag_content_parts.append(_clarify_flush_tag)
                        if _clarify_flush_c:
                            await harness.observer.emit_agent_message_delta(context.node_id, _clarify_flush_c)
                        else:
                            await harness.observer.emit_agent_message_delta(context.node_id, _flush_c)
                    else:
                        _clarify_flush_c, _clarify_flush_tag = _clarify_detector.flush()
                        if _clarify_flush_tag:
                            _clarify_tag_content_parts.append(_clarify_flush_tag)
                        if _clarify_flush_c:
                            await harness.observer.emit_agent_message_delta(context.node_id, _clarify_flush_c)
                _clarify_tag_full = "".join(_clarify_tag_content_parts)
                if _clarify_tag_full:
                    logger.info(f"[loop] LLM 自主触发澄清: <needs_clarification> 标签检测到 ({len(_clarify_tag_full)} chars)")
                if not _reasoning_pushed:
                    logger.debug(f"[loop] No reasoning_content or <thinking> tag received in this stream")
            else:
                result = await llm.chat(messages)
                content_parts.append(result.get("content", ""))
                token_usage = result.get("token_usage", 0)
                if result.get("reasoning_content"):
                    await harness.observer.emit_llm_stream(context.node_id, {"reasoning_content": result["reasoning_content"]})
                    _reasoning_pushed = True
                _result_content = result.get("content", "")
                _clarify_tag_full = ""
                if _result_content and emit_delta:
                    _det = ThinkingTagDetector()
                    _r, _c = _det.feed(_result_content)
                    _fr, _fc = _det.flush()
                    _r += _fr
                    _c += _fc
                    if _r:
                        await harness.observer.emit_reasoning_delta(context.node_id, _r)
                        _reasoning_pushed = True
                    if _c:
                        _cdet = ClarificationTagDetector()
                        _cc, _ct = _cdet.feed(_c)
                        _fcc, _fct = _cdet.flush()
                        _clarify_tag_full = _ct + _fct
                        if _cc + _fcc:
                            await harness.observer.emit_agent_message_delta(context.node_id, _cc + _fcc)
                    else:
                        _cdet = ClarificationTagDetector()
                        _cc, _ct = _cdet.feed(_result_content)
                        _fcc, _fct = _cdet.flush()
                        _clarify_tag_full = _ct + _fct
                if _clarify_tag_full:
                    logger.info(f"[loop] LLM 自主触发澄清 (非流式): <needs_clarification> 标签检测到 ({len(_clarify_tag_full)} chars)")
                tool_calls_result = result.get("tool_calls", [])
        except Exception as e:
            circuit = get_llm_circuit()
            is_unrecoverable = circuit.check_error(e)
            if is_unrecoverable:
                logger.error(
                    f"[{context.node_id}] LLM call unrecoverable error, "
                    f"circuit now {circuit.state.value}: {e}"
                )
            raise

        get_llm_circuit().record_success()

        if _reasoning_pushed:
            try:
                await harness.observer.emit_reasoning_completed(context.node_id, [])
            except Exception:
                pass

        return "".join(content_parts), token_usage, tool_calls_result, _reasoning_pushed, _clarify_tag_full

    # ------------------------------------------------------------------
    # 解析与工具分发
    # ------------------------------------------------------------------

    @staticmethod
    def _tool_calls_from_text(content: str) -> list[dict[str, Any]]:
        """从正文 JSON 中提取 tool_calls（兼容 markdown fence）。

        协议见本文件顶部示例：{"thought": ..., "tool_calls": [{"name":..., "arguments": {...}}], "final": false}
        模型没走 function calling 时用它兜底；解析不到就返回空列表。

        v2 加固：JSON 解析失败后，追加正则兜底提取 tool_name({...}) 模式，
        防止模型输出格式微偏导致"说要调工具但没人执行"的静默停摆。
        """
        text = (content or "").strip()
        if not text or "{" not in text:
            return []
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            first, last = text.find("{"), text.rfind("}")
            if first < 0 or last <= first:
                return LoopExecutor._tool_calls_from_regex(content)
            try:
                parsed = json.loads(text[first : last + 1])
            except json.JSONDecodeError:
                return LoopExecutor._tool_calls_from_regex(content)
        if not isinstance(parsed, dict):
            return LoopExecutor._tool_calls_from_regex(content)
        raw_calls = parsed.get("tool_calls")
        if not isinstance(raw_calls, list):
            return LoopExecutor._tool_calls_from_regex(content)
        calls: list[dict[str, Any]] = []
        for tc in raw_calls:
            if not isinstance(tc, dict):
                continue
            name = str(tc.get("name") or "").strip()
            if not name:
                continue
            args = tc.get("arguments") or tc.get("args") or {}
            if not isinstance(args, dict):
                args = {"value": args}
            calls.append({"name": name, "arguments": args})
        return calls

    _TOOL_CALL_RE = re.compile(
        r'\b([a-z][a-z0-9_]+)\s*\(\s*(\{[^}]*\})\s*\)',
        re.IGNORECASE,
    )

    @staticmethod
    def _tool_calls_from_regex(content: str) -> list[dict[str, Any]]:
        """正则兜底：从文本中提取 tool_name({...}) 模式的调用。

        当 JSON 解析完全失败时，尝试匹配形如 trending_search({"keyword": "AI"}) 的模式。
        仅提取最简单的单层 JSON 参数，复杂嵌套参数会被忽略（安全降级）。
        """
        calls: list[dict[str, Any]] = []
        seen: set[str] = set()
        for match in LoopExecutor._TOOL_CALL_RE.finditer(content):
            name = match.group(1)
            if name in seen or name in ("json", "dict", "list", "set", "print", "log"):
                continue
            try:
                args = json.loads(match.group(2))
                if isinstance(args, dict):
                    seen.add(name)
                    calls.append({"name": name, "arguments": args})
            except json.JSONDecodeError:
                continue
        if calls:
            logger.info(f"[loop] regex fallback extracted {len(calls)} tool calls: {[c['name'] for c in calls]}")
        return calls

    @staticmethod
    def _parse_clarification_tag(tag_content: str) -> dict[str, Any] | None:
        """解析 <needs_clarification> 标签内的结构化内容。

        支持两种格式：
        1. 结构化键值对：
           question: 第4张对比图的布局方式？
           options: 左右对比 | 上下对比 | 表格对比

        2. JSON 格式：
           {"question": "...", "options": ["...", "..."]}

        解析失败返回 None（容错：当普通文本处理）。
        """
        text = tag_content.strip()
        if not text:
            return None

        # 尝试 JSON 格式
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "question" in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

        # 尝试键值对格式
        result: dict[str, Any] = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.lower().startswith("question:"):
                result["question"] = line[len("question:"):].strip()
            elif line.lower().startswith("options:"):
                opts_str = line[len("options:"):].strip()
                result["options"] = [o.strip() for o in opts_str.split("|") if o.strip()]

        if "question" in result:
            return result

        # 兜底：整段文本作为 question
        return {"question": text}

    def _parse_step(self, content: str) -> dict[str, Any]:
        """容忍 markdown fence / 多余文字的 JSON 解析。"""
        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            # 兜底：尝试截取第一个 JSON 对象
            first = text.find("{")
            last = text.rfind("}")
            if first >= 0 and last > first:
                try:
                    return json.loads(text[first : last + 1])
                except json.JSONDecodeError:
                    pass
            return {"raw_text": content}

    async def _load_user_profile_safely(
        self, db: Any, context: WorkflowContext
    ) -> dict[str, Any] | None:
        """软注入读取创作者画像（D18），任何失败都不影响 chat 主流程。

        返回画像 dict 或 None；工作流节点不走这里（节点层从 state 注入），
        本方法只服务 ReAct Loop 的 skill 调用（chat/微信/飞书三入口共用）。
        """
        user_id = str(getattr(context, "user_id", "") or "")
        if not user_id or db is None:
            return None
        try:
            from app.services.profile_service import get_profile_cached

            profile = await get_profile_cached(db, user_id)
            if profile is None:
                return None
            return profile.model_dump(mode="json")
        except Exception as e:
            # 表未迁移/DB 抖动等：按"无画像"处理，chat 不拦
            logger.debug(f"[loop] profile soft-inject skipped: {e}")
            return None

    async def _execute_tool_call(
        self,
        harness: AgentHarness,
        context: WorkflowContext,
        skill_map: dict[str, Any],
        call: dict[str, Any],
        *,
        _approved: bool = False,
    ) -> tuple[str, dict[str, Any] | None]:
        """执行一次 tool_call，返回 (observation_str, confirmation_dict_or_None)。

        Ref: Codex exec.rs — every tool call goes through:
          1. Guardian check (policy -> confirm -> validate)
          2. Pre-tool hooks
          3. Skill execution
          4. Post-tool hooks
          5. Thread store recording
        """
        tool_name = str(call.get("name") or "").strip()
        arguments = call.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {"value": arguments}

        if not tool_name:
            return '{"error": "missing tool name"}', None

        skill = skill_map.get(tool_name)
        if skill is None:
            return f'{{"error": "unknown tool: {tool_name}"}}', None

        # ---- Stage 0: Clarification check (Progressive Clarification Protocol) ----
        # 在 Guardian 之前：如果 Skill 声明了 clarify_meta 且有未回答字段，
        # 暂停循环，返回澄清请求让用户填写。
        _clarify_meta = getattr(skill, "clarify_meta", None)
        logger.info(
            f"[clarify] Stage 0 check: tool={tool_name}, "
            f"node_type={getattr(skill, 'node_type', '?')}, "
            f"has_clarify_meta={bool(_clarify_meta)}, "
            f"meta_fields={list(_clarify_meta.keys()) if _clarify_meta else []}, "
            f"approved={_approved}"
        )
        if _clarify_meta and isinstance(_clarify_meta, dict) and _clarify_meta:
            _already_clarified = (
                getattr(context, "extra", {}).get("clarification_result", {})
                if hasattr(context, "extra")
                else {}
            )
            _needs_clarify = False
            for _fname, _fmeta in _clarify_meta.items():
                _when = getattr(_fmeta, "when", None)
                _when_val = getattr(_when, "value", "missing") if _when else "missing"
                _in_args = _fname in arguments
                _in_clarified = _fname in _already_clarified
                logger.debug(
                    f"[clarify] field={_fname}, when={_when_val}, "
                    f"in_args={_in_args}, in_clarified={_in_clarified}"
                )
                if _when_val == "always" and _fname not in _already_clarified:
                    _needs_clarify = True
                    break
                if _when_val == "missing" and _fname not in _already_clarified and _fname not in arguments:
                    _needs_clarify = True
                    break
                if _when_val == "ambiguous" and _is_ambiguous(
                    _fname, arguments, _already_clarified
                ):
                    _needs_clarify = True
                    break
            logger.info(
                f"[clarify] needs_clarify={_needs_clarify}, "
                f"already_clarified_fields={list(_already_clarified.keys())}, "
                f"arguments_keys={list(arguments.keys())}"
            )
            # v2.2 意图过滤：搜索/分析类 Skill 不触发澄清
            if _needs_clarify and not _approved:
                _skill_node = getattr(skill, "node_type", "")
                if _skill_node not in _CLARIFY_TRIGGER_NODE_TYPES:
                    logger.info(f"[clarify] blocked by node_type filter: {_skill_node} not in {_CLARIFY_TRIGGER_NODE_TYPES}")
                    _needs_clarify = False
            if _needs_clarify and not _approved:
                # v3 auto_default: 检查所有需要澄清的字段是否都能自动填默认值
                _auto_defaultable = True
                _auto_default_fields: dict[str, str] = {}
                for _fname, _fmeta in _clarify_meta.items():
                    _when = getattr(_fmeta, "when", None)
                    _when_val = getattr(_when, "value", "missing") if _when else "missing"
                    _in_args = _fname in arguments
                    _in_clarified = _fname in _already_clarified
                    _field_needs_clarify = False
                    if _when_val == "always" and _fname not in _already_clarified:
                        _field_needs_clarify = True
                    elif _when_val == "missing" and _fname not in _already_clarified and _fname not in arguments:
                        _field_needs_clarify = True
                    elif _when_val == "ambiguous" and _is_ambiguous(_fname, arguments, _already_clarified):
                        _field_needs_clarify = True
                    if _field_needs_clarify:
                        _ad = getattr(_fmeta, "auto_default", False)
                        _dv = getattr(_fmeta, "default", "")
                        if _ad and _dv:
                            _auto_default_fields[_fname] = _dv
                        else:
                            _auto_defaultable = False
                            break

                if _auto_defaultable and _auto_default_fields:
                    # 软建议模式：注入默认值到 arguments，不 break 循环
                    for _fn, _fv in _auto_default_fields.items():
                        if _fn not in arguments:
                            arguments[_fn] = _fv
                    logger.info(
                        f"[clarify] auto_default injected for {tool_name}: "
                        f"{list(_auto_default_fields.keys())} -> continuing execution"
                    )
                    # 推送建议卡片给前端（非阻塞）
                    try:
                        from app.agents.clarification_graph import collect_clarify_fields, build_batches
                        _batches = build_batches(
                            collect_clarify_fields([skill], clarified_answers=_already_clarified),
                            clarified_answers=_already_clarified,
                        )
                        if _batches:
                            await harness.observer.emit(context.node_id, "agent_clarification_hint", {
                                "clarification_prompt": _batches[0].title,
                                "clarification_skill": tool_name,
                                "clarification_batches": [b.model_dump() for b in _batches],
                                "auto_defaulted_fields": _auto_default_fields,
                                "message": f"已使用默认偏好继续创作，如需调整请随时告诉我",
                            })
                    except Exception:
                        logger.debug("[clarify] auto_default hint SSE push failed (non-critical)")
                    _needs_clarify = False

                if _needs_clarify:
                    from app.agents.clarification_graph import collect_clarify_fields, build_batches
                    _batches = build_batches(
                        collect_clarify_fields([skill], clarified_answers=_already_clarified),
                        clarified_answers=_already_clarified,
                    )
                    if _batches:
                        return (
                            json.dumps(
                                {"needs_clarification": True, "batch_count": len(_batches)},
                                ensure_ascii=False,
                            ),
                            {
                                "_type": "clarification",
                                "name": tool_name,
                                "arguments": arguments,
                                "_clarification_batches": [
                                    b.model_dump() for b in _batches
                                ],
                                "_clarification_prompt": _batches[0].title,
                            },
                        )

        # ---- Stage 1: Guardian check (ref: Codex exec.rs approval chain) ----
        decision = await harness.guardian.check(
            tool_name=tool_name,
            arguments=arguments,
            context=context,
            skill=skill,
        )

        if decision.action.value == "deny":
            await harness.observer.emit_tool_call_start(
                context.node_id, tool_name, arguments
            )
            await harness.observer.emit_tool_call_end(
                context.node_id, tool_name, False, f"guardian denied: {decision.reason}"
            )
            harness.thread_store.record(
                ThreadEventType.GUARDIAN_DECISION,
                {"tool": tool_name, "action": "denied", "reason": decision.reason},
            )
            return decision.to_observation(), None

        if decision.action.value == "needs_confirm":
            if _approved:
                # 用户已在确认卡片批准该调用：跳过确认门直接执行
                # （guardian 的 deny/参数校验仍然生效，只是不再二次询问）
                harness.thread_store.record(
                    ThreadEventType.GUARDIAN_DECISION,
                    {
                        "tool": tool_name,
                        "action": "approved_by_user",
                        "risk_level": decision.risk_level,
                    },
                )
            else:
                return (
                    json.dumps(
                        {"needs_confirmation": True, "prompt": decision.confirmation_prompt},
                        ensure_ascii=False,
                    ),
                    {
                        "name": tool_name,
                        "arguments": arguments,
                        "_confirmation_prompt": decision.confirmation_prompt,
                        "_risk_level": decision.risk_level,
                    },
                )

        # ---- Stage 2: Pre-tool hooks (ref: Codex hooks.rs) ----
        hook_payload = await harness.hooks.fire(
            "pre_tool",
            tool_name=tool_name,
            arguments=arguments,
            context=context,
        )
        arguments = hook_payload.get("arguments", arguments)

        # ---- Stage 3: Permission gate (legacy, kept for backward compat) ----
        from app.tools.permissions import permission_gate

        try:
            await permission_gate.require(skill.required_permissions, context)
        except PermissionDeniedError as e:
            await harness.observer.emit_tool_call_start(
                context.node_id, tool_name, arguments
            )
            await harness.observer.emit_tool_call_end(
                context.node_id, tool_name, False, f"permission denied: {e.permission.value}"
            )
            harness.thread_store.record(
                ThreadEventType.GUARDIAN_DECISION,
                {"tool": tool_name, "action": "permission_denied", "permission": e.permission.value},
            )
            return json.dumps(
                {
                    "error": "permission_denied",
                    "permission": e.permission.value,
                    "hint": (
                        "该权限未开放，这不是任务终点：向用户说明缺少权限 "
                        f"{e.permission.value}，告知开启方法（backend/.env 的 "
                        "PERMISSIONS_ALLOW 加入该值并重启后端），并明确询问用户"
                        "是否开启后继续。不要默默放弃或只字不提地结束任务。"
                    ),
                },
                ensure_ascii=False,
            ), None

        # ---- Stage 4: Execute skill ----
        await harness.observer.emit_tool_call_start(context.node_id, tool_name, arguments)
        harness.thread_store.record(
            ThreadEventType.TOOL_CALL,
            {"tool": tool_name, "arguments": arguments},
        )
        try:
            from app.tools.context_vars import current_db_session
            db = current_db_session.get(None)
            last_search = harness.memory.get("_last_search_results")
            execute_params = {
                **arguments,
                "llm": harness.llm,
                "_context": context,
                "_db_session": db,
                "_last_search_results": last_search,
                "_observer": harness.observer,
            }
            # D18 chat 链路软注入：画像存在时塞给 skill（文案/审核等已支持
            # inputs["user_profile"]）；无画像/读失败则静默跳过，不拦 chat。
            # 读取走 profile_service 的 TTL 缓存，不会每次工具调用都打 DB。
            _profile_dict = await self._load_user_profile_safely(db, context)
            if _profile_dict:
                execute_params["user_profile"] = _profile_dict
            if hasattr(harness, "collaboration_tools"):
                execute_params = harness.collaboration_tools.inject_params(
                    execute_params, harness.agent_id
                )

            if hasattr(skill, "execute_streaming") and callable(getattr(skill, "execute_streaming")):
                result = await skill.execute_streaming(execute_params)
            else:
                result = await skill.execute(execute_params)
            harness.memory.set("_last_" + tool_name, result)
            if tool_name == "trending_search" and isinstance(result, dict):
                harness.memory.set("_last_search_results", result.get("results", []))
            summary = _truncate(str(result), 200)
            result_data = _safe_result_data(result)
            await harness.observer.emit_tool_call_end(
                context.node_id, tool_name, True, summary,
                result_data=result_data,
            )

            # 活文档：关键工具成功后持久化到 creative_state
            await self._persist_creative_state(harness, context, tool_name, result, arguments)

            # Emit collaboration events for frontend
            if tool_name == "spawn_agent" and isinstance(result, dict) and result.get("success"):
                await harness.observer.emit_trace(
                    context.node_id, "collab_agent_spawned", {
                        "agent_id": result.get("agent_id", ""),
                        "name": result.get("name", ""),
                        "path": result.get("path", ""),
                        "parent_id": result.get("parent_id", ""),
                        "depth": result.get("depth", 1),
                        "role": result.get("role"),
                        "task_description": arguments.get("task_description", ""),
                        "fork_mode": arguments.get("fork_mode", "clean"),
                    },
                )
            elif tool_name == "interrupt_agent" and isinstance(result, dict) and result.get("interrupted"):
                await harness.observer.emit_trace(
                    context.node_id, "collab_agent_interrupted", {
                        "agent_id": result.get("agent_id", ""),
                    },
                )
            harness.thread_store.record(
                ThreadEventType.TOOL_RESULT,
                {"tool": tool_name, "success": True, "summary": summary},
            )

            # Persist after each successful tool call
            # Ref: Codex session.rs — persist after each rollout step
            await harness.thread_store.persist()

            # ---- Stage 5: Post-tool hooks ----
            hook_payload = await harness.hooks.fire(
                "post_tool",
                tool_name=tool_name,
                result=result,
                context=context,
            )
            result = hook_payload.get("result", result)

            # ---- Stage 4.5: Skill 输出级 confirmation 检查 ----
            if isinstance(result, dict) and result.get("needs_confirmation"):
                confirmation_prompt = (
                    result.get("prompt")
                    or result.get("confirmation_prompt")
                    or "需要您确认才能继续"
                )
                return (
                    json.dumps(result, ensure_ascii=False, default=str),
                    {
                        "name": tool_name,
                        "arguments": arguments,
                        "_confirmation_prompt": confirmation_prompt,
                        "_risk_level": result.get("risk_level", "medium"),
                        "_source": "skill_output",
                    },
                )

            return json.dumps(result, ensure_ascii=False, default=str), None
        except Exception as e:
            # str(e) 可能为空（如 NotImplementedError），拼上异常类型名才能定位真凶
            err_msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            logger.warning(f"[{context.node_id}] tool {tool_name} failed: {err_msg}")
            await harness.observer.emit_tool_call_end(
                context.node_id, tool_name, False, err_msg
            )
            harness.thread_store.record(
                ThreadEventType.TOOL_RESULT,
                {"tool": tool_name, "success": False, "error": err_msg, "exception_type": type(e).__name__},
            )
            hint = ""
            if "validation error" in err_msg.lower() and "field required" in err_msg.lower():
                schema_cls = getattr(skill, "input_schema", None)
                if schema_cls is not None:
                    try:
                        schema = schema_cls.model_json_schema()
                        required = schema.get("required", [])
                        hint = f" You must provide these required fields: {required}. Check the tool description above for parameter details."
                    except Exception:
                        pass
            return json.dumps(
                {"error": "tool_failed", "tool": tool_name, "message": err_msg + hint},
                ensure_ascii=False,
            ), None

    def _output_from_last_observation(
        self, messages: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """无 final output 时的兜底：取最后一条 observation。"""
        for msg in reversed(messages):
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                c = msg["content"]
                if c.startswith("[observation] "):
                    payload = c[len("[observation] "):]
                    try:
                        parsed = json.loads(payload)
                        if isinstance(parsed, dict):
                            return parsed
                    except json.JSONDecodeError:
                        pass
        return {}

    @staticmethod
    def _check_tools_already_called(messages: list[dict[str, Any]], tool_names: tuple[str, ...]) -> set[str]:
        """检查对话历史中是否已经调用过指定工具。

        只采信明确的工具调用证据：assistant 的结构化 tool_calls、
        [observation] 中显式写出的 tool 字段，以及消息自带的 tool 元数据。
        system prompt 和用户普通文本里出现工具名不算已调用，避免把提示词
        中提到的 lively_girl 当成已完成。
        """
        called = set()
        for msg in messages:
            if msg.get("role") == "system":
                continue

            explicit_tool = msg.get("tool") or msg.get("tool_name")
            if explicit_tool in tool_names:
                called.add(explicit_tool)

            content = msg.get("content", "")
            if isinstance(content, str):
                if content.startswith("[observation] "):
                    try:
                        payload = json.loads(content[len("[observation] "):])
                        if isinstance(payload, dict):
                            tool = payload.get("tool")
                            if tool in tool_names:
                                called.add(tool)
                    except (json.JSONDecodeError, TypeError):
                        pass
                elif content.startswith("[observation:"):
                    tool = content.split("]", 1)[0][len("[observation:"):].strip()
                    if tool in tool_names:
                        called.add(tool)
            for tc in msg.get("tool_calls") or []:
                func = tc.get("function", {}) if isinstance(tc, dict) else {}
                name = func.get("name", "")
                if name in tool_names:
                    called.add(name)
        return called

    @staticmethod
    def _ensure_readable_output(output: dict[str, Any], last_thought: str = "") -> dict[str, Any]:
        """确保 output 包含前端可渲染的人类可读字段。

        当 LLM 直接把工具原始 JSON 作为 output 返回时（缺少 summary），
        从结构化数据中提取关键信息生成 summary / key_findings / recommendations。
        """
        if not isinstance(output, dict):
            return output

        if output.get("summary") or output.get("content"):
            return output

        if output.get("raw_text"):
            output["summary"] = str(output["raw_text"])
            return output

        parts: list[str] = []

        results = output.get("results")
        if isinstance(results, list) and results:
            top = results[:5]
            for i, r in enumerate(top, 1):
                title = r.get("title") or r.get("name") or f"结果{i}"
                interactions = r.get("interactions") or r.get("likes") or 0
                platform = r.get("platform", "")
                parts.append(f"{i}. {title}（互动{interactions}，{platform}）" if platform else f"{i}. {title}（互动{interactions}）")

        patterns = output.get("patterns")
        if isinstance(patterns, dict) and not patterns.get("_skipped"):
            hooks = patterns.get("title_hooks")
            if isinstance(hooks, list) and hooks:
                parts.append("标题钩子: " + "、".join(str(h) for h in hooks[:5]))
            emotions = patterns.get("emotion_triggers")
            if isinstance(emotions, list) and emotions:
                parts.append("情绪触发: " + "、".join(str(e) for e in emotions[:5]))

        insights = output.get("insights")
        if isinstance(insights, dict) and not insights.get("_skipped"):
            signals = insights.get("trend_signals")
            if isinstance(signals, list) and signals:
                parts.append("趋势信号: " + "、".join(str(s) for s in signals[:3]))
            recs = insights.get("recommendations")
            if isinstance(recs, list) and recs:
                output["recommendations"] = recs[:5]

        layer1 = output.get("layer1_stats")
        if isinstance(layer1, dict):
            total = layer1.get("total_notes", 0)
            content_pct = layer1.get("content_dominant_pct", 0)
            if total:
                parts.append(f"共分析 {total} 条内容，内容型爆款占比 {content_pct:.0%}" if content_pct else f"共分析 {total} 条内容")

        if parts:
            output["summary"] = "\n".join(parts)
        else:
            output["summary"] = "任务已完成，详细结果见上方工具输出。"

        if not output.get("key_findings"):
            output["key_findings"] = []
        if not output.get("recommendations"):
            output["recommendations"] = []
        if not output.get("tags"):
            output["tags"] = []

        return output

    @staticmethod
    async def _publish_governance_event(
        context: WorkflowContext,
        event_type: str,
        **details: Any,
    ) -> None:
        """Publish a governance event to SSE bus for frontend consumption.

        Ref: Codex session.rs — governance events are pushed to the event bus
        so the frontend can display budget warnings, compaction events, etc.
        This is a fire-and-forget operation; failures are silently logged.
        """
        try:
            from app.services.sse_bus import sse_bus

            workflow_id = context.workflow_id
            if not workflow_id:
                return

            await sse_bus.publish(workflow_id, event_type, {
                "node_id": context.node_id,
                **details,
            })
        except Exception as e:
            logger.debug(f"[governance] failed to publish SSE event {event_type}: {e}")


def _truncate(text: str, max_len: int) -> str:
    return text[:max_len] if len(text) > max_len else text


def _safe_result_data(result: Any) -> Any:
    """Extract JSON-safe result data for frontend structured rendering."""
    if result is None:
        return None
    if isinstance(result, (bool, int, float, str)):
        return result
    if isinstance(result, (list, tuple)):
        if len(result) > 50:
            return list(result[:50])
        return list(result)
    if isinstance(result, dict):
        try:
            import json
            json.dumps(result, default=str, ensure_ascii=False)
            return result
        except (TypeError, ValueError, OverflowError):
            return None
    return None