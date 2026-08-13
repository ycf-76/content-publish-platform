"""Single-shot executor.

Single round: build prompt -> call LLM (streaming) -> call Skills -> parse output.
Must support LLM streaming callback (D16 agent_thinking).
Must support tool call callback (D16 tool_call_start/end).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from app.agents.core.harness.executor.base import ExecutorBase

if TYPE_CHECKING:
    from app.agents.core.harness.runtime import AgentHarness
    from app.agents.core.schemas import WorkflowContext

logger = logging.getLogger(__name__)


class SingleShotExecutor(ExecutorBase):
    """Single-round executor used by all 6 MVP agents."""

    async def execute(
        self,
        harness: AgentHarness,
        input: dict[str, Any],
        context: WorkflowContext,
    ) -> dict[str, Any]:
        prompt = self._build_prompt(harness, input, context)
        content, token_usage = await self._call_llm_streaming(harness, prompt, context)
        raw_output = self._parse_output(content)
        if harness.skills:
            raw_output = await harness._execute_with_skills(raw_output, context)
        raw_output["_token_usage"] = token_usage
        return raw_output

    def _build_prompt(
        self,
        harness: AgentHarness,
        input: dict[str, Any],
        context: WorkflowContext,
    ) -> str:
        """Render prompt template with input, context, and memory."""
        template_vars: dict[str, Any] = {}
        template_vars.update(input)
        template_vars.update(context.model_dump())
        if harness.memory:
            template_vars["memory"] = harness.memory.to_dict()
        try:
            return harness.prompt_template.format(**template_vars)
        except (KeyError, IndexError):
            return harness.prompt_template

    async def _call_llm_streaming(
        self,
        harness: AgentHarness,
        prompt: str,
        context: WorkflowContext,
    ) -> tuple[str, int]:
        """Call LLM with streaming, emit reasoning chunks via observer.

        Falls back to non-streaming chat if stream_chat is unavailable.
        """
        messages = [{"role": "user", "content": prompt}]
        response_format = self._response_format(harness)
        content_parts: list[str] = []
        token_usage = 0

        llm = harness.llm
        if llm is None:
            return "", 0

        stream_fn = getattr(llm, "stream_chat", None)
        if stream_fn is not None:
            async for chunk in stream_fn(messages, response_format=response_format):
                reasoning = chunk.get("reasoning_content")
                if reasoning:
                    await harness.observer.emit_llm_stream(context.node_id, chunk)
                text = chunk.get("content")
                if text:
                    content_parts.append(text)
                if chunk.get("is_final"):
                    token_usage = chunk.get("token_usage", 0) or token_usage
        else:
            result = await llm.chat(messages, response_format=response_format)
            content_parts.append(result.get("content", ""))
            token_usage = result.get("token_usage", 0)
            if result.get("reasoning_content"):
                await harness.observer.emit_llm_stream(context.node_id, result)

        return "".join(content_parts), token_usage

    def _response_format(self, harness: AgentHarness) -> dict[str, Any] | None:
        """Determine response_format from output_schema."""
        if harness.output_schema is not None:
            return {"type": "json_object"}
        return None

    def _parse_output(self, content: str) -> dict[str, Any]:
        """Parse LLM output as JSON. Tolerant of markdown fences."""
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
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        except json.JSONDecodeError:
            logger.warning("LLM output is not valid JSON, wrapping as raw text")
            return {"raw_text": content}
