"""
AI Copywrite Node Plugin - AI文案生成工作流节点插件
将现有 copywrite_node 逻辑包装为标准 WorkflowNode Plugin
"""

from __future__ import annotations

import logging
import time
import re
from typing import Any, Dict, Optional

from app.core.base_interfaces import (
    BaseWorkflowNodePlugin,
    PluginContext,
    NodeExecutionError,
)
from app.core.plugin_types import PluginCategory


class AICopywriteNodePlugin(BaseWorkflowNodePlugin):
    """
    AI文案生成工作流节点插件
    
    功能：
    1. 基于LLM的小红书专业文案生成
    2. 多种写作风格支持（爆款/种草/避雷/情感/科普）
    3. 自动融合上游分析洞察和图片描述
    4. 用户偏好记忆注入（跨工作流）
    5. 成本控制与降级模板
    
    输入依赖：
    - analyze 节点：patterns + insights（情绪/场景/视觉模式）
    - image_gen 节点：image_details[] + style
    - image_review 节点：feedback（可选，审核修正建议）
    
    输出：
    - title: 符合平台调性的标题
    - content: 高质量正文内容
    - tags: 相关话题标签列表
    - 元数据：字数、风格、模型、耗时等
    """

    @property
    def plugin_id(self) -> str:
        return "ai-copywrite-node"

    @property
    def plugin_name(self) -> str:
        return "AI文案生成器"

    @property
    def node_type(self) -> str:
        return "ai_copywrite"

    @property
    def display_name(self) -> str:
        return "AI文案生成"

    @property
    def description(self) -> str:
        return ("基于LLM生成符合小红书调性的专业文案，"
                "融合分析洞察、图片描述和用户偏好")

    @property
    def icon(self) -> str:
        return "✍️"

    @property
    def input_schema(self) -> Dict[str, Any]:
        """输入参数Schema"""
        return {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "选题/主题关键词"
                },
                "analyze_output": {
                    "type": "object",
                    "description": "分析节点的输出数据",
                    "properties": {
                        "patterns": {"type": "object"},
                        "insights": {"type": "object"}
                    }
                },
                "image_gen_output": {
                    "type": "object",
                    "description": "图片生成节点的输出",
                    "properties": {
                        "image_details": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "图片描述列表"
                        },
                        "style": {"type": "string", "description": "图片风格"}
                    }
                },
                "image_review_feedback": {
                    "type": "string",
                    "description": "图片审核反馈"
                },
                "reference": {
                    "type": "object",
                    "description": "选题池参考素材"
                },
                "user_memory": {
                    "type": "object",
                    "description": "用户长期记忆"
                }
            },
            "required": ["topic"]
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        """输出参数Schema"""
        return {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "笔记标题"},
                "content": {"type": "string", "description": "正文内容"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "话题标签"
                },
                "word_count": {"type": "integer", "description": "字数统计"},
                "style_applied": {"type": "string", "description": "写作风格"},
                "model_used": {"type": "string", "description": "使用的模型"},
                "generation_time_ms": {"type": "integer", "description": "生成耗时(ms)"}
            }
        }

    async def setup(self, ctx: PluginContext) -> None:
        """初始化文案生成器，加载配置和LLM适配器"""
        await super().setup(ctx)
        
        self._log(logging.INFO, "初始化AI文案生成器...")
        
        try:
            config = ctx.config or {}
            
            # 加载配置参数
            self._model = config.get("text_model", "deepseek-chat")
            self._temperature = config.get("temperature", 0.7)
            self._max_tokens = config.get("max_tokens", 1500)
            self._writing_style = config.get("writing_style", "爆款标题党")
            self._content_length = config.get("content_length", 500)
            self._auto_emoji = config.get("auto_emoji", True)
            self._auto_tags = config.get("auto_tags", True)
            self._enable_memory = config.get("enable_user_memory", True)
            
            # 初始化LLM适配器
            from app.agents.adapters.deepseek import DeepSeekAdapter
            
            self._llm_adapter = DeepSeekAdapter(
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            
            self._log(
                logging.INFO,
                f"配置加载完成 | 模型: {self._model} | "
                f"风格: {self._writing_style} | 目标字数: {self._content_length}"
            )
            
        except Exception as e:
            self._log(logging.ERROR, f"初始化失败: {e}")
            raise

    async def execute(
        self,
        inputs: Dict[str, Any],
        node_config: Dict[str, Any],
        ctx: PluginContext
    ) -> Dict[str, Any]:
        """
        执行文案生成逻辑
        
        Args:
            inputs: 上游节点传递的输入数据
                - topic: 选题主题
                - analyze_output: 分析结果（patterns + insights）
                - image_gen_output: 图片信息（image_details + style）
                - image_review_feedback: 审核反馈（可选）
                - reference: 选题池参考（可选）
                - user_memory: 用户记忆（可选）
            node_config: 当前节点配置（可覆盖默认值）
            ctx: 插件上下文
                
        Returns:
            节点输出字典：
            - title: 生成的标题
            - content: 生成的正文
            - tags: 标签列表
            - word_count: 字数统计
            - style_applied: 应用的风格
            - model_used: 实际使用的模型
            - generation_time_ms: 耗时
        """
        start_time = time.time()
        
        # 合并配置（node_config优先级更高）
        base_config = ctx.config if ctx.config else {}
        effective_config = {**base_config, **node_config}
        topic = inputs.get("topic", "")
        
        self._log(logging.INFO, f"开始生成文案 | 选题: {topic[:30]}...")
        
        try:
            # 发布开始事件
            await ctx.event_bus.publish("workflow:node_started:copywrite", {
                "topic": topic,
                "plugin_id": self.plugin_id,
            }, source_plugin_id=self.plugin_id)
            
            # Step 1: 收集并处理上游数据
            processed_inputs = await self._prepare_inputs(inputs, effective_config)
            
            # Step 2: 构建Prompt
            prompt = await self._build_prompt(processed_inputs, effective_config)
            
            # Step 3: 调用LLM生成
            generated_text = await self._call_llm(prompt, effective_config)
            
            # Step 4: 解析输出结构化数据
            result = self._parse_llm_output(generated_text, topic)
            
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            # 补充元数据
            result.update({
                "word_count": len(result["content"]),
                "style_applied": effective_config.get("writing_style", self._writing_style),
                "model_used": self._model,
                "generation_time_ms": execution_time_ms,
            })
            
            self._log(
                logging.INFO,
                f"文案生成完成 | 标题: {result['title'][:20]}... | "
                f"字数: {result['word_count']} | 耗时: {execution_time_ms}ms"
            )
            
            # 发布完成事件
            await ctx.event_bus.publish("workflow:node_completed:copywrite", {
                **result,
                "plugin_id": self.plugin_id,
            }, source_plugin_id=self.plugin_id)
            
            # 发布内容生成事件
            await ctx.event_bus.publish("content:generated", {
                "title": result["title"],
                "content_length": result["word_count"],
                "style": result["style_applied"],
                "tags_count": len(result.get("tags", [])),
            }, source_plugin_id=self.plugin_id)
            
            return result
            
        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_msg = f"文案生成失败: {str(e)}"
            
            self._log(logging.ERROR, error_msg, exc_info=True)
            
            # 尝试降级为模板生成
            fallback_result = await self._fallback_template_generation(
                inputs, effective_config, execution_time_ms
            )
            
            if fallback_result:
                self._log(logging.WARNING, "已降级为模板生成")
                fallback_result["_fallback"] = True
                fallback_result["_error"] = error_msg
                return fallback_result
            
            raise NodeExecutionError(
                message=error_msg,
                node_type=self.node_type,
                recoverable=False
            )

    async def before_execute(
        self,
        inputs: Dict[str, Any],
        node_config: Dict[str, Any]
    ) -> None:
        """
        执行前钩子：验证必要输入
        
        Raises:
            ValueError: 缺少必要字段时抛出
        """
        if not inputs.get("topic"):
            raise ValueError("缺少必要输入: topic（选题）")
        
        if not inputs.get("analyze_output") and not inputs.get("image_gen_output"):
            self._log(
                logging.WARNING,
                "缺少上游分析或图片数据，将使用基础模板生成"
            )

    async def after_execute(
        self,
        result: Dict[str, Any],
        execution_time_ms: int
    ) -> None:
        """
        执行后钩子：日志记录和质量检查
        """
        word_count = result.get("word_count", 0)
        target_length = self._content_length
        
        quality_score = min(100, (word_count / target_length) * 100) if target_length > 0 else 100
        
        self._log(
            logging.INFO,
            f"质量评估 | 字数达标率: {quality_score:.1f}% | "
            f"目标: {target_length} | 实际: {word_count}"
        )

    async def _prepare_inputs(
        self,
        raw_inputs: Dict[str, Any],
        config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """预处理输入数据，提取关键字段"""
        
        topic = raw_inputs.get("topic", "")
        
        # 提取分析结果
        analyze_output = raw_inputs.get("analyze_output", {}) or {}
        patterns = analyze_output.get("patterns", {})
        insights = analyze_output.get("insights", {})
        
        # 提取执行指令（从recommendations[0].execution_brief）
        recommendations = insights.get("recommendations", [])
        execution_brief = {}
        if recommendations and isinstance(recommendations[0], dict):
            brief = recommendations[0].get("execution_brief")
            if isinstance(brief, dict):
                execution_brief = brief
        
        # 提取图片信息
        image_gen_output = raw_inputs.get("image_gen_output", {}) or {}
        image_details = image_gen_output.get("image_details", [])
        image_style = image_gen_output.get("style", "")
        
        # 提取审核反馈
        image_review_output = raw_inputs.get("image_review_feedback", "")
        
        # 提取参考素材和用户记忆
        reference = raw_inputs.get("reference", {}) or {}
        user_memory = raw_inputs.get("user_memory", {}) or {} if self._enable_memory else {}
        
        return {
            "topic": topic,
            "patterns": patterns,
            "insights": insights,
            "execution_brief": execution_brief,
            "image_details": image_details,
            "image_style": image_style,
            "review_feedback": image_review_output,
            "reference": reference,
            "user_memory": user_memory,
        }

    async def _build_prompt(
        self,
        processed: Dict[str, Any],
        config: Dict[str, Any]
    ) -> str:
        """构建LLM Prompt"""
        
        writing_style = config.get("writing_style", self._writing_style)
        content_length = config.get("content_length", self._content_length)
        auto_emoji = config.get("auto_emoji", self._auto_emoji)
        auto_tags = config.get("auto_tags", self._auto_tags)
        
        prompt_parts = [
            f"""你是一位小红书爆款文案专家。请根据以下信息生成一篇{writing_style}风格的笔记。

## 选题主题
{processed['topic']}

## 写作要求
- 风格：{writing_style}
- 正文字数：约{content_length}字
- {'自动添加emoji表情符号' if auto_emoji else '不使用emoji'}
- {'自动生成3-5个话题标签' if auto_tags else '不生成标签'}
"""
        ]
        
        # 添加分析洞察
        if processed.get("patterns") or processed.get("execution_brief"):
            prompt_parts.append("\n## 分析洞察\n")
            if processed.get("patterns"):
                prompt_parts.append(f"- 情绪维度：{processed['patterns'].get('emotion', '未知')}\n")
                prompt_parts.append(f"- 场景维度：{processed['patterns'].get('scene', '未知')}\n")
                prompt_parts.append(f"- 视觉形式：{processed['patterns'].get('visual', '未知')}\n")
            if processed.get("execution_brief"):
                prompt_parts.append(f"\n执行建议：\n")
                for key, value in processed["execution_brief"].items():
                    prompt_parts.append(f"- {key}: {value}\n")
        
        # 添加图片描述
        if processed.get("image_details"):
            prompt_parts.append("\n## 配图说明\n")
            for i, detail in enumerate(processed["image_details"][:3], 1):  # 最多3张图
                desc = detail.get("description", "") if isinstance(detail, dict) else str(detail)
                prompt_parts.append(f"- 图{i}: {desc[:100]}\n")
            if processed.get("image_style"):
                prompt_parts.append(f"\n整体风格：{processed['image_style']}")
        
        # 添加审核反馈
        if processed.get("review_feedback"):
            prompt_parts.append(f"\n## 图片审核反馈\n{processed['review_feedback']}\n")
        
        # 注入用户记忆（跨工作流偏好）
        if processed.get("user_memory") and self._enable_memory:
            memory = processed["user_memory"]
            memory_parts = []
            if memory.get("preferred_topics"):
                memory_parts.append(f"- 偏好领域：{', '.join(memory['preferred_topics'][:5])}")
            if memory.get("writing_preferences"):
                memory_parts.append(f"- 文风偏好：{memory['writing_preferences']}")
            if memory_parts:
                prompt_parts.append("\n## 用户历史偏好（供参考）\n")
                prompt_parts.extend([f"{m}\n" for m in memory_parts])
        
        # 输出格式指令
        prompt_parts.append("""
## 输出格式（严格JSON）
请严格按照以下JSON格式输出，不要包含其他文字：

```json
{
  "title": "吸引人的标题（15-25字）",
  "content": "正文内容...",
  "tags": ["#标签1", "#标签2", "#标签3"]
}
```
""")
        
        return "".join(prompt_parts)

    async def _call_llm(
        self,
        prompt: str,
        config: Dict[str, Any]
    ) -> str:
        """调用LLM生成文本"""
        
        try:
            messages = [{"role": "user", "content": prompt}]
            
            response = await self._llm_adapter.generate(messages)
            
            return response.strip()
            
        except Exception as e:
            self._log(logging.ERROR, f"LLM调用失败: {e}")
            raise

    def _parse_llm_output(
        self,
        llm_text: str,
        topic: str
    ) -> Dict[str, Any]:
        """解析LLM输出的JSON结构"""
        
        default_result = {
            "title": f"关于{topic}的笔记",
            "content": llm_text,
            "tags": [],
        }
        
        try:
            # 提取JSON部分
            json_match = re.search(r'```json\s*(.*?)\s*```', llm_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1).strip()
            elif llm_text.strip().startswith('{'):
                json_str = llm_text.strip()
            else:
                self._log(logging.WARNING, "未找到JSON格式，尝试整体解析")
                json_str = llm_text
            
            import json
            parsed = json.loads(json_str)
            
            return {
                "title": parsed.get("title", default_result["title"]),
                "content": parsed.get("content", default_result["content"]),
                "tags": parsed.get("tags", []),
            }
            
        except (json.JSONDecodeError, Exception) as e:
            self._log(logging.WARNING, f"JSON解析失败: {e}, 使用原始文本")
            return default_result

    async def _fallback_template_generation(
        self,
        inputs: Dict[str, Any],
        config: Dict[str, Any],
        execution_time_ms: int
    ) -> Optional[Dict[str, Any]]:
        """降级为模板生成（当LLM不可用时）"""
        
        topic = inputs.get("topic", "未知主题")
        style = config.get("writing_style", self._writing_style)
        
        templates = {
            "爆款标题党": {
                "title": f"🔥{topic}！90%的人都不知道的真相！",
                "content": f"姐妹们！今天必须跟你们聊聊{topic}这件事！\n\n真的太震撼了！我之前一直以为...直到最近才发现...\n\n📌重点来了！\n1️⃣ 首先...\n2️⃣ 其次...\n3️⃣ 最重要的是...\n\n真的建议大家试试看！不好用你打我！💪\n\n#{topic.replace(' ', '')} #干货分享 #真实体验",
                "tags": [f"#{topic}", "#干货分享", "#真实体验"],
            },
            "种草安利风": {
                "title": f"挖到宝了‼️这个{topic}真的绝了！",
                "content": f"家人们！今天要给你们按头安利一个超级棒的{topic}！\n\n✨ 使用感受：\n- 外观真的很好看！\n- 效果超出预期！\n- 性价比超高！\n\n💡 小贴士：\n记得搭配使用效果更好哦～\n\n真心推荐给需要的姐妹们！冲就完事了！🛒\n\n#{topic} #好物推荐 #种草",
                "tags": [f"#{topic}", "#好物推荐", "#种草"],
            },
        }
        
        template = templates.get(style, templates["爆款标题党"])
        
        return {
            **template,
            "word_count": len(template["content"]),
            "style_applied": style,
            "model_used": "template_fallback",
            "generation_time_ms": execution_time_ms,
        }

    async def health_check(self) -> tuple[bool, str]:
        """健康检查：验证LLM可用性"""
        try:
            if not hasattr(self, '_llm_adapter'):
                return False, "LLM适配器未初始化"
            
            # 简单测试调用
            test_messages = [{"role": "user", "content": "测试"}]
            response = await self._llm_adapter.generate(test_messages)
            
            return True, f"AI文案生成器运行正常（模型: {self._model}）"
            
        except Exception as e:
            return False, f"健康检查失败: {str(e)}"

    async def teardown(self) -> None:
        """清理资源"""
        self._log(logging.INFO, "释放AI文案生成器资源...")
        
        if hasattr(self, '_llm_adapter'):
            del self._llm_adapter
            
        self._log(logging.INFO, "资源释放完成")


# 导出插件类
__all__ = ['AICopywriteNodePlugin']