"""
Model Router - 智能模型路由与动态切换系统
==========================================

功能：
1. 统一的模型调用接口（屏蔽底层差异）
2. 动态模型切换（运行时/对话式）
3. 智能模型推荐（基于任务特征）
4. 模型降级与回退（主模型失败→备用模型）
5. 成本优化（根据预算自动选择）
6. 模型版本管理

支持的模型：
- 文本生成: DeepSeek, OpenAI GPT, Claude, Qwen, 通义千问
- 图片理解: Qwen-VL, GPT-4V
- 图片生成: Wanx(通义万相), Pollinations, DALL-E, Stable Diffusion

使用方式：
    from app.adapters.model_router import ModelRouter, ModelConfig
    
    router = ModelRouter()
    
    # 方式1: 直接调用（自动路由到最优模型）
    result = await router.chat(
        messages=[{"role": "user", "content": "写一篇小红书文案"}],
        task_type="copywrite",  # 任务类型
        budget=0.01,           # 成本预算（元/次）
    )
    
    # 方式2: 指定模型
    result = await router.chat(
        messages=[...],
        model_id="deepseek-chat",
    )
    
    # 方式3: 对话式模式中的动态切换
    async for event in router.chat_interactive(
        messages=[...],
        allow_user_switch=True,  # 允许用户手动切换
    ):
        if event.type == "model_switch_request":
            # 让用户选择模型
            await show_model_selector(event.available_models)
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, AsyncGenerator

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    COPYWRITE = "copywrite"
    ANALYZE = "analyze"
    IMAGE_GEN = "image_gen"
    IMAGE_REVIEW = "image_review"
    TRANSLATE = "translate"
    SUMMARIZE = "summarize"
    CODE = "code"
    GENERAL = "general"


class ModelTier(str, Enum):
    PREMIUM = "premium"
    STANDARD = "standard"
    BUDGET = "budget"
    FALLBACK = "fallback"


class ModelProvider(str, Enum):
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ALIBABA = "alibaba"
    POLLINATIONS = "pollinations"
    LOCAL = "local"


@dataclass
class ModelConfig:
    model_id: str
    provider: ModelProvider
    display_name: str

    capabilities: List[str] = field(default_factory=lambda: [
        "text_generation", "chat", "function_calling"
    ])

    tier: ModelTier = ModelTier.STANDARD
    quality_score: float = 8.0
    speed_score: float = 8.0

    cost_per_1k_tokens: float = 0.001
    cost_per_image: float = 0.0
    max_tokens: int = 4096

    best_for: List[TaskType] = field(default_factory=list)
    avoid_for: List[TaskType] = field(default_factory=list)

    config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.best_for:
            self.best_for = [TaskType.GENERAL]

    @property
    def is_available(self) -> bool:
        try:
            if self.provider == ModelProvider.DEEPSEEK:
                from app.config import get_settings
                return bool(get_settings().deepseek_api_key)
            elif self.provider == ModelProvider.OPENAI:
                from app.config import get_settings
                return bool(get_settings().openai_api_key)
            elif self.provider == ModelProvider.ALIBABA:
                from app.config import get_settings
                return bool(get_settings().dashscope_api_key)
            else:
                return True
        except Exception as e:
            logger.warning(f"[ModelRouter] Failed to check availability for {self.model_id}: {e}")
            return False

    def estimated_cost(self, input_tokens: int = 1000, output_tokens: int = 500) -> float:
        total_tokens = (input_tokens + output_tokens) / 1000
        return total_tokens * self.cost_per_1k_tokens


@dataclass
class ChatRequest:
    messages: List[Dict[str, str]]
    task_type: TaskType = TaskType.GENERAL
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    response_format: Optional[Dict[str, str]] = None

    preferred_model: Optional[str] = None
    budget: Optional[float] = None
    require_high_quality: bool = False
    require_fast_response: bool = False
    allow_fallback: bool = True

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    success: bool
    content: str = ""
    model_used: str = ""
    provider_used: ModelProvider = None
    tokens_used: int = 0
    cost: float = 0.0
    latency_ms: int = 0
    finish_reason: str = ""

    fallback_used: bool = False
    routing_decision: str = ""

    @classmethod
    def ok(cls, content: str, **kwargs) -> "ChatResponse":
        return cls(success=True, content=content, **kwargs)

    @classmethod
    def fail(cls, error: str, **kwargs) -> "ChatResponse":
        return cls(success=False, content=f"Error: {error}", **kwargs)


@dataclass
class ModelSwitchEvent:
    event_type: str
    current_model: str
    suggested_models: List[Dict[str, Any]]
    user_choice: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ModelRouter:

    def __init__(self):
        self._models: Dict[str, ModelConfig] = {}
        self._adapters: Dict[ModelProvider, Any] = {}
        self._resolve_cache: Dict[str, Any] = {}

        self._stats = {
            "total_calls": 0,
            "by_model": {},
            "total_cost": 0.0,
            "total_tokens": 0,
            "fallback_count": 0,
            "errors": 0,
        }

        self._register_builtin_models()

        logger.info("[ModelRouter] Initialized with %d models", len(self._models))

    def _register_builtin_models(self):
        self.register(ModelConfig(
            model_id="deepseek-chat",
            provider=ModelProvider.DEEPSEEK,
            display_name="DeepSeek V3 (通用)",
            capabilities=["text_generation", "chat", "code"],
            tier=ModelTier.STANDARD,
            quality_score=8.5,
            speed_score=9.0,
            cost_per_1k_tokens=0.001,
            max_tokens=8192,
            best_for=[TaskType.COPYWRITE, TaskType.ANALYZE, TaskType.GENERAL],
            config={"temperature_range": [0, 2]},
        ))

        self.register(ModelConfig(
            model_id="deepseek-coder",
            provider=ModelProvider.DEEPSEEK,
            display_name="DeepSeek Coder (代码)",
            capabilities=["text_generation", "code", "reasoning"],
            tier=ModelTier.STANDARD,
            quality_score=8.8,
            speed_score=8.5,
            cost_per_1k_tokens=0.001,
            max_tokens=16384,
            best_for=[TaskType.CODE],
        ))

        self.register(ModelConfig(
            model_id="gpt-4o",
            provider=ModelProvider.OPENAI,
            display_name="GPT-4o (最新旗舰)",
            capabilities=["text_generation", "vision", "function_calling"],
            tier=ModelTier.PREMIUM,
            quality_score=9.5,
            speed_score=7.5,
            cost_per_1k_tokens=0.09,
            max_tokens=4096,
            best_for=[TaskType.ANALYZE, TaskType.IMAGE_REVIEW],
            config={"supports_vision": True},
        ))

        self.register(ModelConfig(
            model_id="gpt-4o-mini",
            provider=ModelProvider.OPENAI,
            display_name="GPT-4o Mini (性价比)",
            capabilities=["text_generation", "vision"],
            tier=ModelTier.STANDARD,
            quality_score=8.0,
            speed_score=9.0,
            cost_per_1k_tokens=0.01,
            max_tokens=4096,
            best_for=[TaskType.TRANSLATE, TaskType.SUMMARIZE],
        ))

        self.register(ModelConfig(
            model_id="claude-3-5-sonnet-20241022",
            provider=ModelProvider.ANTHROPIC,
            display_name="Claude 3.5 Sonnet",
            capabilities=["text_generation", "long_context", "analysis"],
            tier=ModelTier.PREMIUM,
            quality_score=9.3,
            speed_score=8.0,
            cost_per_1k_tokens=0.05,
            max_tokens=8192,
            best_for=[TaskType.COPYWRITE, TaskType.ANALYZE],
            config={"max_context": 200000},
        ))

        self.register(ModelConfig(
            model_id="qwen-turbo",
            provider=ModelProvider.ALIBABA,
            display_name="Qwen Turbo (通义千问)",
            capabilities=["text_generation", "chat", "chinese"],
            tier=ModelTier.BUDGET,
            quality_score=7.5,
            speed_score=9.5,
            cost_per_1k_tokens=0.0004,
            max_tokens=6000,
            best_for=[TaskType.SUMMARIZE, TaskType.TRANSLATE, TaskType.GENERAL],
        ))

        self.register(ModelConfig(
            model_id="qwen-max",
            provider=ModelProvider.ALIBABA,
            display_name="Qwen Max (通义千问旗舰)",
            capabilities=["text_generation", "reasoning", "chinese"],
            tier=ModelTier.STANDARD,
            quality_score=8.5,
            speed_score=7.5,
            cost_per_1k_tokens=0.002,
            max_tokens=8000,
            best_for=[TaskType.COPYWRITE, TaskType.ANALYZE],
        ))

        self.register(ModelConfig(
            model_id="qwen-vl-max",
            provider=ModelProvider.ALIBABA,
            display_name="Qwen-VL Max (图片理解)",
            capabilities=["vision", "image_understanding"],
            tier=ModelTier.STANDARD,
            quality_score=8.5,
            speed_score=7.0,
            cost_per_1k_tokens=0.003,
            max_tokens=2000,
            best_for=[TaskType.IMAGE_REVIEW],
        ))

        self.register(ModelConfig(
            model_id="wanx-v1",
            provider=ModelProvider.ALIBABA,
            display_name="通义万相 V1",
            capabilities=["image_generation"],
            tier=ModelTier.STANDARD,
            quality_score=8.0,
            speed_score=7.0,
            cost_per_image=0.02,
            best_for=[TaskType.IMAGE_GEN],
            config={"size_options": ["1024x1024", "768x1344", "1344x768"]},
        ))

        self.register(ModelConfig(
            model_id="pollinations-free",
            provider=ModelProvider.POLLINATIONS,
            display_name="Pollinations (免费)",
            capabilities=["image_generation"],
            tier=ModelTier.FALLBACK,
            quality_score=6.0,
            speed_score=6.0,
            cost_per_image=0.0,
            best_for=[TaskType.IMAGE_GEN],
            avoid_for=[TaskType.IMAGE_GEN],
            config={"requires_proxy": True},
        ))

    def register(self, model_config: ModelConfig):
        self._models[model_config.model_id] = model_config
        logger.info("[ModelRouter] Registered model: %s (%s)",
                   model_config.model_id, model_config.display_name)

    def resolve_llm(
        self,
        model: str | None = None,
        temperature: float | None = None,
    ) -> Any | None:
        from app.config import get_settings
        from app.adapters.deepseek import DeepSeekAdapter

        s = get_settings()
        if not s.deepseek_api_key:
            logger.warning("[ModelRouter] resolve_llm: deepseek_api_key 未配置")
            return None

        model_name = model or s.deepseek_model_v3
        temp_val = 0.7 if temperature is None else float(max(0.0, min(1.0, temperature)))

        _cache_key = f"{model_name}|{temp_val:.3f}"
        if _cache_key in self._resolve_cache:
            return self._resolve_cache[_cache_key]

        try:
            adapter = DeepSeekAdapter(
                api_key=s.deepseek_api_key,
                base_url=s.deepseek_base_url,
                model=model_name,
                temperature=temp_val,
            )
            self._adapters[ModelProvider.DEEPSEEK] = adapter
            self._resolve_cache[_cache_key] = adapter
            return adapter
        except Exception as e:
            logger.warning(f"[ModelRouter] resolve_llm failed: {e}")
            return None

    async def route(self, request: ChatRequest) -> ChatResponse:
        start_time = time.time()
        self._stats["total_calls"] += 1

        try:
            selected_model = self._select_model(request)

            if not selected_model:
                return ChatResponse.fail("No suitable model available")

            logger.info(
                "[ModelRouter] Selected model: %s (tier=%s, reason=%s)",
                selected_model.model_id,
                selected_model.tier.value,
                getattr(request, '_routing_reason', 'user_specified')
            )

            adapter = self._get_adapter(selected_model.provider)

            response_content, tokens_used, finish_reason = await adapter.chat(
                messages=request.messages,
                model=selected_model.model_id,
                temperature=request.temperature,
                max_tokens=request.max_tokens or selected_model.max_tokens,
                response_format=request.response_format,
                config=selected_model.config,
            )

            latency_ms = int((time.time() - start_time) * 1000)
            cost = selected_model.estimated_cost(input_tokens=len(str(request.messages)),
                                                output_tokens=tokens_used)

            self._update_stats(selected_model.model_id, tokens_used, cost)

            return ChatResponse.ok(
                content=response_content,
                model_used=selected_model.model_id,
                provider_used=selected_model.provider,
                tokens_used=tokens_used,
                cost=cost,
                latency_ms=latency_ms,
                finish_reason=finish_reason,
                routing_decision=getattr(request, '_routing_reason', ''),
            )

        except Exception as e:
            self._stats["errors"] += 1
            logger.exception("[ModelRouter] Model execution failed: %s", e)

            if request.allow_fallback:
                return await self._try_fallback(request, original_error=str(e))

            return ChatResponse.fail(f"All models failed: {e}")

    @property
    def model_name(self) -> str:
        return "model-router"

    async def chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        request = ChatRequest(messages=messages, response_format=response_format)
        resp = await self.route(request)
        if not resp.success:
            raise RuntimeError(resp.content or "ModelRouter routing failed")
        return {
            "content": resp.content,
            "reasoning_content": None,
            "token_usage": resp.tokens_used,
        }

    async def stream_chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        from app.config import get_settings
        s = get_settings()
        model_name = s.deepseek_model_v3
        adapter = self.resolve_llm(model=model_name)
        if adapter and hasattr(adapter, 'stream_chat'):
            async for chunk in adapter.stream_chat(messages, response_format, tools):
                yield chunk
            return
        result = await self.chat(messages, response_format)
        yield {
            "content": result["content"],
            "reasoning_content": result.get("reasoning_content"),
            "is_final": True,
            "token_usage": result["token_usage"],
        }

    async def chat_interactive(
        self,
        request: ChatRequest,
        allow_user_switch: bool = False,
        on_switch_request: Optional[callable] = None,
    ) -> AsyncGenerator[Any, None]:
        initial_model = self._select_model(request)

        current_model = initial_model
        switched = False

        while True:
            try:
                if allow_user_switch and not switched:
                    switch_suggestion = self._should_suggest_switch(current_model, request)

                    if switch_suggestion:
                        switch_event = ModelSwitchEvent(
                            event_type="switch_required",
                            current_model=current_model.model_id,
                            suggested_models=switch_suggestion,
                            metadata={
                                "current_tier": current_model.tier.value,
                                "current_quality": current_model.quality_score,
                                "reason": "better_model_available",
                            },
                        )

                        yield switch_event

                        if on_switch_request:
                            user_choice = await on_switch_request(switch_event)

                            if user_choice and user_choice in self._models:
                                current_model = self._models[user_choice]
                                switched = True

                                yield ModelSwitchEvent(
                                    event_type="switch_completed",
                                    current_model=current_model.model_id,
                                    user_choice=user_choice,
                                )

                        else:
                            yield ModelSwitchEvent(
                                event_type="switch_rejected",
                                current_model=current_model.model_id,
                            )

                response = await self.route(ChatRequest(
                    **request.__dict__,
                    preferred_model=current_model.model_id,
                    allow_fallback=False,
                ))

                yield response
                break

            except Exception as e:
                if not allow_user_switch:
                    fallback_resp = await self._try_fallback(request, str(e))
                    yield fallback_resp
                    break
                else:
                    raise

    def _select_model(self, request: ChatRequest) -> Optional[ModelConfig]:
        if request.preferred_model and request.preferred_model in self._models:
            model = self._models[request.preferred_model]
            if model.is_available:
                request._routing_reason = "user_specified"
                return model
            else:
                logger.warning("[ModelRouter] User requested model %s is unavailable",
                              request.preferred_model)

        available_models = [m for m in self._models.values() if m.is_available]

        if not available_models:
            logger.error("[ModelRouter] No models available")
            return None

        if request.budget:
            affordable_models = [
                m for m in available_models
                if m.estimated_cost() <= request.budget
            ]
            if affordable_models:
                available_models = affordable_models
            else:
                logger.warning("[ModelRouter] No models within budget %.4f, using cheapest", request.budget)
                available_models = [min(available_models, key=lambda m: m.estimated_cost())]

        scored_models = []
        for model in available_models:
            score = 0

            if request.task_type in model.best_for:
                score += 20
            if request.task_type in model.avoid_for:
                score -= 30

            if request.require_high_quality and model.tier == ModelTier.PREMIUM:
                score += 15
            elif request.require_high_quality and model.tier == ModelTier.BUDGET:
                score -= 10

            if request.require_fast_response and model.speed_score >= 8.5:
                score += 10

            score += model.quality_score * 2

            if request.budget:
                cost_ratio = model.estimated_cost() / request.budget
                if cost_ratio > 0.8:
                    score -= 5

            scored_models.append((score, model))

        scored_models.sort(key=lambda x: x[0], reverse=True)

        best_model = scored_models[0][1]
        request._routing_reason = f"auto_selected_{best_model.tier.value}"

        return best_model

    def _should_suggest_switch(
        self,
        current_model: ModelConfig,
        request: ChatRequest
    ) -> Optional[List[Dict[str, Any]]]:
        suggestions = []

        for model in self._models.values():
            if not model.is_available or model.model_id == current_model.model_id:
                continue

            should_suggest = False
            reasons = []

            if (model.quality_score > current_model.quality_score + 1.5 and
                model.estimated_cost() < current_model.estimated_cost() * 1.5):
                should_suggest = True
                reasons.append(f"质量更高 ({model.quality_score} vs {current_model.quality_score})")

            if (request.task_type in model.best_for and
                request.task_type not in current_model.best_for):
                should_suggest = True
                reasons.append(f"更适合{request.task_type.value}任务")

            if (model.speed_score > current_model.speed_score + 1.0 and
                abs(model.quality_score - current_model.quality_score) <= 0.5):
                should_suggest = True
                reasons.append(f"响应更快 ({model.speed_score} vs {current_model.speed_score})")

            if should_suggest:
                suggestions.append({
                    "model_id": model.model_id,
                    "display_name": model.display_name,
                    "provider": model.provider.value,
                    "tier": model.tier.value,
                    "quality_score": model.quality_score,
                    "speed_score": model.speed_score,
                    "estimated_cost": f"¥{model.estimated_cost():.4f}",
                    "reasons": reasons,
                })

        return suggestions[:3] if suggestions else None

    async def _try_fallback(
        self,
        request: ChatRequest,
        original_error: str
    ) -> ChatResponse:
        self._stats["fallback_count"] += 1

        logger.warning(
            "[ModelRouter] Primary model failed, trying fallback. Error: %s",
            original_error
        )

        fallback_order = [
            ModelTier.STANDARD,
            ModelTier.BUDGET,
            ModelTier.PREMIUM,
        ]

        for tier in fallback_order:
            fallback_request = ChatRequest(
                **request.__dict__,
                preferred_model=None,
                allow_fallback=False,
            )

            fallback_candidates = [
                m for m in self._models.values()
                if m.tier == tier and m.is_available and m.model_id != request.preferred_model
            ]

            if fallback_candidates:
                best_fallback = max(fallback_candidates,
                                   key=lambda m: m.quality_score)

                try:
                    response = await self.route(ChatRequest(
                        **request.__dict__,
                        preferred_model=best_fallback.model_id,
                        allow_fallback=False,
                    ))

                    response.fallback_used = True
                    response.routing_decision = (
                        f"fallback_from_error (original: {original_error[:50]})"
                    )

                    return response

                except Exception as fallback_error:
                    logger.warning(
                        "[ModelRouter] Fallback to %s also failed: %s",
                        best_fallback.model_id,
                        fallback_error
                    )
                    continue

        return ChatResponse.fail(f"All models exhausted. Original: {original_error}")

    def _get_adapter(self, provider: ModelProvider):
        if provider in self._adapters:
            return self._adapters[provider]

        adapter = None

        if provider == ModelProvider.DEEPSEEK:
            adapter = self.resolve_llm()

        elif provider == ModelProvider.OPENAI:
            from langchain_openai import ChatOpenAI
            adapter = ChatOpenAI

        elif provider == ModelProvider.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic
            adapter = ChatAnthropic

        elif provider == ModelProvider.ALIBABA:
            if "vl" in str(self._models):
                from app.adapters.qwen_vl import QwenVLAdapter
                adapter = QwenVLAdapter
            else:
                from langchain_community.chat_models import ChatTongyi
                adapter = ChatTongyi

        elif provider == ModelProvider.POLLINATIONS:
            from app.adapters.image_gen import PollinationsAdapter
            adapter = PollinationsAdapter

        if adapter:
            self._adapters[provider] = adapter
            logger.info("[ModelRouter] Loaded adapter for %s", provider.value)

        return adapter

    def _update_stats(self, model_id: str, tokens: int, cost: float):
        if model_id not in self._stats["by_model"]:
            self._stats["by_model"][model_id] = {
                "calls": 0,
                "tokens": 0,
                "cost": 0.0,
            }

        stats = self._stats["by_model"][model_id]
        stats["calls"] += 1
        stats["tokens"] += tokens
        stats["cost"] += cost

        self._stats["total_tokens"] += tokens
        self._stats["total_cost"] += cost

    def get_stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "available_models": len([m for m in self._models.values() if m.is_available]),
            "total_registered": len(self._models),
        }

    def list_models(
        self,
        tier: Optional[ModelTier] = None,
        provider: Optional[ModelProvider] = None,
        capability: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        models = []

        for model in self._models.values():
            if tier and model.tier != tier:
                continue
            if provider and model.provider != provider:
                continue
            if capability and capability not in model.capabilities:
                continue

            models.append({
                "model_id": model.model_id,
                "display_name": model.display_name,
                "provider": model.provider.value,
                "tier": model.tier.value,
                "is_available": model.is_available,
                "quality_score": model.quality_score,
                "speed_score": model.speed_score,
                "estimated_cost_per_call": f"¥{model.estimated_cost():.4f}",
                "capabilities": model.capabilities,
                "best_for": [t.value for t in model.best_for],
            })

        return models


_router_instance: Optional[ModelRouter] = None

def get_model_router() -> ModelRouter:
    global _router_instance
    if _router_instance is None:
        _router_instance = ModelRouter()
    return _router_instance