"""DeepSeek adapter (V3 + R1).

Uses OpenAI-compatible API (DeepSeek is OpenAI-compatible).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from openai import AsyncOpenAI

from app.agents.adapters.llm_base import BaseLLM, ChatMessage, LLMConfig

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

# 成本控制：单次调用最大输出 token 数（防止 LLM 输出失控烧钱）
# DeepSeek-V3 输入 2元/百万token，输出 8元/百万token
# 1500 token 输出 ≈ 0.012元/次，足够覆盖 JSON 结构化输出
_DEFAULT_MAX_TOKENS = 1500


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
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
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
    ) -> dict[str, Any]:
        """Non-streaming chat with optional JSON mode."""
        openai_messages = [ChatMessage(**m).model_dump() for m in messages]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "max_tokens": self._max_tokens,  # 成本控制：限制输出 token
            "temperature": self._temperature,  # 用户在右侧工作区调节的温度
        }
        if response_format and response_format.get("type") == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = await self.client.chat.completions.create(**kwargs)
            choice = resp.choices[0]
            content = choice.message.content or ""
            # reasoning_content 仅 R1 模型返回，V3 无此字段，用 getattr 安全访问
            reasoning = getattr(choice.message, "reasoning_content", None)
            # 成本日志：打印 token 用量，方便追踪消耗
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
        except Exception as e:
            logger.error(f"DeepSeek chat failed: {e}")
            raise

    async def _stream_chat_impl(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Streaming chat with reasoning content support.

        Yields chunks: content, reasoning_content, is_final, token_usage.
        """
        openai_messages = [ChatMessage(**m).model_dump() for m in messages]
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "stream": True,
        }
        if response_format and response_format.get("type") == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        try:
            stream = await self.client.chat.completions.create(**kwargs)
            async for chunk in stream:
                delta = chunk.choices[0].delta
                content = delta.content
                # reasoning_content 仅 R1 流式返回，V3 无此字段，用 getattr 安全访问
                reasoning = getattr(delta, "reasoning_content", None)
                is_final = chunk.choices[0].finish_reason is not None
                token_usage = chunk.usage.total_tokens if chunk.usage else None

                chunk_dict: dict[str, Any] = {}
                if content is not None:
                    chunk_dict["content"] = content
                if reasoning is not None:
                    chunk_dict["reasoning_content"] = reasoning
                if is_final:
                    chunk_dict["is_final"] = True
                if token_usage is not None:
                    chunk_dict["token_usage"] = token_usage
                if chunk_dict:
                    yield chunk_dict
        except Exception as e:
            logger.error(f"DeepSeek streaming failed: {e}")
            raise