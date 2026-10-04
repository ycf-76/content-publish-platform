"""Codex-style session: lightweight ReAct loop + thin primitives.

This is the top-level orchestrator that replaces LangGraph's fixed graph
with an LLM-driven ReAct loop. The LLM decides which primitives to call,
in what order, based on the user's intent.

Key design:
- No AgentHarness dependency (no governance/recovery/compaction overhead)
- No LangGraph dependency
- Direct LLM calls with simple retry
- Primitives are dispatched via permission gate
- Observations feed back into the message chain for the next LLM call
- Full SSE event streaming: thought / tool_call_start / tool_call_end / progress / final

This module coexists with the existing graph.py — no existing code is modified.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from app.engine.codex.prompt import get_codex_system_prompt
from app.engine.codex.primitives import Primitive, PRIMITIVES_BY_NAME
from app.engine.schemas import Permission

logger = logging.getLogger(__name__)

_DEFAULT_MAX_ITER = 12
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 1.0
_OBSERVATION_MAX_LEN = 4000
_MESSAGES_MAX_LEN = 60


class CodexSession:
    """Codex-style top-level session with full SSE event streaming.

    Usage:
        session = CodexSession(allowed_permissions={Permission.FILE_READ, ...})
        result = await session.run("帮我做一期手冲咖啡的内容")
    """

    def __init__(
        self,
        llm: Any | None = None,
        primitives: list[Primitive] | None = None,
        allowed_permissions: set[Permission] | None = None,
        max_iterations: int = _DEFAULT_MAX_ITER,
        system_prompt: str | None = None,
        observer: Any | None = None,
        sse_bus: Any | None = None,
        workflow_id: str = "",
    ) -> None:
        self.llm = llm
        self.primitives = {p.name: p for p in (primitives or list(PRIMITIVES_BY_NAME.values()))}
        self.allowed_permissions = allowed_permissions or set()
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt or get_codex_system_prompt()
        self.observer = observer
        self.sse_bus = sse_bus
        self.workflow_id = workflow_id
        self._token_count = 0
        self._max_tokens = 100_000
        self._steps: list[dict[str, Any]] = []

    async def _emit_sse(self, event_type: str, payload: dict[str, Any]) -> None:
        if not self.sse_bus or not self.workflow_id:
            return
        try:
            await self.sse_bus.publish(self.workflow_id, event_type, payload)
        except Exception:
            pass

    async def _emit_observer(self, method: str, *args: Any, **kwargs: Any) -> None:
        if not self.observer:
            return
        try:
            fn = getattr(self.observer, method, None)
            if fn:
                await fn(*args, **kwargs)
        except Exception:
            pass

    async def run(
        self,
        user_intent: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute user intent through a ReAct loop with full event streaming."""
        messages = self._build_initial_messages(user_intent, context)
        total_token_usage = 0
        last_thought = ""
        final_output: dict[str, Any] | None = None
        iteration = 0

        await self._emit_sse("workflow_started", {
            "intent": user_intent,
            "max_iterations": self.max_iterations,
            "primitives": list(self.primitives.keys()),
        })
        await self._emit_sse("node_started", {
            "node_id": "codex",
            "node_type": "codex_react",
            "intent": user_intent,
        })

        for iteration in range(1, self.max_iterations + 1):
            step_record: dict[str, Any] = {
                "iteration": iteration,
                "thought": "",
                "tool_calls": [],
                "observations": [],
                "token_usage": 0,
                "duration_ms": 0,
            }
            step_start = time.monotonic()

            logger.info(f"[codex] iteration {iteration}/{self.max_iterations}")

            await self._emit_sse("progress_update", {
                "node_id": "codex",
                "current": iteration,
                "total": self.max_iterations,
                "label": f"第 {iteration} 步推理",
            })
            await self._emit_observer("emit_progress", "codex", iteration, self.max_iterations, f"ReAct iter {iteration}")

            content, token_usage, reasoning = await self._call_llm(messages, emit_delta=True)
            total_token_usage += token_usage or 0
            self._token_count += token_usage or 0
            step_record["token_usage"] = token_usage or 0

            if reasoning:
                await self._emit_sse("reasoning_completed", {
                    "node_id": "codex",
                    "iteration": iteration,
                    "summary_parts": [reasoning],
                })

            parsed = self._parse_step(content)
            thought = parsed.get("thought") or ""
            tool_calls = parsed.get("tool_calls") or []
            is_final = parsed.get("final", False)

            step_record["thought"] = thought

            logger.info(
                f"[codex] iter={iteration} thought={thought[:120]} "
                f"tool_calls={[tc.get('name') for tc in tool_calls]} final={is_final}"
            )

            if thought:
                last_thought = thought
                await self._emit_sse("decision_made", {
                    "node_id": "codex",
                    "iteration": iteration,
                    "decision": thought,
                })
                await self._emit_observer("emit_decision", "codex", thought)

            if is_final:
                final_output = parsed.get("output") or self._extract_output_from_messages(messages)
                step_record["final"] = True
                step_record["output"] = final_output
                break

            if not tool_calls:
                final_output = parsed if parsed else {"raw_text": content}
                step_record["final"] = True
                step_record["output"] = final_output
                break

            messages.append({"role": "assistant", "content": content})

            for call in tool_calls:
                tool_name = call.get("name", "?")
                tool_args = call.get("arguments", {})
                if not isinstance(tool_args, dict):
                    tool_args = {}

                display_args = self._summarize_tool_args(tool_name, tool_args)

                await self._emit_sse("tool_call_start", {
                    "node_id": "codex",
                    "iteration": iteration,
                    "tool_name": tool_name,
                    "inputs": display_args,
                })
                await self._emit_observer("emit_tool_call_start", "codex", tool_name, display_args)

                tool_start = time.monotonic()
                obs = await self._dispatch(call)
                tool_duration = int((time.monotonic() - tool_start) * 1000)

                obs_ok = obs.get("ok", True) if isinstance(obs, dict) else True
                obs_summary = self._summarize_observation(tool_name, obs)

                await self._emit_sse("tool_call_end", {
                    "node_id": "codex",
                    "iteration": iteration,
                    "tool_name": tool_name,
                    "success": obs_ok,
                    "summary": obs_summary,
                    "duration_ms": tool_duration,
                })
                await self._emit_observer("emit_tool_call_end", "codex", tool_name, obs_ok, obs_summary)

                step_record["tool_calls"].append({
                    "name": tool_name,
                    "args": display_args,
                    "ok": obs_ok,
                    "summary": obs_summary,
                    "duration_ms": tool_duration,
                })

                obs_str = json.dumps(obs, ensure_ascii=False, default=str)
                if len(obs_str) > _OBSERVATION_MAX_LEN:
                    obs_str = obs_str[:_OBSERVATION_MAX_LEN] + "...(truncated)"
                messages.append({
                    "role": "user",
                    "content": f"[observation] {tool_name} -> {obs_str}",
                })

                step_record["observations"].append(obs_summary)

            step_record["duration_ms"] = int((time.monotonic() - step_start) * 1000)
            self._steps.append(step_record)
            messages = self._maybe_truncate_messages(messages)
        else:
            logger.warning(f"[codex] max_iterations={self.max_iterations} reached")
            final_output = self._extract_output_from_messages(messages)
            final_output.setdefault("_loop_truncated", True)

        if not isinstance(final_output, dict):
            final_output = {"value": final_output}

        final_output["_token_usage"] = total_token_usage
        final_output["_iterations"] = iteration
        final_output.setdefault("_last_thought", last_thought)
        final_output["_steps"] = self._steps

        display_output = self._format_final_output(final_output)

        await self._emit_sse("node_completed", {
            "node_id": "codex",
            "node_type": "codex_react",
            "output": display_output,
            "iterations": iteration,
            "token_usage": total_token_usage,
        })
        await self._emit_sse("workflow_completed", {
            "output": display_output,
            "iterations": iteration,
            "token_usage": total_token_usage,
        })

        return final_output

    @staticmethod
    def _summarize_tool_args(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Summarize tool arguments for display (truncate large values)."""
        display: dict[str, Any] = {}
        for k, v in args.items():
            if isinstance(v, str) and len(v) > 200:
                display[k] = v[:200] + "..."
            elif isinstance(v, list) and len(v) > 5:
                display[k] = v[:5]
            else:
                display[k] = v
        return display

    @staticmethod
    def _summarize_observation(tool_name: str, obs: dict[str, Any]) -> str:
        """Create a human-readable summary of a tool observation."""
        if not obs.get("ok", True):
            return f"❌ {obs.get('error', 'unknown error')}"

        summaries: dict[str, str] = {
            "file_read": lambda o: f"📄 读取成功 ({o.get('total_lines', '?')} 行, {o.get('file_size', '?')} bytes)",
            "file_write": lambda o: f"📝 写入成功 ({o.get('lines', '?')} 行)",
            "file_edit": lambda o: f"✏️ 替换成功",
            "bash": lambda o: f"⚡ 执行完成 (exit_code={o.get('exit_code', '?')})",
            "glob": lambda o: f"🔍 找到 {o.get('count', 0)} 个文件",
            "grep": lambda o: f"🔍 匹配 {o.get('count', 0)} 处",
            "xhs_search": lambda o: f"🔎 搜索到 {o.get('count', len(o.get('results', [])))} 条笔记",
            "image_gen": lambda o: f"🎨 生成 {len(o.get('images', []))} 张图片",
            "image_read": lambda o: f"🖼️ 读取图片 {o.get('file_name', '')} ({o.get('file_size', 0)} bytes)",
            "image_analyze": lambda o: f"👁️ 分析完成",
            "llm_generate": lambda o: f"🧠 生成 {len(o.get('text', ''))} 字",
            "viral_score": lambda o: f"📊 爆款评分完成",
            "content_check": lambda o: f"✅ 合规{'通过' if o.get('passed') else '未通过'}",
        }

        fn = summaries.get(tool_name)
        if fn:
            try:
                return fn(obs)
            except Exception:
                pass

        return f"✅ 执行成功"

    @staticmethod
    def _format_final_output(output: dict[str, Any]) -> dict[str, Any]:
        """Format the final output for frontend display."""
        display: dict[str, Any] = {}

        for key in ("title", "content", "status", "tags", "file", "path"):
            if key in output:
                display[key] = output[key]

        if "error" in output:
            display["error"] = output["error"]

        display["_iterations"] = output.get("_iterations", 0)
        display["_token_usage"] = output.get("_token_usage", 0)
        display["_last_thought"] = output.get("_last_thought", "")

        return display

    def _build_initial_messages(
        self,
        user_intent: str,
        context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
        ]
        if context:
            context_str = json.dumps(context, ensure_ascii=False, default=str)
            messages.append({
                "role": "system",
                "content": f"[context] {context_str}",
            })
        messages.append({"role": "user", "content": user_intent})
        return messages

    async def _call_llm(
        self,
        messages: list[dict[str, Any]],
        emit_delta: bool = True,
    ) -> tuple[str, int, str]:
        """Call LLM with streaming + simple retry. Returns (content, token_usage, reasoning).

        Codex streaming philosophy: every token chunk from the LLM is immediately
        pushed to the frontend via agent_message_delta / reasoning_summary_text_delta.
        The LLM does NOT buffer its full output before emitting — we stream as we go.

        Args:
            messages: Chat message list.
            emit_delta: If True, push agent_message_delta events for each content chunk.
        """
        if self.llm is None:
            return '{"final": true, "output": {"error": "no LLM configured"}}', 0, ""

        stream_fn = getattr(self.llm, "stream_chat", None)
        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                if stream_fn is not None:
                    content_parts: list[str] = []
                    reasoning_parts: list[str] = []
                    token_usage = 0

                    async for chunk in stream_fn(messages):
                        reasoning = chunk.get("reasoning_content")
                        text = chunk.get("content")
                        if reasoning:
                            reasoning_parts.append(reasoning)
                            await self._emit_sse("reasoning_summary_text_delta", {
                                "node_id": "codex",
                                "delta": reasoning,
                            })
                        if text:
                            content_parts.append(text)
                            if emit_delta:
                                await self._emit_sse("agent_message_delta", {
                                    "node_id": "codex",
                                    "delta": text,
                                })
                        if chunk.get("is_final"):
                            token_usage = chunk.get("token_usage", 0) or token_usage

                    content = "".join(content_parts)
                    reasoning = "".join(reasoning_parts)
                    if reasoning_parts:
                        await self._emit_sse("reasoning_completed", {
                            "node_id": "codex",
                            "summary_parts": [],
                        })
                    return content, token_usage, reasoning
                else:
                    result = await self.llm.chat(messages)
                    content = result.get("content", "")
                    token_usage = result.get("token_usage", 0) or 0
                    reasoning = result.get("reasoning_content") or ""
                    return content, token_usage, reasoning
            except Exception as e:
                last_error = e
                logger.warning(f"[codex] LLM call attempt {attempt} failed: {e}")
                if attempt < _MAX_RETRIES:
                    delay = _RETRY_BASE_DELAY * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)

        logger.error(f"[codex] LLM call failed after {_MAX_RETRIES} retries: {last_error}")
        return json.dumps({
            "thought": f"LLM call failed: {last_error}",
            "final": True,
            "output": {"error": str(last_error)},
        }), 0, ""

    async def _dispatch(self, tool_call: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a tool call to the corresponding primitive."""
        name = tool_call.get("name", "")
        args = tool_call.get("arguments", {})

        if not isinstance(args, dict):
            args = {}

        primitive = self.primitives.get(name)
        if primitive is None:
            available = list(self.primitives.keys())
            return {
                "ok": False,
                "error": f"unknown tool: {name}",
                "available_tools": available,
            }

        for perm in primitive.required_permissions:
            if perm not in self.allowed_permissions:
                return {
                    "ok": False,
                    "error": f"permission denied: {perm.value}. Ask the user to grant this permission.",
                    "required": perm.value,
                }

        try:
            result = await primitive.execute(**args)
            if not isinstance(result, dict):
                result = {"ok": True, "value": result}
            return result
        except TypeError as e:
            return {"ok": False, "error": f"invalid arguments for {name}: {e}"}
        except Exception as e:
            logger.exception(f"[codex] primitive {name} failed")
            return {"ok": False, "error": str(e)}

    def _parse_step(self, content: str) -> dict[str, Any]:
        """Parse LLM output as a ReAct step."""
        text = content.strip()

        if text.startswith("```"):
            text = self._strip_code_fence(text)

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        json_in_text = self._extract_json_from_text(text)
        if json_in_text:
            return json_in_text

        return {"thought": content, "tool_calls": [], "final": False}

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """Remove markdown code fences (```json ... ```)."""
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines)

    @staticmethod
    def _extract_json_from_text(text: str) -> dict[str, Any] | None:
        """Try to find a JSON object in free-form text.

        Uses bracket-depth tracking to find candidate spans,
        avoiding O(n^2) json.loads calls on long text.
        """
        for i, ch in enumerate(text):
            if ch == '{':
                depth = 0
                for j in range(i, len(text)):
                    if text[j] == '{':
                        depth += 1
                    elif text[j] == '}':
                        depth -= 1
                        if depth == 0:
                            try:
                                parsed = json.loads(text[i:j + 1])
                                if isinstance(parsed, dict):
                                    return parsed
                            except json.JSONDecodeError:
                                break
                if depth == 0:
                    continue
        return None

    def _maybe_truncate_messages(
        self,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Simple truncation: keep system + last N messages."""
        if len(messages) <= _MESSAGES_MAX_LEN:
            return messages

        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system = [m for m in messages if m.get("role") != "system"]
        keep = _MESSAGES_MAX_LEN - len(system_msgs)
        return system_msgs + non_system[-keep:]

    @staticmethod
    def _extract_output_from_messages(messages: list[dict[str, Any]]) -> dict[str, Any]:
        """Fallback: extract output from the last observation in messages."""
        for msg in reversed(messages):
            content = msg.get("content", "")
            if content.startswith("[observation]"):
                try:
                    json_part = content.split(" -> ", 1)[1]
                    return json.loads(json_part)
                except (IndexError, json.JSONDecodeError):
                    pass
        return {"raw_output": messages[-1].get("content", "") if messages else ""}

    def info(self) -> dict[str, Any]:
        """Return session info for debugging."""
        return {
            "primitives": list(self.primitives.keys()),
            "allowed_permissions": [p.value for p in self.allowed_permissions],
            "max_iterations": self.max_iterations,
            "token_count": self._token_count,
            "max_tokens": self._max_tokens,
            "workflow_id": self.workflow_id,
        }


def build_codex_session(
    workflow_id: str = "",
    allowed_permissions: set[Permission] | None = None,
    max_iterations: int = _DEFAULT_MAX_ITER,
) -> CodexSession:
    """Factory: build a CodexSession with the default LLM, all primitives, and SSE."""
    from app.engine.factory import get_deepseek_llm

    llm = get_deepseek_llm()

    observer = None
    sse_bus = None

    if workflow_id:
        try:
            from app.engine.factory import _make_observer
            observer = _make_observer(workflow_id)
        except Exception:
            pass
        try:
            from app.services.sse_bus import sse_bus as _sse_bus
            sse_bus = _sse_bus
        except Exception:
            pass

    return CodexSession(
        llm=llm,
        allowed_permissions=allowed_permissions or set(),
        max_iterations=max_iterations,
        observer=observer,
        sse_bus=sse_bus,
        workflow_id=workflow_id,
    )