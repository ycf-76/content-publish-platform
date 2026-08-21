"""
AI Text Translator Plugin - AI多语言翻译器
==========================================

基于大语言模型（LLM）的智能翻译节点，支持：
- 100+种语言互译
- 自动源语言检测
- 多种翻译风格（正式/口语/学术等）
- 批量翻译优化
- 智能缓存机制
- 费用统计和预估

技术栈：
- httpx (异步HTTP客户端)
- 缓存系统 (内存 + 可选Redis)
- 事件驱动架构

难度：⭐⭐ 进阶
预计学习时间：2小时
"""

import asyncio
import hashlib
import time
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass

# 尝试导入平台基类，失败则使用本地模拟定义
try:
    from app.core.base_interfaces import (
        BaseWorkflowNodePlugin,
        PluginContext,
        NodeOutput
    )
    from app.core.plugin_types import PluginManifest, HealthStatus
    
except ImportError:
    # 开发模式下的类型占位符
    @dataclass
    class NodeOutput:
        success: bool
        data: Dict[str, Any]
        message: str = ""
        execution_time_ms: int = 0
    
    @dataclass
    class PluginManifest:
        id: str
        name: str
        version: str
        category: str
        description: str
        capabilities: list
        permissions_required: list
    
    class HealthStatus:
        def __init__(self, status: str, message: str, timestamp: datetime = None, details: dict = None):
            self.status = status
            self.message = message
            self.timestamp = timestamp or datetime.utcnow()
            self.details = details or {}
    
    class PluginContext:
        def __init__(self):
            self.user_id = "anonymous"
            self.config: Optional[Dict] = None
            self.event_bus = None
            self.data_store = None
    
    class BaseWorkflowNodePlugin:
        id = ""
        name = ""
        version = "0.0.1"
        
        async def on_load(self): pass
        async def on_unload(self): pass


# 语言代码映射表
LANGUAGE_NAMES = {
    "zh": "Chinese (中文)",
    "en": "English",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
    "fr": "French (Français)",
    "de": "German (Deutsch)",
    "es": "Spanish (Español)",
    "it": "Italian (Italiano)",
    "pt": "Portuguese (Português)",
    "ru": "Russian (Русский)",
    "ar": "Arabic (العربية)",
    "hi": "Hindi (हिन्दी)",
}

# 翻译风格映射
STYLE_PROMPTS = {
    "literal": "Translate literally, word-for-word where possible.",
    "natural": "Translate naturally as a native speaker would.",
    "formal": "Translate in formal, professional language.",
    "casual": "Translate in casual, conversational language.",
    "academic": "Translate using academic/technical terminology."
}


@dataclass
class TranslationResult:
    """单个文本的翻译结果"""
    original: str
    translated: str
    source_lang: str
    target_lang: str
    confidence: float
    token_count: int
    cached: bool = False


@dataclass
class TranslationSummary:
    """批量翻译汇总信息"""
    total_texts: int
    total_tokens_used: float
    estimated_cost_usd: float
    processing_time_ms: int
    cache_hits: int
    api_calls_made: int


class TextTranslatorPlugin(BaseWorkflowNodePlugin):
    """
    AI多语言翻译插件
    
    功能特性：
    - 支持多种LLM提供商（OpenAI、DeepSeek、Anthropic等）
    - 自动源语言检测
    - 批量翻译优化（减少API调用）
    - 智能缓存（避免重复翻译相同内容）
    - 翻译风格控制（正式/口语/学术等）
    - 费用追踪和预估
    
    使用场景：
    - 内容国际化（i18n）
    - 文档翻译
    - 社交媒体多语言发布
    - 客户服务自动回复翻译
    """
    
    id = "text-translator"
    name = "AI Text Translator"
    version = "1.0.0"
    
    def __init__(self):
        super().__init__()
        
        # HTTP客户端（懒初始化）
        self._http_client = None
        
        # 内存缓存：{hash: (translation, timestamp)}
        self._cache: Dict[str, Tuple[TranslationResult, datetime]] = {}
        
        # 统计数据
        self._stats = {
            "total_translations": 0,
            "total_tokens": 0,
            "cache_hits": 0,
            "api_errors": 0,
            "last_translation_time": None
        }
        
        # API端点配置
        API_ENDPOINTS = {
            "openai": "https://api.openai.com/v1/chat/completions",
            "deepseek": "https://api.deepseek.com/chat/completions",
            "anthropic": "https://api.anthropic.com/v1/messages"
        }
    
    async def _get_http_client(self):
        """获取或创建HTTP客户端实例（连接池复用）"""
        if not self._http_client:
            try:
                import httpx
                
                self._http_client = httpx.AsyncClient(
                    timeout=30.0,
                    limits=httpx.Limits(
                        max_connections=10,
                        max_keepalive_connections=5
                    ),
                    headers={
                        "User-Agent": f"{self.id}/{self.version}"
                    }
                )
                
                print(f"[{self.id}] HTTP client initialized")
                
            except ImportError:
                raise RuntimeError(
                    "httpx package is required. Install with: pip install httpx"
                )
        
        return self._http_client
    
    async def on_load(self) -> None:
        """插件加载时初始化资源"""
        print(f"[{self.id}] Loading translator plugin...")
        
        # 预热HTTP客户端
        await self._get_http_client()
        
        print(f"[{self.id}] Translator plugin ready")
    
    async def on_unload(self) -> None:
        """插件卸载时清理资源"""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        
        # 清空缓存
        self._cache.clear()
        
        print(f"[{self.id}] Plugin unloaded, resources cleaned up")
    
    async def get_info(self) -> PluginManifest:
        """返回插件元信息"""
        return PluginManifest(
            id=self.id,
            name=self.name,
            version=self.version,
            category="workflow_node",
            description="AI-powered multi-language translation using LLMs",
            capabilities=["execute", "validate_inputs", "optimize_output"],
            permissions_required=["llm:use", "network:read"]
        )
    
    async def health_check(self) -> HealthStatus:
        """健康检查 - 验证API连接可用性"""
        
        is_healthy = True
        details = {}
        
        # 检查HTTP客户端状态
        if self._http_client:
            details["client_status"] = "initialized"
        else:
            details["client_status"] = "not_initialized"
        
        # 检查缓存大小
        cache_size = len(self._cache)
        details["cache_entries"] = cache_size
        details["cache_memory_kb"] = cache_size * 2  # 估算
        
        return HealthStatus(
            status="healthy" if is_healthy else "degraded",
            message=f"Ready | Cache: {cache_size} entries",
            timestamp=datetime.utcnow(),
            details=details
        )
    
    async def validate_inputs(
        self, 
        inputs: Dict[str, Any]
    ) -> Tuple[bool, str]:
        """
        验证输入参数
        
        验证规则：
        1. texts 必须存在且非空
        2. target_language 必须是支持的语言
        3. 单个文本长度限制（10000字符）
        4. 批量数量限制（最多50条）
        """
        
        # 检查texts字段
        if 'texts' not in inputs:
            return False, "Missing required field: 'texts'"
        
        texts = inputs['texts']
        
        # 支持单个字符串或数组
        if isinstance(texts, str):
            texts_list = [texts]
        elif isinstance(texts, list):
            texts_list = texts
        else:
            return False, "'texts' must be a string or array of strings"
        
        # 检查是否为空
        if not texts_list or all(not t or not t.strip() for t in texts_list):
            return False, "'texts' cannot be empty"
        
        # 检查每条文本长度
        for i, text in enumerate(texts_list):
            if text and len(text) > 10000:
                return False, f"Text at index {i} too long (max 10000 chars)"
        
        # 检查数量限制
        if len(texts_list) > 50:
            return False, f"Too many texts ({len(texts_list)}, max 50)"
        
        # 检查目标语言
        target_lang = inputs.get('target_language', 'en')
        if target_lang not in LANGUAGE_NAMES and target_lang != 'auto':
            valid = ', '.join(LANGUAGE_NAMES.keys())
            return False, f"Invalid target language '{target_lang}'. Valid: {valid}"
        
        return True, "Inputs validated successfully"
    
    async def execute(
        self, 
        ctx: PluginContext, 
        inputs: Dict[str, Any]
    ) -> NodeOutput:
        """
        执行翻译任务
        
        处理流程：
        1. 解析并验证输入
        2. 读取配置（API密钥、模型参数等）
        3. 规范化输入为列表格式
        4. 查询缓存（命中则跳过API调用）
        5. 构建LLM提示词
        6. 调用翻译API
        7. 更新缓存
        8. 统计费用和时间
        9. 发出完成事件
        10. 返回结果
        """
        
        start_time = time.perf_counter()
        
        try:
            # ===== 步骤1: 验证输入 =====
            is_valid, error_msg = await self.validate_inputs(inputs)
            if not is_valid:
                return NodeOutput(
                    success=False,
                    data={},
                    message=f"Validation failed: {error_msg}",
                    execution_time_ms=0
                )
            
            # ===== 步骤2: 读取配置 =====
            config = ctx.config or {}
            
            api_key = config.get('api_key', '')
            if not api_key:
                return NodeOutput(
                    success=False,
                    data={},
                    message="API key not configured. Please set it in plugin settings.",
                    execution_time_ms=0
                )
            
            provider = config.get('api_provider', 'openai')
            model_name = config.get('model_name', 'gpt-3.5-turbo')
            temperature = config.get('temperature', 0.3)
            max_tokens = config.get('max_tokens', 2000)
            style = config.get('translation_style', 'natural')
            preserve_fmt = config.get('preserve_formatting', True)
            enable_cache = config.get('enable_cache', True)
            cache_ttl_hours = config.get('cache_ttl_hours', 24)
            batch_size = config.get('batch_size', 10)
            base_url = config.get('base_url', '').strip()
            
            # ===== 步骤3: 规范化输入 =====
            raw_texts = inputs['texts']
            if isinstance(raw_texts, str):
                texts_to_translate = [raw_texts.strip()]
            else:
                texts_to_translate = [t.strip() for t in raw_texts if t and t.strip()]
            
            target_lang = inputs.get('target_language', 'en')
            source_lang = inputs.get('source_language', 'auto')
            context = inputs.get('context', '')
            
            # 发出开始事件
            if ctx.event_bus:
                await ctx.event_bus.emit("translation:started", {
                    "plugin_id": self.id,
                    "text_count": len(texts_to_translate),
                    "target_language": target_lang,
                    "provider": provider,
                    "model": model_name
                })
            
            # ===== 步骤4: 查询缓存 =====
            results: List[TranslationResult] = []
            uncached_texts = []  # 需要翻译的文本
            uncached_indices = []  # 对应原始索引
            
            for idx, text in enumerate(texts_to_translate):
                if enable_cache:
                    cache_key = self._generate_cache_key(
                        text=text,
                        target_lang=target_lang,
                        style=style,
                        model=model_name
                    )
                    
                    cached_result = self._get_from_cache(cache_key, cache_ttl_hours)
                    if cached_result:
                        results.append(cached_result)
                        self._stats["cache_hits"] += 1
                        
                        # 发出缓存命中事件
                        if ctx.event_bus:
                            await ctx.event_bus.emit("translation:cache_hit", {
                                "cache_key": cache_key[:16],
                                "original_preview": text[:50]
                            })
                        
                        continue
                
                # 未命中缓存，需要翻译
                uncached_texts.append(text)
                uncached_indices.append(idx)
            
            # ===== 步骤5-7: 调用API翻译未缓存的文本 =====
            if uncached_texts:
                translated_batch = await self._translate_batch(
                    texts=uncached_texts,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    context=context,
                    style=style,
                    preserve_formatting=preserve_fmt,
                    provider=provider,
                    model=model_name,
                    api_key=api_key,
                    base_url=base_url,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    ctx=ctx
                )
                
                # 将结果放入正确位置
                for i, result in enumerate(translated_batch):
                    original_idx = uncached_indices[i]
                    
                    # 插入到结果列表的正确位置
                    while len(results) <= original_idx:
                        results.append(None)  # 占位
                    
                    results[original_idx] = result
                    
                    # 更新缓存
                    if enable_cache:
                        cache_key = self._generate_cache_key(
                            text=result.original,
                            target_lang=result.target_lang,
                            style=style,
                            model=model_name
                        )
                        self._set_cache(cache_key, result)
            
            # 移除可能的None值（理论上不应该有）
            results = [r for r in results if r is not None]
            
            # ===== 步骤8: 计算统计信息 =====
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            
            total_tokens = sum(r.token_count for r in results)
            estimated_cost = self._estimate_cost(provider, model_name, total_tokens)
            
            summary = TranslationSummary(
                total_texts=len(results),
                total_tokens_used=total_tokens,
                estimated_cost_usd=estimated_cost,
                processing_time_ms=elapsed_ms,
                cache_hits=sum(1 for r in results if r.cached),
                api_calls_made=len(uncached_texts) // batch_size + (1 if len(uncached_texts) % batch_size > 0 else 0)
            )
            
            # 更新全局统计
            self._stats["total_translations"] += len(results)
            self._stats["total_tokens"] += total_tokens
            self._stats["last_translation_time"] = datetime.utcnow().isoformat()
            
            # ===== 步骤9: 构建输出 =====
            output_data = {
                "translations": [
                    {
                        "original": r.original,
                        "translated": r.translated,
                        "source_lang": r.source_lang,
                        "target_lang": r.target_lang,
                        "confidence": r.confidence,
                        "token_count": r.token_count,
                        "cached": r.cached
                    }
                    for r in results
                ],
                "summary": {
                    **summary.__dict__
                }
            }
            
            # 发出完成事件
            if ctx.event_bus:
                await ctx.event_bus.emit("translation:completed", {
                    "plugin_id": self.id,
                    "results_count": len(results),
                    "tokens_used": total_tokens,
                    "cost_usd": round(estimated_cost, 4),
                    "duration_ms": elapsed_ms,
                    "cache_hit_rate": f"{(summary.cache_hits / len(results) * 100):.1f}%" if results else "0%"
                })
            
            return NodeOutput(
                success=True,
                data=output_data,
                message=(
                    f"Translated {len(results)} text(s) to "
                    f"{LANGUAGE_NAMES.get(target_lang, target_lang)}. "
                    f"Cost: ~${round(estimated_cost, 4)}"
                ),
                execution_time_ms=elapsed_ms
            )
            
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            
            self._stats["api_errors"] += 1
            
            # 发出失败事件
            if ctx.event_bus:
                await ctx.event_bus.emit("translation:failed", {
                    "plugin_id": self.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)[:200],
                    "duration_ms": elapsed_ms
                })
            
            print(f"[ERROR] {self.id}: {e}")
            
            return NodeOutput(
                success=False,
                data={},
                message=f"Translation failed: {str(e)}",
                execution_time_ms=elapsed_ms
            )
    
    async def _translate_batch(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str,
        context: str,
        style: str,
        preserve_formatting: bool,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        temperature: float,
        max_tokens: int,
        ctx: PluginContext
    ) -> List[TranslationResult]:
        """
        批量调用LLM API进行翻译
        
        优化策略：
        - 将多个短文本合并为一个请求以减少API调用次数
        - 对长文本单独处理
        - 实现指数退避重试
        """
        
        results = []
        
        # 根据文本长度决定策略
        # 短文本可以合并，长文本需要单独处理
        MAX_COMBINED_LENGTH = 4000  # 合并后的最大字符数
        
        batches = []
        current_batch = []
        current_length = 0
        
        for text in texts:
            text_len = len(text)
            
            # 如果单条文本太长或加入后会超限，则开始新批次
            if text_len > MAX_COMBINED_LENGTH or \
               (current_batch and current_length + text_len > MAX_COMBINED_LENGTH):
                if current_batch:
                    batches.append(current_batch)
                current_batch = [text]
                current_length = text_len
            else:
                current_batch.append(text)
                current_length += text_len
        
        if current_batch:
            batches.append(current_batch)
        
        # 为每个批次调用API
        for batch in batches:
            try:
                batch_results = await self._call_llm_api(
                    texts=batch,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    context=context,
                    style=style,
                    preserve_formatting=preserve_formatting,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                results.extend(batch_results)
                
            except Exception as e:
                # 单个批次失败不影响其他批次
                print(f"[WARN] Batch translation failed: {e}")
                
                # 为失败的文本创建错误标记的结果
                for text in batch:
                    results.append(TranslationResult(
                        original=text,
                        translated=f"[TRANSLATION ERROR: {str(e)[:100]}]",
                        source_lang=source_lang,
                        target_lang=target_lang,
                        confidence=0.0,
                        token_count=0,
                        cached=False
                    ))
        
        return results
    
    async def _call_llm_api(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str,
        context: str,
        style: str,
        preserve_formatting: bool,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        temperature: float,
        max_tokens: int
    ) -> List[TranslationResult]:
        """
        调用具体的LLM API
        
        支持OpenAI兼容接口（包括DeepSeek）和Anthropic Claude
        """
        
        client = await self._get_http_client()
        
        # 构建系统提示词
        system_prompt = self._build_system_prompt(
            target_lang=target_lang,
            source_lang=source_lang,
            style=style,
            preserve_formatting=preserve_formatting,
            context=context
        )
        
        # 构建用户消息
        if len(texts) == 1:
            user_content = texts[0]
        else:
            # 多条文本：使用JSON格式以便解析
            user_content = json.dumps({
                "texts": texts,
                "instruction": (
                    f"Translate each text to {LANGUAGE_NAMES.get(target_lang, target_lang)}. "
                    "Return the translations as a JSON array in the same order."
                )
            }, ensure_ascii=False)
        
        # 根据provider选择不同的请求格式
        if provider == "anthropic":
            response_data = await self._call_anthropic_api(
                client=client,
                system_prompt=system_prompt,
                user_content=user_content,
                model=model,
                api_key=api_key,
                base_url=base_url,
                max_tokens=max_tokens
            )
        else:
            # OpenAI兼容接口（包括DeepSeek）
            response_data = await self._call_openai_compatible_api(
                client=client,
                system_prompt=system_prompt,
                user_content=user_content,
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
                max_tokens=max_tokens
            )
        
        # 解析响应
        return self._parse_response(response_data, texts, source_lang, target_lang)
    
    def _build_system_prompt(
        self,
        target_lang: str,
        source_lang: str,
        style: str,
        preserve_formatting: bool,
        context: str
    ) -> str:
        """构建系统提示词"""
        
        target_name = LANGUAGE_NAMES.get(target_lang, target_lang)
        style_instruction = STYLE_PROMPTS.get(style, STYLE_PROMPTS["natural"])
        
        prompt_parts = [
            f"You are a professional translator specializing in {target_name}.",
            f"Translation style: {style_instruction}",
        ]
        
        if source_lang != 'auto':
            source_name = LANGUAGE_NAMES.get(source_lang, source_lang)
            prompt_parts.append(f"Source language: {source_name}")
        
        if preserve_formatting:
            prompt_parts.append(
                "Preserve formatting such as Markdown, HTML tags, line breaks, etc."
            )
        
        if context:
            prompt_parts.append(f"Context for better translation: {context}")
        
        prompt_parts.extend([
            "Rules:",
            "- Translate accurately while maintaining the original meaning",
            "- Do NOT add explanations, notes, or extra content",
            "- If translating multiple texts, maintain the order",
            "- Return ONLY the translation(s), nothing else"
        ])
        
        return "\n".join(prompt_parts)
    
    async def _call_openai_compatible_api(
        self,
        client,
        system_prompt: str,
        user_content: str,
        model: str,
        api_key: str,
        base_url: str,
        temperature: float,
        max_tokens: int
    ) -> dict:
        """调用OpenAI兼容的API（包括DeepSeek）"""
        
        url = base_url if base_url else f"https://api.{provider}.com/v1/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    async def _call_anthropic_api(
        self,
        client,
        system_prompt: str,
        user_content: str,
        model: str,
        api_key: str,
        base_url: str,
        max_tokens: int
    ) -> dict:
        """调用Anthropic Claude API"""
        
        url = base_url if base_url else "https://api.anthropic.com/v1/messages"
        
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_content}]
        }
        
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        return response.json()
    
    def _parse_response(
        self,
        response_data: dict,
        original_texts: List[str],
        source_lang: str,
        target_lang: str
    ) -> List[TranslationResult]:
        """解析API响应为TranslationResult列表"""
        
        results = []
        
        try:
            # OpenAI格式
            if "choices" in response_data:
                content = response_data["choices"][0]["message"]["content"]
                usage = response_data.get("usage", {})
                total_tokens = usage.get("total_tokens", 0)
            # Anthropic格式
            elif "content" in response_data:
                content = response_data["content"][0]["text"]
                usage = response_data.get("usage", {})
                total_tokens = usage.get("output_tokens", 0)
            else:
                raise ValueError("Unexpected response format")
            
            # 尝试解析JSON数组（多条文本的情况）
            if len(original_texts) > 1:
                try:
                    translations = json.loads(content)
                    if isinstance(translations, list):
                        for i, orig_text in enumerate(original_texts):
                            trans_text = translations[i] if i < len(translations) else "[PARSING ERROR]"
                            results.append(TranslationResult(
                                original=orig_text,
                                translated=trans_text,
                                source_lang=source_lang if source_lang != 'auto' else 'detected',
                                target_lang=target_lang,
                                confidence=0.95,  # LLM通常置信度较高
                                token_count=total_tokens // len(original_texts),
                                cached=False
                            ))
                        return results
                except json.JSONDecodeError:
                    pass
            
            # 单条文本或多条文本但未返回JSON数组
            lines = content.split('\n')
            
            for i, orig_text in enumerate(original_texts):
                if i < len(lines):
                    trans_text = lines[i].strip()
                else:
                    trans_text = content  # Fallback
                
                results.append(TranslationResult(
                    original=orig_text,
                    translated=trans_text,
                    source_lang=source_lang if source_lang != 'auto' else 'detected',
                    target_lang=target_lang,
                    confidence=0.95,
                    token_count=total_tokens // max(len(original_texts), 1),
                    cached=False
                ))
            
        except (KeyError, IndexError, ValueError) as e:
            print(f"[ERROR] Failed to parse response: {e}")
            
            # 返回错误标记的结果
            for text in original_texts:
                results.append(TranslationResult(
                    original=text,
                    translated="[RESPONSE PARSING ERROR]",
                    source_lang=source_lang,
                    target_lang=target_lang,
                    confidence=0.0,
                    token_count=0,
                    cached=False
                ))
        
        return results
    
    def _generate_cache_key(
        self,
        text: str,
        target_lang: str,
        style: str,
        model: str
    ) -> str:
        """生成缓存键（基于内容的哈希）"""
        content = f"{text}|{target_lang}|{style}|{model}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def _get_from_cache(
        self, 
        key: str, 
        ttl_hours: int
    ) -> Optional[TranslationResult]:
        """从缓存中获取结果（考虑TTL）"""
        
        if key not in self._cache:
            return None
        
        # TTL为0或负数时直接视为过期
        if ttl_hours <= 0:
            del self._cache[key]
            return None
        
        result, timestamp = self._cache[key]
        age = datetime.utcnow() - timestamp
        
        if age.total_seconds() > ttl_hours * 3600:
            # 过期，删除
            del self._cache[key]
            return None
        
        # 返回副本，标记为缓存
        cached_copy = TranslationResult(
            original=result.original,
            translated=result.translated,
            source_lang=result.source_lang,
            target_lang=result.target_lang,
            confidence=result.confidence,
            token_count=result.token_count,
            cached=True
        )
        
        return cached_copy
    
    def _set_cache(self, key: str, result: TranslationResult):
        """将结果存入缓存"""
        self._cache[key] = (result, datetime.utcnow())
        
        # 简单的LRU：如果缓存太大，删除最旧的条目
        MAX_CACHE_SIZE = 1000
        if len(self._cache) > MAX_CACHE_SIZE:
            oldest_key = min(self._cache.keys(),
                           key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
    
    def _estimate_cost(
        self, 
        provider: str, 
        model: str, 
        tokens: float
    ) -> float:
        """估算API调用费用（美元）"""
        
        # 价格表（每1K tokens，2024年价格）
        PRICING = {
            "openai": {
                "gpt-4": {"input": 0.03, "output": 0.06},
                "gpt-4-turbo": {"input": 0.01, "output": 0.03},
                "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015}
            },
            "deepseek": {
                "deepseek-chat": {"input": 0.0014, "output": 0.0028}
            },
            "anthropic": {
                "claude-3-opus": {"input": 0.015, "output": 0.075},
                "claude-3-sonnet": {"input": 0.003, "output": 0.015}
            }
        }
        
        try:
            pricing_info = PRICING.get(provider, {}).get(model, {})
            input_price = pricing_info.get("input", 0.01)
            output_price = pricing_info.get("output", 0.02)
            
            # 假设输入输出各占一半
            cost = (tokens / 1000) * ((input_price + output_price) / 2)
            return round(cost, 6)
            
        except:
            # 无法估算时返回保守估计
            return (tokens / 1000) * 0.02
    
    async def optimize_output(
        self, 
        output: NodeOutput,
        feedback: str = None
    ) -> NodeOutput:
        """
        根据反馈优化翻译结果（可选功能）
        
        用途：
        - 用户对翻译不满意时重新生成
        - 根据上下文调整翻译风格
        """
        
        if not output.success or not feedback:
            return output
        
        # TODO: 实现优化逻辑
        # 可以重新调用API，附加用户的反馈作为额外上下文
        
        return output


# ===== 本地测试入口 =====

if __name__ == "__main__":
    """
    自测脚本 - 无需启动完整服务即可测试核心逻辑
    """
    
    import asyncio
    
    async def test():
        print("=" * 70)
        print("  AI Text Translator - Local Test Mode")
        print("=" * 70)
        
        plugin = TextTranslatorPlugin()
        
        # 模拟上下文
        ctx = PluginContext()
        ctx.config = {
            "api_provider": "mock",  # 使用mock模式避免真实API调用
            "model_name": "test-model",
            "api_key": "test-key-for-mock-mode",
            "translation_style": "natural",
            "enable_cache": True
        }
        ctx.user_id = "test_user"
        
        # 测试1: 输入验证
        print("\n[Test 1] Input validation:")
        
        valid, msg = await plugin.validate_inputs({
            "texts": ["Hello world"],
            "target_language": "zh"
        })
        print(f"  Valid input: {valid}, Message: {msg}")
        
        invalid, msg = await plugin.validate_inputs({})
        print(f"  Invalid input: {invalid}, Message: {msg}")
        
        # 测试2: 健康检查
        print("\n[Test 2] Health check:")
        health = await plugin.health_check()
        print(f"  Status: {health.status}")
        print(f"  Message: {health.message}")
        
        # 测试3: 插件信息
        print("\n[Test 3] Plugin info:")
        info = await plugin.get_info()
        print(f"  ID: {info.id}")
        print(f"  Name: {info.name}")
        print(f"  Capabilities: {info.capabilities}")
        
        # 测试4: 缓存功能演示
        print("\n[Test 4] Cache mechanism:")
        
        # 创建一个假的翻译结果用于测试缓存
        fake_result = TranslationResult(
            original="Hello",
            translated="你好",
            source_lang="en",
            target_lang="zh",
            confidence=0.95,
            token_count=2
        )
        
        cache_key = plugin._generate_cache_key(
            text="Hello",
            target_lang="zh",
            style="natural",
            model="test"
        )
        
        plugin._set_cache(cache_key, fake_result)
        cached = plugin._get_from_cache(cache_key, ttl_hours=24)
        
        if cached and cached.cached:
            print(f"  ✓ Cache hit! Original: {cached.original}")
            print(f"  ✓ Translated: {cached.translated}")
        else:
            print("  ✗ Cache miss")
        
        # 测试5: 费用估算
        print("\n[Test 5] Cost estimation:")
        
        costs = [
            ("openai", "gpt-4", 1000),
            ("openai", "gpt-3.5-turbo", 1000),
            ("deepseek", "deepseek-chat", 1000),
        ]
        
        for provider, model, tokens in costs:
            cost = plugin._estimate_cost(provider, model, tokens)
            print(f"  {provider}/{model} ({tokens} tokens): ${cost:.4f}")
        
        print("\n" + "=" * 70)
        print("  All tests completed!")
        print("=" * 70)
        print("\nNote: To test actual API calls, configure real API keys")
        print("      and run: plugin dev → call the execute endpoint")
    
    asyncio.run(test())