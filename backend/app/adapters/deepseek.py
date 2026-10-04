"""DeepSeek adapter (V3 + R1).

Uses OpenAI-compatible API (DeepSeek is OpenAI-compatible).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from openai import APIConnectionError, AsyncOpenAI, RateLimitError

from app.adapters.llm_base import BaseLLM, ChatMessage, LLMConfig

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

# 成本控制：单次调用最大输出 token 数（防止 LLM 输出失控烧钱）
# DeepSeek-V3 输入 2元/百万token，输出 8元/百万token
# 4096 token 输出 ≈ 0.033元/次，覆盖长程多工具编排的复杂 JSON 输出
_DEFAULT_MAX_TOKENS = 4096


class DeepSeekAdapter(BaseLLM):
    """DeepSeek-V3 (default) and DeepSeek-R1 (reasoning-only).

    R1 reasoning is streamed via reasoning_content field.
    Supports JSON mode via response_format.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        temperature: float = 0.7,
    ) -> None:
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=120.0,
            max_retries=2,
        )
        self.model = model
        # 温度参数：用户可在右侧工作区调节，影响文本生成随机性
        # 0.0 = 确定性输出（适合专业干货），1.0 = 高随机性（适合活泼少女风）
        self._temperature = float(max(0.0, min(1.0, temperature)))
        self._config = LLMConfig(
            model_name=model,
            temperature=self._temperature,
            max_tokens=max_tokens,
        )
        self._max_tokens = max_tokens

    @property
    def model_name(self) -> str:
        return self.model

    async def _chat_impl(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Non-streaming chat with optional JSON mode."""
        openai_messages = [ChatMessage(**m).model_dump() for m in messages]
        effective_max_tokens = max_tokens if max_tokens is not None else self._max_tokens
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": effective_max_tokens,
            "temperature": self._temperature,
        }
        if response_format and response_format.get("type") == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                resp = await self.client.chat.completions.create(**kwargs)
                choice = resp.choices[0]
                content = choice.message.content or ""
                reasoning = getattr(choice.message, "reasoning_content", None)
                if resp.usage:
                    prompt_t = resp.usage.prompt_tokens or 0
                    completion_t = resp.usage.completion_tokens or 0
                    total_t = resp.usage.total_tokens or 0
                    logger.info(
                        f"[deepseek] token usage: prompt={prompt_t}, "
                        f"completion={completion_t}, total={total_t}, "
                        f"model={self.model}"
                    )
                return {
                    "content": content,
                    "reasoning_content": reasoning,
                    "token_usage": resp.usage.total_tokens if resp.usage else 0,
                }
            except RateLimitError as e:
                if attempt < max_retries:
                    wait = 2 ** attempt + 1
                    logger.warning(
                        f"[deepseek] 429 rate limited (attempt {attempt+1}/{max_retries+1}), "
                        f"retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"[deepseek] 429 exhausted retries: {e}")
                raise
            except APIConnectionError as e:
                if attempt < max_retries:
                    wait = 2 ** attempt + 1
                    logger.warning(
                        f"[deepseek] connection error (attempt {attempt+1}/{max_retries+1}), "
                        f"retrying in {wait}s: {e}"
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"[deepseek] connection error exhausted retries: {e}")
                raise
            except Exception as e:
                logger.error(f"DeepSeek chat failed: {e}")
                raise

    async def _stream_chat_impl(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming chat with reasoning content and tool calling support.

        Yields chunks: content, reasoning_content, tool_calls, is_final, token_usage.
        """
        openai_messages = [ChatMessage(**m).model_dump() for m in messages]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "stream": True,
        }
        if response_format and response_format.get("type") == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                stream = await self.client.chat.completions.create(**kwargs)
                break
            except RateLimitError:
                if attempt < max_retries:
                    wait = 2 ** attempt + 1
                    logger.warning(
                        f"[deepseek] stream 429 rate limited (attempt {attempt+1}/{max_retries+1}), "
                        f"retrying in {wait}s"
                    )
                    await asyncio.sleep(wait)
                    continue
                raise
            except APIConnectionError as e:
                if attempt < max_retries:
                    wait = 2 ** attempt + 1
                    logger.warning(
                        f"[deepseek] stream connection error (attempt {attempt+1}/{max_retries+1}), "
                        f"retrying in {wait}s: {e}"
                    )
                    await asyncio.sleep(wait)
                    continue
                logger.error(f"[deepseek] stream connection error exhausted retries: {e}")
                raise
        try:
            _tool_calls_buffer: dict[int, dict[str, Any]] = {}
            async for chunk in stream:
                choice = chunk.choices[0]
                delta = choice.delta
                content = delta.content
                reasoning = getattr(delta, "reasoning_content", None)
                is_final = choice.finish_reason is not None
                token_usage = chunk.usage.total_tokens if chunk.usage else None

                delta_tool_calls = getattr(delta, "tool_calls", None)
                if delta_tool_calls:
                    for tc_delta in delta_tool_calls:
                        idx = tc_delta.index if hasattr(tc_delta, 'index') and tc_delta.index is not None else 0
                        if idx not in _tool_calls_buffer:
                            _tool_calls_buffer[idx] = {
                                "id": getattr(tc_delta, 'id', None) or "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            }
                        if hasattr(tc_delta, 'id') and tc_delta.id:
                            _tool_calls_buffer[idx]["id"] = tc_delta.id
                        func_delta = getattr(tc_delta, 'function', None)
                        if func_delta:
                            if getattr(func_delta, 'name', None):
                                _tool_calls_buffer[idx]["function"]["name"] += func_delta.name
                            if getattr(func_delta, 'arguments', None):
                                _tool_calls_buffer[idx]["function"]["arguments"] += func_delta.arguments

                chunk_dict: dict[str, Any] = {}
                if content is not None:
                    chunk_dict["content"] = content
                if reasoning is not None:
                    chunk_dict["reasoning_content"] = reasoning
                if is_final:
                    chunk_dict["is_final"] = True
                    if _tool_calls_buffer:
                        chunk_dict["tool_calls"] = [
                            _tool_calls_buffer[i] for i in sorted(_tool_calls_buffer.keys())
                        ]
                if token_usage is not None:
                    chunk_dict["token_usage"] = token_usage
                if chunk_dict:
                    yield chunk_dict
        except Exception as e:
            logger.error(f"DeepSeek streaming failed: {e}")
            raise