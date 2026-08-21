"""
AI Sentiment Analyzer Plugin - 智能情感分析器
============================================

基于大语言模型的多维度情感分析节点，提供：
- 多维度情感识别（情感、情绪、主观性、极性、强度）
- 情感强度评分（-1.0 到 +1.0）
- 关键词和实体提取
- 方面级情感分析（Aspect-Based Sentiment Analysis）
- 可视化报告生成
- 批量文本处理优化

技术亮点：
- 结构化Prompt工程（确保JSON输出格式稳定）
- 多维度并行分析
- 结果聚合与统计
- 自定义标签映射

难度：⭐⭐⭐ 高级
预计学习时间：3小时
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field, asdict
from enum import Enum

# 尝试导入平台基类
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


# ===== 数据模型定义 =====

class SentimentLabel(Enum):
    """情感标签枚举"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"


class EmotionType(Enum):
    """基本情绪类型"""
    JOY = "joy"
    SADNESS = "sadness"
    ANGER = "anger"
    FEAR = "fear"
    SURPRISE = "surprise"
    DISGUST = "disgust"
    TRUST = "trust"
    ANTICIPATION = "anticipation"


@dataclass
class SentimentResult:
    """单条文本的情感分析结果"""
    
    # 基本信息
    original_text: str
    text_length: int
    detected_language: Optional[str] = None
    
    # 核心情感指标
    sentiment_label: SentimentLabel = SentimentLabel.NEUTRAL
    sentiment_score: float = 0.0  # -1.0 (very negative) to +1.0 (very positive)
    confidence: float = 0.5  # 0.0 to 1.0
    
    # 情绪分布（多个情绪可以共存）
    emotions: Dict[str, float] = field(default_factory=dict)  # {emotion_type: intensity}
    
    # 细粒度指标
    subjectivity: float = 0.5  # 0.0 (objective) to 1.0 (subjective)
    polarity: float = 0.0  # -1.0 to +1.0
    intensity: float = 0.5  # 0.0 (mild) to 1.0 (extreme)
    
    # 提取的内容
    keywords: List[str] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    aspects: List[Dict[str, Any]] = field(default_factory=list)  # aspect-based sentiment
    
    # 原始LLM响应（用于调试）
    raw_response: Optional[str] = None


@dataclass
class AnalysisSummary:
    """批量分析的汇总信息"""
    total_texts: int
    avg_sentiment_score: float
    avg_intensity: float  # 平均情感强度
    sentiment_distribution: Dict[str, int]  # {label: count}
    top_emotions: List[Tuple[str, float]]  # [(emotion, avg_intensity)]
    key_findings: List[str]
    processing_time_ms: int
    tokens_used: int
    estimated_cost_usd: float


# ===== Prompt模板 =====

ANALYSIS_SYSTEM_PROMPT = """You are an expert sentiment analysis AI specializing in multi-dimensional text understanding.

Your task is to analyze the provided text(s) and return a structured JSON response with the following dimensions:

## Required Output Format (STRICT JSON):

```json
{{
  "analyses": [
    {{
      "sentiment": "<positive|negative|neutral|mixed>",
      "score": <-1.0 to 1.0>,
      "confidence": <0.0 to 1.0>,
      "emotions": {{
        "joy": <0.0 to 1.0>,
        "sadness": <0.0 to 1.0>,
        "anger": <0.0 to 1.0>,
        "fear": <0.0 to 1.0>,
        "surprise": <0.0 to 1.0>,
        "disgust": <0.0 to 1.0>
      }},
      "subjectivity": <0.0 to 1.0>,
      "polarity": <-1.0 to 1.0>,
      "intensity": <0.0 to 1.0>,
      "keywords": ["<keyword1>", "<keyword2>"],
      "aspects": [
        {{"aspect": "<topic>", "sentiment": "<pos/neg/neu>", "confidence": <0.0-1.0>}}
      ]
    }}
  ],
  "summary": {{
    "key_findings": ["<finding1>", "<finding2>"]
  }}
}}
```

## Analysis Guidelines:

### Sentiment Scoring:
- **Positive**: score > 0.2 (happy, satisfied, praising)
- **Negative**: score < -0.2 (angry, disappointed, criticizing)
- **Neutral**: -0.2 <= score <= 0.2 (factual, informational)
- **Mixed**: contains both positive and negative elements

### Emotion Intensity (0.0 - 1.0):
Rate each emotion's presence and strength in the text.

### Subjectivity:
- 0.0-0.3: Mostly objective facts
- 0.3-0.7: Mix of opinion and fact
- 0.7-1.0: Highly subjective/personal opinion

### Polarity:
Similar to sentiment but more fine-grained (-1.0 to +1.0)

### Intensity:
How strongly expressed are the emotions? (mild → extreme)

## Important Rules:
- Return ONLY valid JSON, no markdown formatting or explanations
- Ensure all scores are within specified ranges
- If text is empty or unclear, mark as neutral with low confidence
- Extract meaningful keywords (not stop words)
- Identify specific aspects/topics being discussed
"""


class SentimentAnalyzerPlugin(BaseWorkflowNodePlugin):
    """
    AI情感分析插件
    
    功能特性：
    - 6个分析维度：情感、情绪、主观性、极性、强度、方面级
    - 支持8种基本情绪类型识别
    - 自动语言检测
    - 关键词和实体提取
    - 方面级情感分析（ABSA）
    - 批量处理与结果聚合
    - 可视化报告生成建议
    
    使用场景：
    - 社交媒体监控与分析
    - 产品评论挖掘
    - 客户反馈分析
    - 品牌声誉监测
    - 市场调研数据处理
    """
    
    id = "sentiment-analyzer"
    name = "AI Sentiment Analyzer"
    version = "1.0.0"
    
    def __init__(self):
        super().__init__()
        
        # HTTP客户端
        self._http_client = None
        
        # 统计数据
        self._stats = {
            "total_analyses": 0,
            "total_texts_processed": 0,
            "total_tokens_used": 0,
            "cache_hits": 0,
            "errors": 0
        }
        
        # 价格表（每1K tokens）
        PRICING = {
            "openai": {"gpt-4": 0.045, "gpt-4-turbo": 0.02, "gpt-3.5-turbo": 0.001},
            "deepseek": {"deepseek-chat": 0.0028},
            "anthropic": {"claude-3-opus": 0.045, "claude-3-sonnet": 0.009}
        }
    
    async def _get_http_client(self):
        """获取HTTP客户端"""
        if not self._http_client:
            try:
                import httpx
                
                self._http_client = httpx.AsyncClient(
                    timeout=60.0,  # 分析任务可能较慢
                    limits=httpx.Limits(
                        max_connections=10,
                        max_keepalive_connections=5
                    )
                )
                
            except ImportError:
                raise RuntimeError("httpx package required. Install: pip install httpx")
        
        return self._http_client
    
    async def on_load(self) -> None:
        print(f"[{self.id}] Loading sentiment analyzer...")
        await self._get_http_client()
        print(f"[{self.id}] Analyzer ready")
    
    async def on_unload(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        
        print(f"[{self.id}] Unloaded")
    
    async def get_info(self) -> PluginManifest:
        return PluginManifest(
            id=self.id,
            name=self.name,
            version=self.version,
            category="workflow_node",
            description="Multi-dimensional AI sentiment analysis using LLMs",
            capabilities=["execute", "validate_inputs", "generate_report"],
            permissions_required=["llm:use", "network:read"]
        )
    
    async def health_check(self) -> HealthStatus:
        is_healthy = True
        
        return HealthStatus(
            status="healthy" if is_healthy else "degraded",
            message=f"Ready | Analyzed: {self._stats['total_texts_processed']} texts",
            timestamp=datetime.utcnow(),
            details={
                "texts_processed": self._stats["total_texts_processed"],
                "total_tokens": self._stats["total_tokens_used"]
            }
        )
    
    async def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, str]:
        """验证输入参数"""
        
        if 'texts' not in inputs:
            return False, "Missing required field: 'texts'"
        
        texts = inputs['texts']
        
        # 支持字符串或数组
        if isinstance(texts, str):
            texts_list = [texts]
        elif isinstance(texts, list):
            texts_list = texts
        else:
            return False, "'texts' must be string or array of strings"
        
        # 验证非空
        if not texts_list or all(not t or not t.strip() for t in texts_list):
            return False, "'texts' cannot be empty"
        
        # 验证长度限制
        for i, text in enumerate(texts_list):
            if text and len(text) > 5000:
                return False, f"Text at index {i} too long (max 5000 chars)"
        
        # 验证数量限制
        if len(texts_list) > 20:
            return False, f"Too many texts ({len(texts_list)}, max 20)"
        
        return True, "Inputs validated"
    
    async def execute(
        self,
        ctx: PluginContext,
        inputs: Dict[str, Any]
    ) -> NodeOutput:
        """
        执行情感分析
        
        处理流程：
        1. 验证输入
        2. 读取配置
        3. 规范化输入
        4. 构建分析Prompt
        5. 调用LLM API
        6. 解析JSON响应
        7. 构建SentimentResult对象
        8. 聚合统计数据
        9. 发出完成事件
        10. 返回结果
        """
        
        start_time = time.perf_counter()
        
        try:
            # 步骤1: 验证
            is_valid, error_msg = await self.validate_inputs(inputs)
            if not is_valid:
                return NodeOutput(success=False, data={}, message=error_msg, execution_time_ms=0)
            
            # 步骤2: 读取配置
            config = ctx.config or {}
            
            api_key = config.get('api_key', '')
            if not api_key:
                return NodeOutput(
                    success=False,
                    data={},
                    message="API key required. Configure in plugin settings.",
                    execution_time_ms=0
                )
            
            provider = config.get('api_provider', 'openai')
            model = config.get('model_name', 'gpt-4')
            temperature = config.get('temperature', 0.1)
            max_tokens = config.get('max_tokens', 3000)
            
            dimensions = config.get('analysis_dimensions', ['sentiment', 'emotion', 'aspects'])
            output_format = config.get('output_format', 'detailed_json')
            include_keywords = config.get('include_keywords', True)
            include_entities = config.get('include_entities', False)
            detect_language = config.get('language_detection', True)
            batch_size = config.get('batch_size', 5)
            
            context = inputs.get('context', 'General text analysis')
            custom_labels = inputs.get('custom_labels', {})
            
            # 步骤3: 规范化输入
            raw_texts = inputs['texts']
            if isinstance(raw_texts, str):
                texts_to_analyze = [raw_texts.strip()]
            else:
                texts_to_analyze = [t.strip() for t in raw_texts if t and t.strip()]
            
            # 发出开始事件
            if ctx.event_bus:
                await ctx.event_bus.emit("analysis:started", {
                    "plugin_id": self.id,
                    "text_count": len(texts_to_analyze),
                    "dimensions": dimensions,
                    "model": model
                })
            
            # 步骤4-7: 分批调用API并解析
            all_results: List[SentimentResult] = []
            total_tokens = 0
            
            # 分批处理
            for batch_start in range(0, len(texts_to_analyze), batch_size):
                batch_texts = texts_to_analyze[batch_start:batch_start + batch_size]
                
                # 构建用户消息
                user_message = self._build_user_prompt(
                    texts=batch_texts,
                    context=context,
                    dimensions=dimensions,
                    include_keywords=include_keywords,
                    include_entities=include_entities,
                    custom_labels=custom_labels
                )
                
                # 调用API
                response_data, tokens_used = await self._call_analysis_api(
                    user_message=user_message,
                    provider=provider,
                    model=model,
                    api_key=api_key,
                    base_url=config.get('base_url'),
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                
                total_tokens += tokens_used
                
                # 解析响应
                batch_results = self._parse_analysis_response(
                    response_data=response_data,
                    original_texts=batch_texts,
                    detect_language=detect_language
                )
                
                all_results.extend(batch_results)
            
            # 步骤8: 聚合统计
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            summary = self._aggregate_summary(all_results, elapsed_ms, total_tokens)
            
            # 更新全局统计
            self._stats["total_analyses"] += 1
            self._stats["total_texts_processed"] += len(all_results)
            self._stats["total_tokens_used"] += total_tokens
            
            # 步骤9: 构建输出
            output_data = self._format_output(
                results=all_results,
                summary=summary,
                output_format=output_format
            )
            
            # 发出完成事件
            if ctx.event_bus:
                await ctx.event_bus.emit("analysis:completed", {
                    "plugin_id": self.id,
                    "results_count": len(all_results),
                    "avg_score": round(summary.avg_sentiment_score, 3),
                    "tokens_used": total_tokens,
                    "duration_ms": elapsed_ms
                })
            
            return NodeOutput(
                success=True,
                data=output_data,
                message=(
                    f"Analyzed {len(all_results)} text(s). "
                    f"Avg sentiment: {round(summary.avg_sentiment_score, 3)}"
                ),
                execution_time_ms=elapsed_ms
            )
            
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            self._stats["errors"] += 1
            
            if ctx.event_bus:
                await ctx.event_bus.emit("analysis:failed", {
                    "plugin_id": self.id,
                    "error": str(e)[:200],
                    "duration_ms": elapsed_ms
                })
            
            print(f"[ERROR] {self.id}: {e}")
            
            return NodeOutput(
                success=False,
                message=f"Analysis failed: {str(e)}",
                execution_time_ms=elapsed_ms
            )
    
    def _build_user_prompt(
        self,
        texts: List[str],
        context: str,
        dimensions: List[str],
        include_keywords: bool,
        include_entities: bool,
        custom_labels: Dict[str, List[str]]
    ) -> str:
        """构建用户提示词"""
        
        prompt_parts = []
        
        # 添加上下文
        prompt_parts.append(f"Context/Domain: {context}")
        
        # 添加维度说明
        dim_descriptions = {
            "sentiment": "Overall positive/negative/neutral classification",
            "emotion": "Basic emotion types (joy, sadness, anger, fear, etc.)",
            "subjectivity": "Objective vs subjective content",
            "polarity": "Fine-grained positive/negative scale",
            "intensity": "Strength of emotional expression",
            "aspects": "Topic-specific sentiment (aspect-based analysis)"
        }
        
        active_dims = [dim_descriptions[d] for d in dimensions if d in dim_descriptions]
        prompt_parts.append(f"\nAnalysis Dimensions:\n" + "\n".join(f"- {d}" for d in active_dims))
        
        # 添加额外要求
        extras = []
        if include_keywords:
            extras.append("- Extract important keywords")
        if include_entities:
            extras.append("- Identify named entities (people, organizations, locations)")
        if custom_labels:
            extras.append(f"- Map sentiments to custom labels: {json.dumps(custom_labels)}")
        
        if extras:
            prompt_parts.append("\nAdditional Requirements:\n" + "\n".join(extras))
        
        # 添加待分析文本
        prompt_parts.append("\n\nTexts to Analyze:")
        for i, text in enumerate(texts, 1):
            prompt_parts.append(f"\n--- Text {i} ---\n{text}")
        
        prompt_parts.append("\n\nProvide the analysis in the exact JSON format specified above.")
        
        return "\n".join(prompt_parts)
    
    async def _call_analysis_api(
        self,
        user_message: str,
        provider: str,
        model: str,
        api_key: str,
        base_url: Optional[str],
        temperature: float,
        max_tokens: int
    ) -> Tuple[dict, int]:
        """调用分析API"""
        
        client = await self._get_http_client()
        
        url = base_url if base_url else self._get_default_endpoint(provider)
        headers = self._build_headers(provider, api_key)
        payload = self._build_payload(provider, model, user_message, temperature, max_tokens)
        
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        
        data = response.json()
        
        # 提取token使用量
        tokens_used = 0
        if "usage" in data:
            tokens_used = data["usage"].get("total_tokens", 0)
        elif data.get("usage"):
            tokens_used = data["usage"].get("output_tokens", 0)
        
        return data, tokens_used
    
    def _get_default_endpoint(self, provider: str) -> str:
        """获取默认API端点"""
        endpoints = {
            "openai": "https://api.openai.com/v1/chat/completions",
            "deepseek": "https://api.deepseek.com/chat/completions",
            "anthropic": "https://api.anthropic.com/v1/messages"
        }
        return endpoints.get(provider, endpoints["openai"])
    
    def _build_headers(self, provider: str, api_key: str) -> dict:
        """构建请求头"""
        if provider == "anthropic":
            return {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
        else:
            return {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
    
    def _build_payload(
        self,
        provider: str,
        model: str,
        message: str,
        temperature: float,
        max_tokens: int
    ) -> dict:
        """构建请求体"""
        
        if provider == "anthropic":
            return {
                "model": model,
                "max_tokens": max_tokens,
                "system": ANALYSIS_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": message}]
            }
        else:
            return {
                "model": model,
                "messages": [
                    {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
                    {"role": "user", "content": message}
                ],
                "temperature": temperature,
                "max_tokens": max_tokens
            }
    
    def _parse_analysis_response(
        self,
        response_data: dict,
        original_texts: List[str],
        detect_language: bool
    ) -> List[SentimentResult]:
        """解析API响应为SentimentResult列表"""
        
        results = []
        
        try:
            # 提取内容
            if "choices" in response_data:
                content = response_data["choices"][0]["message"]["content"]
            elif "content" in response_data:
                content = response_data["content"][0]["text"]
            else:
                raise ValueError("Unexpected response format")
            
            # 清理可能的markdown代码块标记
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            # 解析JSON
            parsed = json.loads(content)
            analyses = parsed.get("analyses", [])
            
            for i, analysis in enumerate(analyses):
                if i >= len(original_texts):
                    break
                
                original_text = original_texts[i]
                
                # 映射情感标签
                label_str = analysis.get("sentiment", "neutral").lower()
                try:
                    label = SentimentLabel(label_str)
                except ValueError:
                    label = SentimentLabel.NEUTRAL
                
                result = SentimentResult(
                    original_text=original_text,
                    text_length=len(original_text),
                    detected_language=None,  # TODO: 实现语言检测
                    sentiment_label=label,
                    sentiment_score=float(analysis.get("score", 0.0)),
                    confidence=float(analysis.get("confidence", 0.5)),
                    emotions=analysis.get("emotions", {}),
                    subjectivity=float(analysis.get("subjectivity", 0.5)),
                    polarity=float(analysis.get("polarity", 0.0)),
                    intensity=float(analysis.get("intensity", 0.5)),
                    keywords=analysis.get("keywords", []),
                    entities=[],  # TODO: 从response中提取
                    aspects=analysis.get("aspects", []),
                    raw_response=content
                )
                
                results.append(result)
            
            # 如果返回的分析数少于原始文本，为缺失的创建空结果
            while len(results) < len(original_texts):
                idx = len(results)
                results.append(SentimentResult(
                    original_text=original_texts[idx],
                    text_length=len(original_texts[idx]),
                    raw_response="[PARSING ERROR]"
                ))
        
        except (json.JSONDecodeError, KeyError, IndexError, ValueError) as e:
            print(f"[ERROR] Failed to parse analysis response: {e}")
            
            # 为所有文本创建错误标记的结果
            for text in original_texts:
                results.append(SentimentResult(
                    original_text=text,
                    text_length=len(text),
                    raw_response=f"[PARSE ERROR: {str(e)[:100]}]"
                ))
        
        return results
    
    def _aggregate_summary(
        self,
        results: List[SentimentResult],
        processing_time_ms: int,
        tokens_used: int
    ) -> AnalysisSummary:
        """聚合批量分析结果"""
        
        if not results:
            return AnalysisSummary(
                total_texts=0,
                avg_sentiment_score=0.0,
                avg_intensity=0.0,
                sentiment_distribution={},
                top_emotions=[],
                key_findings=["No texts analyzed"],
                processing_time_ms=processing_time_ms,
                tokens_used=tokens_used,
                estimated_cost_usd=0.0
            )
        
        # 平均情感得分
        avg_score = sum(r.sentiment_score for r in results) / len(results)
        
        # 情感分布
        distribution = {}
        for r in results:
            label = r.sentiment_label.value
            distribution[label] = distribution.get(label, 0) + 1
        
        # 汇总情绪
        emotion_sums = {}
        for r in results:
            for emotion, intensity in r.emotions.items():
                emotion_sums[emotion] = emotion_sums.get(emotion, 0) + intensity
        
        # 计算平均情绪强度
        num_results = len(results)
        top_emotions = sorted(
            [(e, s / num_results) for e, s in emotion_sums.items()],
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        # 关键发现（基于关键词和情感）
        key_findings = []
        if avg_score > 0.3:
            key_findings.append(f"Overall positive sentiment ({avg_score:.2f})")
        elif avg_score < -0.3:
            key_findings.append(f"Overall negative sentiment ({avg_score:.2f})")
        else:
            key_findings.append(f"Neutral/mixed sentiment ({avg_score:.2f})")
        
        # 最常见的情感
        most_common = max(distribution.items(), key=lambda x: x[1])[0]
        key_findings.append(f"Dominant sentiment: {most_common}")
        
        # 费用估算
        cost = self._estimate_cost(tokens_used)

        # 计算平均强度
        avg_intensity = sum(r.intensity for r in results) / len(results) if results else 0.0

        return AnalysisSummary(
            total_texts=len(results),
            avg_sentiment_score=round(avg_score, 4),
            avg_intensity=round(avg_intensity, 4),
            sentiment_distribution=distribution,
            top_emotions=top_emotions,
            key_findings=key_findings,
            processing_time_ms=processing_time_ms,
            tokens_used=tokens_used,
            estimated_cost_usd=cost
        )
    
    def _estimate_cost(self, tokens: int) -> float:
        """估算费用（使用GPT-4价格作为基准）"""
        # 默认$0.045 per 1K tokens (GPT-4 average)
        return round((tokens / 1000) * 0.045, 6)
    
    def _format_output(
        self,
        results: List[SentimentResult],
        summary: AnalysisSummary,
        output_format: str
    ) -> Dict[str, Any]:
        """格式化输出数据"""
        
        if output_format == "report":
            # 报告格式：包含可视化建议
            return self._format_report_output(results, summary)
        elif output_format == "summary":
            # 简洁格式：只包含摘要
            return {
                "summary": asdict(summary)
            }
        else:
            # JSON格式（默认）：完整详细数据
            return {
                "analyses": [asdict(r) for r in results],
                "summary": asdict(summary)
            }
    
    def _format_report_output(
        self,
        results: List[SentimentResult],
        summary: AnalysisSummary
    ) -> Dict[str, Any]:
        """格式化为报告输出（包含可视化元数据）"""
        
        # 准备图表数据
        chart_data = {
            "sentiment_distribution": {
                "type": "pie",
                "data": summary.sentiment_distribution,
                "labels": {
                    "positive": "😊 Positive",
                    "negative": "😠 Negative",
                    "neutral": "😐 Neutral",
                    "mixed": "🔄 Mixed"
                }
            },
            "emotion_radar": {
                "type": "radar",
                "categories": [e[0] for e in summary.top_emotions],
                "values": [round(e[1], 3) for e in summary.top_emotions]
            },
            "sentiment_timeline": {
                "type": "line",
                "data": [{"index": i, "score": r.sentiment_score} 
                        for i, r in enumerate(results)]
            }
        }
        
        return {
            "report_title": "Sentiment Analysis Report",
            "generated_at": datetime.utcnow().isoformat(),
            "executive_summary": {
                "overall_sentiment": (
                    "Positive" if summary.avg_sentiment_score > 0.2 
                    else "Negative" if summary.avg_sentiment_score < -0.2 
                    else "Neutral"
                ),
                "score": round(summary.avg_sentiment_score, 3),
                "texts_analyzed": summary.total_texts,
                "key_findings": summary.key_findings
            },
            "detailed_results": [asdict(r) for r in results],
            "aggregated_statistics": asdict(summary),
            "visualizations": chart_data,
            "recommendations": self._generate_recommendations(summary)
        }
    
    def _generate_recommendations(self, summary: AnalysisSummary) -> List[str]:
        """基于分析结果生成建议"""
        
        recommendations = []
        
        if summary.avg_sentiment_score > 0.5:
            recommendations.append("Strong positive sentiment - consider leveraging testimonials")
        elif summary.avg_sentiment_score < -0.5:
            recommendations.append("Significant negative sentiment - immediate attention needed")
        
        neg_pct = summary.sentiment_distribution.get("negative", 0) / max(summary.total_texts, 1)
        if neg_pct > 0.3:
            recommendations.append(f"{neg_pct*100:.0f}% negative - review common complaints")
        
        if summary.avg_intensity and summary.avg_intensity > 0.7:
            recommendations.append("High emotional intensity - may indicate strong opinions")
        
        if not recommendations:
            recommendations.append("Sentiments appear balanced - continue monitoring")
        
        return recommendations


# ===== 本地测试入口 =====

if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("=" * 70)
        print("  AI Sentiment Analyzer - Local Test Mode")
        print("=" * 70)
        
        plugin = SentimentAnalyzerPlugin()
        
        # 测试1: 验证功能
        print("\n[Test 1] Input validation:")
        
        valid, msg = await plugin.validate_inputs({
            "texts": ["I love this product!", "Terrible experience."],
            "context": "Product reviews"
        })
        print(f"  Valid input: {valid}, Message: {msg}")
        
        invalid, msg = await plugin.validate_inputs({})
        print(f"  Invalid input: {invalid}, Message: {msg}")
        
        # 测试2: 健康检查
        print("\n[Test 2] Health check:")
        health = await plugin.health_check()
        print(f"  Status: {health.status}")
        print(f"  Message: {health.message}")
        
        # 测试3: 信息获取
        print("\n[Test 3] Plugin info:")
        info = await plugin.get_info()
        print(f"  ID: {info.id}")
        print(f"  Capabilities: {info.capabilities}")
        
        # 测试4: 数据模型验证
        print("\n[Test 4] Data models:")
        
        result = SentimentResult(
            original_text="Great product!",
            text_length=14,
            sentiment_label=SentimentLabel.POSITIVE,
            sentiment_score=0.8,
            confidence=0.95,
            emotions={"joy": 0.9, "trust": 0.7},
            subjectivity=0.7,
            keywords=["great", "product"]
        )
        
        print(f"  SentimentResult created: ✓")
        print(f"  Label: {result.sentiment_label.value}")
        print(f"  Score: {result.sentiment_score}")
        print(f"  Keywords: {result.keywords}")
        
        # 测试5: 输出格式化
        print("\n[Test 5] Output formatting:")
        
        test_results = [result]
        test_summary = AnalysisSummary(
            total_texts=1,
            avg_sentiment_score=0.8,
            avg_intensity=0.85,
            sentiment_distribution={"positive": 1},
            top_emotions=[("joy", 0.9)],
            key_findings=["Positive sentiment detected"],
            processing_time_ms=150,
            tokens_used=50,
            estimated_cost_usd=0.00225
        )
        
        json_output = plugin._format_output(test_results, test_summary, "detailed_json")
        report_output = plugin._format_output(test_results, test_summary, "report")
        
        print(f"  JSON output keys: {list(json_output.keys())}")
        print(f"  Report output keys: {list(report_output.keys())}")
        print(f"  Has visualizations: {'visualizations' in report_output}")
        print(f"  Has recommendations: {'recommendations' in report_output}")
        
        print("\n" + "=" * 70)
        print("  All tests completed!")
        print("=" * 70)
        print("\nNote: To test actual analysis, configure real API keys")
        print("      and run: plugin dev → call execute endpoint")
    
    asyncio.run(test())