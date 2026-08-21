"""Chat completions API — OpenAI-compatible streaming endpoint.

Provides a /api/v1/chat/completions endpoint that proxies to
the configured LLM (DeepSeek-V3 / R1) with SSE streaming.
Also provides a /api/v1/chat/highlight endpoint for the Highlight Agent.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import get_settings
from app.security import decode_user_id

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    jwt_token: str | None = None
    if credentials is not None and (credentials.scheme or "").lower() == "bearer":
        jwt_token = credentials.credentials
    if not jwt_token:
        return "anonymous"
    try:
        return decode_user_id(jwt_token)
    except Exception:
        return "anonymous"

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

SYSTEM_PROMPT = "You are a helpful coding assistant."


class ChatMessageIn(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn]
    model: str = "DeepSeek-V3"
    stream: bool = True
    thinking_depth: str = "off"
    temperature: float | None = None
    max_tokens: int | None = None


def _resolve_model(request: ChatRequest) -> tuple[str, str, float | None]:
    """Return (api_model, base_url, temperature) based on user selection."""
    settings = get_settings()
    model_map = {
        "DeepSeek-V3": settings.deepseek_model_v3,
        "DeepSeek-R1": settings.deepseek_model_r1,
    }
    api_model = model_map.get(request.model, settings.deepseek_model_v3)
    base_url = settings.deepseek_base_url
    temp = request.temperature
    return api_model, base_url, temp


async def _stream_openai_compatible(
    request: ChatRequest,
    api_key: str,
    api_model: str,
    base_url: str,
    temperature: float | None,
) -> Any:
    """Yield SSE lines from an OpenAI-compatible API."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    messages_payload: list[dict[str, str]] = []
    has_system = any(m.role == "system" for m in request.messages)
    if not has_system:
        messages_payload.append({"role": "system", "content": SYSTEM_PROMPT})
    for m in request.messages:
        messages_payload.append({"role": m.role, "content": m.content})

    kwargs: dict[str, Any] = {
        "model": api_model,
        "messages": messages_payload,
        "stream": True,
        "stream_options": {"include_usage": False},
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if request.max_tokens:
        kwargs["max_tokens"] = request.max_tokens

    response = await client.chat.completions.create(**kwargs)
    async for chunk in response:
        yield chunk


@router.post("/completions")
async def chat_completions(
    request: ChatRequest,
    current_user=Depends(get_optional_user),
):
    """OpenAI-compatible chat completions with SSE streaming."""
    settings = get_settings()
    api_key = settings.deepseek_api_key
    if not api_key:
        return StreamingResponse(
            _error_stream("未配置 DeepSeek API Key，请在设置中配置"),
            media_type="text/event-stream",
        )

    api_model, base_url, temperature = _resolve_model(request)

    async def generate():
        chat_id = f"chatcmpl-{uuid.uuid4().hex[:24]}"
        created = int(time.time())
        full_text = ""
        try:
            async for chunk in _stream_openai_compatible(
                request, api_key, api_model, base_url, temperature
            ):
                delta = {}
                if chunk.choices and chunk.choices[0].delta:
                    d = chunk.choices[0].delta
                    if hasattr(d, "reasoning_content") and d.reasoning_content:
                        delta["reasoning_content"] = d.reasoning_content
                    if d.content:
                        delta["content"] = d.content
                        full_text += d.content
                    if d.role:
                        delta["role"] = d.role

                payload = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": api_model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": delta,
                            "finish_reason": chunk.choices[0].finish_reason if chunk.choices else None,
                        }
                    ],
                }
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

            # 流式结束后，异步调用 Highlight Agent
            if full_text.strip():
                highlighted = await _call_highlight_agent(full_text)
                if highlighted is not None:
                    highlight_event = {
                        "type": "highlight",
                        "highlighted_text": highlighted,
                    }
                    yield f"event: highlight\ndata: {json.dumps(highlight_event, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.error("[chat] stream error: %s", e)
            yield _error_chunk(chat_id, created, api_model, str(e))
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _error_stream(msg: str):
    payload = {
        "id": f"chatcmpl-error",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "error",
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": f"❌ {msg}"},
                "finish_reason": "stop",
            }
        ],
    }
    yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


def _error_chunk(chat_id: str, created: int, model: str, msg: str) -> str:
    payload = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"content": f"\n\n❌ 请求出错: {msg}"},
                "finish_reason": "stop",
            }
        ],
    }
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ═══════════════════════════════════════════════════════════
# Highlight Agent — 后端独立 LLM 调用，为主模型回复划重点
# ═══════════════════════════════════════════════════════════

HIGHLIGHT_PROMPT = """你是一个划重点助手。阅读下面的文本，找出最值得注意的关键内容，用 ==双等号== 包裹它们。

【格式要求 - 最重要】
你必须且只能用 == 来标记重点。格式：==重点内容==
- 正确：==降噪深度 35dB==
- 正确：==续航长达 40 小时==
- 错误：**降噪深度 35dB**（不要用加粗）
- 错误：【降噪深度 35dB】（不要用括号）
- 错误：`降噪深度 35dB`（不要用代码格式）

【标记规则】
- 每个段落标记 1-2 处信息密度最高的片段
- 整篇文本标记总数不超过 5 处
- 优先标记：关键数据/指标、核心结论、因果关系、对比差异
- 不标记：标题、列表标记、语气词、普通描述、过渡句
- 每处标记 4-20 字，不要跨句子标记
- 输出必须与原文完全一致，只添加 == 标记，不增删改任何文字

【示例】
输入：降噪深度 35dB，续航长达 40 小时，是目前性价比最高的耳机。售价仅 899 元。
输出：==降噪深度 35dB==，==续航长达 40 小时==，是目前性价比最高的耳机。==售价仅 899 元==。

文本：
{text}"""


class HighlightRequest(BaseModel):
    text: str
    density: str = "medium"


async def _call_highlight_agent(text: str, density: str = "medium") -> str | None:
    """调用轻量 LLM 对文本划重点，返回带 ==...== 标记的文本。"""
    settings = get_settings()
    api_key = settings.deepseek_api_key
    if not api_key:
        logger.warning("[highlight] no API key configured, skipping")
        return None

    base_url = settings.deepseek_base_url
    model = settings.deepseek_model_v3

    density_hint = ""
    if density == "low":
        density_hint = "\n额外要求：标记不超过 3 处，只标记最核心的结论。"
    elif density == "high":
        density_hint = "\n额外要求：可标记至多 8 处，包括重要细节和支撑论据。"

    prompt = HIGHLIGHT_PROMPT.format(text=text) + density_hint

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        system_msg = {
            "role": "system",
            "content": "你是划重点助手。你只能用 ==双等号== 标记重点，例如 ==重点内容==。绝对不要用 **加粗**、括号或任何其他格式来标记重点。输出必须与原文完全一致，只添加 == 标记。",
        }
        user_msg = {"role": "user", "content": prompt}

        for attempt in range(2):
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=model,
                    messages=[system_msg, user_msg],
                    temperature=0.1 if attempt == 0 else 0.3,
                    max_tokens=len(text) + 200,
                ),
                timeout=8.0,
            )
            result = response.choices[0].message.content
            if not result:
                continue

            # 格式修复：LLM 可能用 **...** 替代 ==...==，自动转换
            # 只在原文没有 ** 时才转换（避免误伤原文中的加粗）
            if "**" not in text:
                result = re.sub(r'\*\*(.+?)\*\*', r'==\1==', result)
            # LLM 可能用 【...】 替代 ==...==，自动转换
            if "【" not in text:
                result = re.sub(r'【(.+?)】', r'==\1==', result)

            # 基本校验：结果应包含 == 标记
            if "==" in result:
                break

            logger.warning("[highlight] attempt %d: no markers, %s", attempt + 1, "retrying" if attempt == 0 else "giving up")
        else:
            return None

        # 去掉 == 标记后与原文比对，差异过大则丢弃
        stripped = result.replace("==", "")
        # 允许一定容差（空白差异等），但长度差异不超过 30%
        if len(stripped) > 0 and abs(len(stripped) - len(text)) / max(len(text), 1) > 0.3:
            logger.warning(
                "[highlight] agent output length mismatch: orig=%d stripped=%d, discarding",
                len(text),
                len(stripped),
            )
            return None

        return result

    except asyncio.TimeoutError:
        logger.warning("[highlight] agent timed out, skipping")
        return None
    except Exception as e:
        logger.error("[highlight] agent error: %s", e)
        return None


@router.post("/highlight")
async def highlight_text(
    request: HighlightRequest,
    current_user=Depends(get_optional_user),
):
    """接收一段文本，返回带 ==...== 标记的版本。"""
    if not request.text or not request.text.strip():
        return {"highlighted_text": request.text}

    result = await _call_highlight_agent(request.text, request.density)
    if result is None:
        return {"highlighted_text": request.text}

    return {"highlighted_text": result}