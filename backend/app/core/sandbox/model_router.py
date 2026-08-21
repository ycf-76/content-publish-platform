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
    from app.core.sandbox.model_router import ModelRouter, ModelConfig
    
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


# ===== 枚举定义 =====

class TaskType(str, Enum):
    """任务类型"""
    COPYWRITE = "copywrite"         # 文案生成
    ANALYZE = "analyze"             # 内容分析
    IMAGE_GEN = "image_gen"         # 图片生成
    IMAGE_REVIEW = "image_review"   # 图片审核
    TRANSLATE = "translate"         # 翻译
    SUMMARIZE = "summarize"         # 摘要
    CODE = "code"                   # 代码生成
    GENERAL = "general"             # 通用


class ModelTier(str, Enum):
    """模型层级"""
    PREMIUM = "premium"     # 高端（GPT-4/Claude-3）- 质量最高，成本高
    STANDARD = "standard"   # 标准（DeepSeek/Qwen）- 性价比最优
    BUDGET = "budget"       # 经济（轻量模型）- 成本最低，质量一般
    FALLBACK = "fallback"   # 兜底（规则/模板）- 无成本，质量有限


class ModelProvider(str, Enum):
    """模型提供商"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    ALIBABA = "alibaba"      # 通义千问/万相
    POLLINATIONS = "pollinations"
    LOCAL = "local"          # 本地模型


@dataclass
class ModelConfig:
    """单个模型配置"""
    model_id: str                    # 唯一标识符 (如 "deepseek-chat")
    provider: ModelProvider          # 提供商
    display_name: str                # 显示名 (如 "DeepSeek Chat")
    
    # 能力标签
    capabilities: List[str] = field(default_factory=lambda: [
        "text_generation", "chat", "function_calling"
    ])
    
    # 性能指标
    tier: ModelTier = ModelTier.STANDARD
    quality_score: float = 8.0       # 质量 (1-10)
    speed_score: float = 8.0        # 速度 (1-10)
    
    # 成本信息
    cost_per_1k_tokens: float = 0.001  # 每1k token成本（元）
    cost_per_image: float = 0.0        # 每张图片成本（仅图片生成模型使用）
    max_tokens: int = 4096            # 最大token数
    
    # 适用场景
    best_for: List[TaskType] = field(default_factory=list)
    avoid_for: List[TaskType] = field(default_factory=list)
    
    # 配置参数
    config: Dict[str, Any] = field(default_factory=dict)  # 特殊配置
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.best_for:
            self.best_for = [TaskType.GENERAL]
    
    @property
    def is_available(self) -> bool:
        """检查模型是否可用（API key是否配置等）"""
        try:
            if self.provider == ModelProvider.DEEPSEEK:
                from app.core.settings import get_settings
                return bool(get_settings().deepseek_api_key)
            elif self.provider == ModelProvider.OPENAI:
                from app.core.settings import get_settings
                return bool(get_settings().openai_api_key)
            elif self.provider == ModelProvider.ALIBABA:
                from app.core.settings import get_settings
                return bool(get_settings().dashscope_api_key)
            else:
                return True  # 其他提供商默认可用
        except Exception as e:
            logger.warning(f"[ModelRouter] Failed to check availability for {self.model_id}: {e}")
            return False
    
    def estimated_cost(self, input_tokens: int = 1000, output_tokens: int = 500) -> float:
        """估算单次调用成本"""
        total_tokens = (input_tokens + output_tokens) / 1000
        return total_tokens * self.cost_per_1k_tokens


@dataclass
class ChatRequest:
    """聊天请求"""
    messages: List[Dict[str, str]]
    task_type: TaskType = TaskType.GENERAL
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    response_format: Optional[Dict[str, str]] = None
    
    # 约束条件
    preferred_model: Optional[str] = None      # 用户偏好模型
    budget: Optional[float] = None             # 成本上限（元）
    require_high_quality: bool = False          # 要求高质量
    require_fast_response: bool = False         # 要求快速响应
    allow_fallback: bool = True                 # 允许降级
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """聊天响应"""
    success: bool
    content: str = ""
    model_used: str = ""               # 实际使用的模型
    provider_used: ModelProvider = None
    tokens_used: int = 0
    cost: float = 0.0                  # 本次调用成本
    latency_ms: int = 0                # 响应延迟
    finish_reason: str = ""
    
    # 元数据
    fallback_used: bool = False        # 是否使用了降级模型
    routing_decision: str = ""         # 路由决策原因
    
    @classmethod
    def ok(cls, content: str, **kwargs) -> "ChatResponse":
        return cls(success=True, content=content, **kwargs)
    
    @classmethod
    def fail(cls, error: str, **kwargs) -> "ChatResponse":
        return cls(success=False, content=f"Error: {error}", **kwargs)


@dataclass 
class ModelSwitchEvent:
    """模型切换事件"""
    event_type: str  # "switch_required", "switch_completed", "switch_rejected"
    current_model: str
    suggested_models: List[Dict[str, Any]]  # [{model_id, reason, estimated_cost}]
    user_choice: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ===== 核心类 =====

class ModelRouter:
    """
    智能模型路由器
    
    提供统一的LLM调用接口，支持：
    - 自动模型选择（基于任务、质量、成本）
    - 动态模型切换（运行时/用户触发）
    - 智能降级（主模型失败→备用模型）
    - 成本控制（预算约束下的最优选择）
    """
    
    def __init__(self):
        self._models: Dict[str, ModelConfig] = {}
        self._adapters: Dict[ModelProvider, Any] = {}
        
        # 使用统计
        self._stats = {
            "total_calls": 0,
            "by_model": {},
            "total_cost": 0.0,
            "total_tokens": 0,
            "fallback_count": 0,
            "errors": 0,
        }
        
        # 初始化内置模型库
        self._register_builtin_models()
        
        logger.info("[ModelRouter] Initialized with %d models", len(self._models))
    
    def _register_builtin_models(self):
        """注册内置模型配置"""
        
        # === DeepSeek 系列 ===
        self.register(ModelConfig(
            model_id="deepseek-chat",
            provider=ModelProvider.DEEPSEEK,
            display_name="DeepSeek V3 (通用)",
            capabilities=["text_generation", "chat", "code"],
            tier=ModelTier.STANDARD,
            quality_score=8.5,
            speed_score=9.0,
            cost_per_1k_tokens=0.001,  # ¥0.001/1k tokens (很便宜!)
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
        
        # === OpenAI 系列 ===
        self.register(ModelConfig(
            model_id="gpt-4o",
            provider=ModelProvider.OPENAI,
            display_name="GPT-4o (最新旗舰)",
            capabilities=["text_generation", "vision", "function_calling"],
            tier=ModelTier.PREMIUM,
            quality_score=9.5,
            speed_score=7.5,
            cost_per_1k_tokens=0.09,  # $0.005/1k input + $0.015/1k output ≈ ¥0.065
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
        
        # === Anthropic Claude ===
        self.register(ModelConfig(
            model_id="claude-3-5-sonnet-20241022",
            provider=ModelProvider.ANTHROPIC,
            display_name="Claude 3.5 Sonnet",
            capabilities=["text_generation", "long_context", "analysis"],
            tier=ModelTier.PREMIUM,
            quality_score=9.3,
            speed_score=8.0,
            cost_per_1k_tokens=0.05,  # $3/1M input + $15/1M output ≈ ¥0.07
            max_tokens=8192,
            best_for=[TaskType.COPYWRITE, TaskType.ANALYZE],
            config={"max_context": 200000},
        ))
        
        # === 阿里通义系列 ===
        self.register(ModelConfig(
            model_id="qwen-turbo",
            provider=ModelProvider.ALIBABA,
            display_name="Qwen Turbo (通义千问)",
            capabilities=["text_generation", "chat", "chinese"],
            tier=ModelTier.BUDGET,
            quality_score=7.5,
            speed_score=9.5,
            cost_per_1k_tokens=0.0004,  # ¥0.0004/1k tokens (超便宜!)
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
        
        # === 图片理解模型 ===
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
        
        # === 图片生成模型 ===
        self.register(ModelConfig(
            model_id="wanx-v1",
            provider=ModelProvider.ALIBABA,
            display_name="通义万相 V1",
            capabilities=["image_generation"],
            tier=ModelTier.STANDARD,
            quality_score=8.0,
            speed_score=7.0,
            cost_per_image=0.02,  # 约¥0.02/张
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
            avoid_for=[TaskType.IMAGE_GEN],  # 质量不够时避免使用
            config={"requires_proxy": True},  # 国内可能需要代理
        ))
    
    def register(self, model_config: ModelConfig):
        """注册新模型"""
        self._models[model_config.model_id] = model_config
        logger.info("[ModelRouter] Registered model: %s (%s)", 
                   model_config.model_id, model_config.display_name)

    def resolve_llm(
        self,
        model: str | None = None,
        temperature: float | None = None,
    ) -> Any | None:
        """解析具体 LLM adapter（BaseLLM），不做 task_type 自动路由。

        当前只支持 DeepSeek provider。未配置 api_key 时返回 None（保留降级行为）。
        返回的是具体 adapter（如 DeepSeekAdapter），不是 ModelRouter 自身。
        """
        from app.config import get_settings
        from app.agents.adapters.deepseek import DeepSeekAdapter

        s = get_settings()
        if not s.deepseek_api_key:
            logger.warning("[ModelRouter] resolve_llm: deepseek_api_key 未配置")
            return None

        model_name = model or s.deepseek_model_v3
        temp_val = 0.7 if temperature is None else float(max(0.0, min(1.0, temperature)))

        try:
            adapter = DeepSeekAdapter(
                api_key=s.deepseek_api_key,
                base_url=s.deepseek_base_url,
                model=model_name,
                temperature=temp_val,
            )
            self._adapters[ModelProvider.DEEPSEEK] = adapter
            return adapter
        except Exception as e:
            logger.warning(f"[ModelRouter] resolve_llm failed: {e}")
            return None
    
    async def route(self, request: ChatRequest) -> ChatResponse:
        """
        执行聊天请求（自动路由到最优模型）
        
        这是主要入口点，会自动：
        1. 选择最合适的模型（或使用用户指定的模型）
        2. 调用对应的适配器执行
        3. 处理错误和降级
        4. 记录统计信息
        
        Args:
            request: 聊天请求对象
            
        Returns:
            ChatResponse 响应对象
        """
        start_time = time.time()
        self._stats["total_calls"] += 1
        
        try:
            # Step 1: 选择模型
            selected_model = self._select_model(request)
            
            if not selected_model:
                return ChatResponse.fail("No suitable model available")
            
            logger.info(
                "[ModelRouter] Selected model: %s (tier=%s, reason=%s)",
                selected_model.model_id,
                selected_model.tier.value,
                getattr(request, '_routing_reason', 'user_specified')
            )
            
            # Step 2: 获取适配器并执行
            adapter = self._get_adapter(selected_model.provider)
            
            response_content, tokens_used, finish_reason = await adapter.chat(
                messages=request.messages,
                model=selected_model.model_id,
                temperature=request.temperature,
                max_tokens=request.max_tokens or selected_model.max_tokens,
                response_format=request.response_format,
                config=selected_model.config,
            )
            
            # Step 3: 计算成本和延迟
            latency_ms = int((time.time() - start_time) * 1000)
            cost = selected_model.estimated_cost(input_tokens=len(str(request.messages)), 
                                                output_tokens=tokens_used)
            
            # Step 4: 更新统计
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
            
            # 尝试降级
            if request.allow_fallback:
                return await self._try_fallback(request, original_error=str(e))
            
            return ChatResponse.fail(f"All models failed: {e}")

    @property
    def model_name(self) -> str:
        """路由自身没有单一模型名，返回哨兵值。

        LLMProtocol 要求 model_name 属性；真正用到的模型名在 ChatResponse.model_used 中体现。
        """
        return "model-router"

    async def chat(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """LLMProtocol 兼容入口：把标准 messages 转成 ChatRequest 并路由。

        返回协议要求的 {"content", "reasoning_content", "token_usage"}。
        """
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
    ) -> AsyncGenerator[dict[str, Any], None]:
        """LLMProtocol 兼容的流式入口。

        当前 router 内部没有真正的逐 token 流式，先退化为一次性返回整段内容。
        """
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
        """
        对话式聊天（支持动态模型切换）
        
        当 allow_user_switch=True 时，如果检测到当前模型可能不是最优选择，
        会 yield 一个 ModelSwitchEvent，让前端展示模型选择界面。
        
        Usage:
            async for event in router.chat_interactive(
                request=ChatRequest(messages=[...]),
                allow_user_switch=True,
            ):
                if isinstance(event, ModelSwitchEvent):
                    # 显示模型选择UI
                    user_choice = await show_model_picker(event.suggested_models)
                    await router.switch_model(user_choice)
                    
                elif isinstance(event, ChatResponse):
                    print("最终结果:", event.content)
        """
        # 初始模型选择
        initial_model = self._select_model(request)
        
        current_model = initial_model
        switched = False
        
        while True:
            try:
                # 检查是否需要建议切换（基于实时反馈）
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
                        
                        # 等待用户响应（通过回调或外部设置）
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
                            # 无回调，继续使用当前模型
                            yield ModelSwitchEvent(
                                event_type="switch_rejected",
                                current_model=current_model.model_id,
                            )
                
                # 执行实际调用
                response = await self.route(ChatRequest(
                    **request.__dict__,
                    preferred_model=current_model.model_id,
                    allow_fallback=False,  # 交互模式下不自动降级
                ))
                
                yield response
                break  # 成功完成
                
            except Exception as e:
                # 出错时尝试降级（但只在非交互模式下）
                if not allow_user_switch:
                    fallback_resp = await self._try_fallback(request, str(e))
                    yield fallback_resp
                    break
                else:
                    raise  # 交互模式下抛出异常让外部处理
    
    def _select_model(self, request: ChatRequest) -> Optional[ModelConfig]:
        """
        智能模型选择算法
        
        选择逻辑：
        1. 如果用户明确指定 → 使用指定的（如果可用）
        2. 如果有预算限制 → 在预算内选质量最高的
        3. 如果要求高质量 → 选PREMIUM层级的
        4. 如果要求快速 → 选速度分最高的
        5. 默认 → 基于任务类型匹配最佳模型
        """
        
        # 1. 用户明确指定
        if request.preferred_model and request.preferred_model in self._models:
            model = self._models[request.preferred_model]
            if model.is_available:
                request._routing_reason = "user_specified"
                return model
            else:
                logger.warning("[ModelRouter] User requested model %s is unavailable", 
                              request.preferred_model)
        
        # 过滤可用模型
        available_models = [m for m in self._models.values() if m.is_available]
        
        if not available_models:
            logger.error("[ModelRouter] No models available")
            return None
        
        # 2. 预算过滤
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
        
        # 3. 任务类型匹配得分
        scored_models = []
        for model in available_models:
            score = 0
            
            # 任务匹配加分
            if request.task_type in model.best_for:
                score += 20
            if request.task_type in model.avoid_for:
                score -= 30
            
            # 约束满足
            if request.require_high_quality and model.tier == ModelTier.PREMIUM:
                score += 15
            elif request.require_high_quality and model.tier == ModelTier.BUDGET:
                score -= 10
                
            if request.require_fast_response and model.speed_score >= 8.5:
                score += 10
            
            # 基础质量分
            score += model.quality_score * 2
            
            # 成本惩罚（预算紧张时）
            if request.budget:
                cost_ratio = model.estimated_cost() / request.budget
                if cost_ratio > 0.8:
                    score -= 5  # 接近预算上限扣分
            
            scored_models.append((score, model))
        
        # 排序选最佳
        scored_models.sort(key=lambda x: x[0], reverse=True)
        
        best_model = scored_models[0][1]
        request._routing_reason = f"auto_selected_{best_model.tier.value}"
        
        return best_model
    
    def _should_suggest_switch(
        self, 
        current_model: ModelConfig, 
        request: ChatRequest
    ) -> Optional[List[Dict[str, Any]]]:
        """
        判断是否应该建议用户切换模型
        
        触发条件：
        1. 当前是BUDGET层级但有PREMIUM可选
        2. 当前模型不在该任务的best_for列表中
        3. 有明显更优的选择（质量提升>1.5且成本增加<50%）
        """
        suggestions = []
        
        for model in self._models.values():
            if not model.is_available or model.model_id == current_model.model_id:
                continue
            
            should_suggest = False
            reasons = []
            
            # 条件1: 明显更高质量
            if (model.quality_score > current_model.quality_score + 1.5 and
                model.estimated_cost() < current_model.estimated_cost() * 1.5):
                should_suggest = True
                reasons.append(f"质量更高 ({model.quality_score} vs {current_model.quality_score})")
            
            # 条件2: 更适合当前任务
            if (request.task_type in model.best_for and 
                request.task_type not in current_model.best_for):
                should_suggest = True
                reasons.append(f"更适合{request.task_type.value}任务")
            
            # 条件3: 更快且质量相当
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
        
        return suggestions[:3] if suggestions else None  # 最多建议3个
    
    async def _try_fallback(
        self, 
        request: ChatRequest, 
        original_error: str
    ) -> ChatResponse:
        """尝试使用备用模型"""
        self._stats["fallback_count"] += 1
        
        logger.warning(
            "[ModelRouter] Primary model failed, trying fallback. Error: %s",
            original_error
        )
        
        # 按优先级尝试备用模型
        fallback_order = [
            ModelTier.STANDARD,
            ModelTier.BUDGET,
            ModelTier.PREMIUM,  # 最后尝试其他高端模型
        ]
        
        for tier in fallback_order:
            fallback_request = ChatRequest(
                **request.__dict__,
                preferred_model=None,  # 清除偏好让路由器重新选择
                allow_fallback=False,  # 防止无限递归
            )
            
            # 强制选择特定层级
            fallback_candidates = [
                m for m in self._models.values() 
                if m.tier == tier and m.is_available and m.model_id != request.preferred_model
            ]
            
            if fallback_candidates:
                # 选一个同类型的
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
        
        # 所有模型都失败
        return ChatResponse.fail(f"All models exhausted. Original: {original_error}")
    
    def _get_adapter(self, provider: ModelProvider):
        """获取或创建模型适配器"""
        if provider in self._adapters:
            return self._adapters[provider]
        
        # 延迟加载适配器
        adapter = None
        
        if provider == ModelProvider.DEEPSEEK:
            adapter = self.resolve_llm()
            
        elif provider == ModelProvider.OPENAI:
            from langchain_openai import ChatOpenAI
            adapter = ChatOpenAI  # 包装器
            
        elif provider == ModelProvider.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic
            adapter = ChatAnthropic
            
        elif provider == ModelProvider.ALIBABA:
            if "vl" in str(self._models):  # 简单判断是否VL模型
                from app.agents.adapters.qwen_vl import QwenVLAdapter
                adapter = QwenVLAdapter
            else:
                from langchain_community.chat_models import ChatTongyi
                adapter = ChatTongyi
        
        elif provider == ModelProvider.POLLINATIONS:
            from app.agents.adapters.image_gen import PollinationsAdapter
            adapter = PollinationsAdapter
        
        if adapter:
            self._adapters[provider] = adapter
            logger.info("[ModelRouter] Loaded adapter for %s", provider.value)
        
        return adapter
    
    def _update_stats(self, model_id: str, tokens: int, cost: float):
        """更新统计信息"""
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
        """获取统计信息"""
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
        """
        列出符合条件的模型
        
        Args:
            tier: 层级过滤
            provider: 提供商过滤
            capability: 能力过滤 (如 "vision", "code")
            
        Returns:
            模型列表（字典格式，隐藏敏感信息）
        """
        models = []
        
        for model in self._models.values():
            # 应用过滤器
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


# ===== 全局单例 =====
_router_instance: Optional[ModelRouter] = None

def get_model_router() -> ModelRouter:
    """获取全局 ModelRouter 单例"""
    global _router_instance
    if _router_instance is None:
        _router_instance = ModelRouter()
    return _router_instance


# ===== 测试入口 =====

if __name__ == "__main__":
    async def test():
        print("=" * 70)
        print("🤖 Model Router Test Suite")
        print("=" * 70)
        
        router = ModelRouter()
        
        # Test 1: 列出所有模型
        print("\n📋 Test 1: List all registered models")
        all_models = router.list_models()
        print(f"   Total: {len(all_models)} models")
        for m in all_models[:5]:  # 只显示前5个
            print(f"   - [{m['tier']}] {m['display_name']} ({m['model_id']})")
        
        # Test 2: 智能路由测试
        print("\n🧭 Test 2: Smart routing")
        test_cases = [
            ("文案生成", TaskType.COPYWRITE),
            ("内容分析", TaskType.ANALYZE),
            ("代码生成", TaskType.CODE),
            ("快速摘要", TaskType.SUMMARIZE),
        ]
        
        for name, task_type in test_cases:
            request = ChatRequest(
                messages=[{"role": "user", "content": f"{name}测试"}],
                task_type=task_type,
            )
            
            selected = router._select_model(request)
            print(f"   {name}: → {selected.display_name} ({selected.tier.value}) "
                  f"[reason: {getattr(request, '_routing_reason', '?')}]")
        
        # Test 3: 预算约束测试
        print("\n💰 Test 3: Budget constraint")
        cheap_request = ChatRequest(
            messages=[{"role": "user", "content": "test"}],
            budget=0.002,  # 只有2厘钱预算
        )
        cheap_model = router._select_model(cheap_request)
        print(f"   Budget ¥0.002 → {cheap_model.display_name} "
              f"(est. cost: ¥{cheap_model.estimated_cost():.4f})")
        
        # Test 4: 模型切换建议
        print("\n🔄 Test 4: Switch suggestion")
        budget_model = router._models.get("qwen-turbo")
        if budget_model:
            suggestions = router._should_suggest_switch(budget_model, ChatRequest(
                messages=[{"role": "user", "content": "test"}],
                task_type=TaskType.COPYWRITE,
            ))
            
            if suggestions:
                print(f"   Current: {budget_model.display_name}")
                print(f"   Suggestions:")
                for s in suggestions:
                    print(f"      → {s['display_name']}: {', '.join(s['reasons'])}")
            else:
                print("   No better alternatives found")
        
        # Test 5: 统计信息
        print("\n📊 Test 5: Statistics (before any calls)")
        stats = router.get_stats()
        print(f"   Registered: {stats['total_registered']} models")
        print(f"   Available: {stats['available_models']} models")
        
        print("\n" + "=" * 70)
        print("✅ All tests completed!")
    
    asyncio.run(test())
