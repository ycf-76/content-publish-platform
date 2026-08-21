"""Loop executor (ReAct-style).

对应架构文档 4.3。与 SingleShotExecutor 相对：
- SingleShot：一次 LLM 调用 + 一次 Skills 集中执行，简单粗暴。
- Loop：多轮 LLM ↔ Tool 交替，LLM 自主决定下一步调哪个 Skill。
  每轮：build prompt → stream LLM → 解析 tool_calls → 权限门控 → 调 Skill
        → 把 observation 拼回对话 → 直到 LLM 给 final=true 或达 max_iterations。

红线：
- max_iterations 上限硬编码（默认 5），防止 LLM 死循环。
- 每次调 Skill 前必须经过 permission_gate，被拒时把错误作为 observation 喂回 LLM，
  让 LLM 有机会改路子，而不是直接崩。
- 不直接调 MCP / LLM，所有外部能力经 Skill，所有 LLM 经 harness.llm。
- 不 import langgraph / fastapi。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from app.agents.core.harness.executor.base import ExecutorBase
from app.agents.core.schemas import PermissionDeniedError

if TYPE_CHECKING:
    from app.agents.core.harness.runtime import AgentHarness
    from app.agents.core.schemas import WorkflowContext

logger = logging.getLogger(__name__)


# 默认上限：5 轮已经够覆盖「搜→分析→再搜→定稿」这类场景。
_DEFAULT_MAX_ITER = 5


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

    def __init__(self, max_iterations: int = _DEFAULT_MAX_ITER) -> None:
        self.max_iterations = max(1, int(max_iterations))

    async def execute(
        self,
        harness: AgentHarness,
        input: dict[str, Any],
        context: WorkflowContext,
    ) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt(harness)},
            {"role": "user", "content": self._initial_user_prompt(harness, input, context)},
        ]

        skill_map = {s.name: s for s in harness.skills}
        total_token_usage = 0
        last_thought = ""
        final_output: dict[str, Any] | None = None

        for iteration in range(1, self.max_iterations + 1):
            await harness.observer.emit_progress(
                context.node_id,
                current=iteration,
                total=self.max_iterations,
                label=f"loop iter {iteration}",
            )

            content, token_usage = await self._call_llm_streaming(harness, messages, context)
            total_token_usage += token_usage or 0
            parsed = self._parse_step(content)

            thought = parsed.get("thought") or ""
            if thought:
                last_thought = thought
                await harness.observer.emit_decision(context.node_id, thought)

            if parsed.get("final"):
                final_output = parsed.get("output") or self._output_from_last_observation(messages)
                break

            tool_calls = parsed.get("tool_calls") or []
            if not tool_calls:
                # LLM 没说要调工具也没说 final：把当前内容当作最终输出收尾
                final_output = parsed if parsed else {"raw_text": content}
                break

            # 把 assistant 这一步的原文喂回对话（保持上下文）
            messages.append({"role": "assistant", "content": content})

            for call in tool_calls:
                obs = await self._dispatch_tool(
                    harness, context, skill_map, call
                )
                messages.append(
                    {"role": "user", "content": f"[observation] {obs}"}
                )
        else:
            # 跑满 max_iterations 仍未 final：用最后一次 thought + 累积 observation 兜底
            logger.warning(
                f"[{context.node_id}] LoopExecutor hit max_iterations={self.max_iterations}, "
                "falling back to last observation as output"
            )
            final_output = final_output or self._output_from_last_observation(messages)
            final_output.setdefault("_loop_truncated", True)

        if not isinstance(final_output, dict):
            final_output = {"value": final_output}

        final_output["_token_usage"] = total_token_usage
        final_output.setdefault("_last_thought", last_thought)
        final_output.setdefault("_iterations", iteration)
        return final_output

    # ------------------------------------------------------------------
    # prompt 构建
    # ------------------------------------------------------------------

    def _system_prompt(self, harness: AgentHarness) -> str:
        skill_lines = "\n".join(
            f"- {s.name}: {s.description}" for s in harness.skills
        ) or "- (no tools available)"
        return (
            "You are an autonomous agent. Think step by step and decide which tool to call next.\n"
            "Reply in STRICT JSON only, no markdown fences.\n"
            "Schema:\n"
            '  {"thought": "<reasoning>", "tool_calls": [{"name": "<tool>", "arguments": {...}}], "final": false}\n'
            "or when done:\n"
            '  {"thought": "<reasoning>", "final": true, "output": {...}}\n'
            "\n"
            "Available tools:\n"
            f"{skill_lines}\n"
            "If a tool is denied or fails, observe the error and try a different path.\n"
            "Never fabricate tool output."
        )

    def _initial_user_prompt(
        self,
        harness: AgentHarness,
        input: dict[str, Any],
        context: WorkflowContext,
    ) -> str:
        try:
            base = harness.prompt_template.format(**{**input, **context.model_dump()})
        except (KeyError, IndexError):
            base = harness.prompt_template or json.dumps(input, ensure_ascii=False)
        if harness.memory:
            mem = harness.memory.to_dict()
            if mem:
                base += "\n\n[memory]\n" + json.dumps(mem, ensure_ascii=False, default=str)
        return base

    # ------------------------------------------------------------------
    # LLM 调用（复用 SingleShotExecutor 的同款逻辑，但不带 response_format）
    # ------------------------------------------------------------------

    async def _call_llm_streaming(
        self,
        harness: AgentHarness,
        messages: list[dict[str, Any]],
        context: WorkflowContext,
    ) -> tuple[str, int]:
        llm = harness.llm
        if llm is None:
            # 无 LLM 场景：直接返回 final=true 占位，让上层走兜底
            return '{"final": true, "output": {}}', 0

        content_parts: list[str] = []
        token_usage = 0

        stream_fn = getattr(llm, "stream_chat", None)
        if stream_fn is not None:
            async for chunk in stream_fn(messages):
                reasoning = chunk.get("reasoning_content")
                if reasoning:
                    await harness.observer.emit_llm_stream(context.node_id, chunk)
                text = chunk.get("content")
                if text:
                    content_parts.append(text)
                if chunk.get("is_final"):
                    token_usage = chunk.get("token_usage", 0) or token_usage
        else:
            result = await llm.chat(messages)
            content_parts.append(result.get("content", ""))
            token_usage = result.get("token_usage", 0)
            if result.get("reasoning_content"):
                await harness.observer.emit_llm_stream(context.node_id, result)

        return "".join(content_parts), token_usage

    # ------------------------------------------------------------------
    # 解析与工具分发
    # ------------------------------------------------------------------

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

    async def _dispatch_tool(
        self,
        harness: AgentHarness,
        context: WorkflowContext,
        skill_map: dict[str, Any],
        call: dict[str, Any],
    ) -> str:
        """执行一次 tool_call，返回给 LLM 的 observation 字符串。"""
        tool_name = str(call.get("name") or "").strip()
        arguments = call.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {"value": arguments}

        if not tool_name:
            return '{"error": "missing tool name"}'

        skill = skill_map.get(tool_name)
        if skill is None:
            return f'{{"error": "unknown tool: {tool_name}"}}'

        # 权限门控：被拒时把错误作为 observation 回喂，不抛异常打断循环
        from app.agents.skills.permissions import permission_gate

        try:
            await permission_gate.require(skill.required_permissions, context)
        except PermissionDeniedError as e:
            await harness.observer.emit_tool_call_start(
                context.node_id, tool_name, arguments
            )
            await harness.observer.emit_tool_call_end(
                context.node_id, tool_name, False, f"permission denied: {e.permission.value}"
            )
            return json.dumps(
                {"error": "permission_denied", "permission": e.permission.value},
                ensure_ascii=False,
            )

        await harness.observer.emit_tool_call_start(context.node_id, tool_name, arguments)
        try:
            # 注入 harness.llm，让需要 LLM 的 skill（如 copywrite）能使用；其余 skill 忽略该字段
            result = await skill.execute({**arguments, "llm": harness.llm})
            summary = _truncate(str(result), 200)
            await harness.observer.emit_tool_call_end(
                context.node_id, tool_name, True, summary
            )
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            logger.warning(f"[{context.node_id}] tool {tool_name} failed: {e}")
            await harness.observer.emit_tool_call_end(
                context.node_id, tool_name, False, str(e)
            )
            return json.dumps(
                {"error": "tool_failed", "tool": tool_name, "message": str(e)},
                ensure_ascii=False,
            )

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


def _truncate(text: str, max_len: int) -> str:
    return text[:max_len] if len(text) > max_len else text