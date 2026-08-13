"""分析 Skill 集合：把搜索结果转化为爆款因子分析和选题建议。

可插拔架构（v2）：
- AnalyzeSkillBase：基类，封装 Layer2/Layer3 LLM 分析调用 + 降级
- 1 个内置 Skill 子类：StandardAnalyzeSkill（默认三层分析）
- 第三方可在 backend/skills/ 下新增自己的 AnalyzeSkillBase 子类并 @register

红线：
- LLM 不碰 results 字段，只产出 patterns / insights
- LLM 不可用时降级为只返回 Layer 1 规则分析结果
- evidence_note_ids 必须在 top 20 中校验

设计说明：
- AnalyzeSkillBase 的方法签名与 analyze_layer.run_layer2/run_layer3 对齐，
  方便 graph.py 的 analyze_node 直接替换硬编码调用
- 节点通过 registry 加载 Skill 子类，调用 skill.analyze_layer2/analyze_layer3
- 事件发送逻辑保留在 graph.py 节点层（Skill 不发 SSE 事件）
"""

from __future__ import annotations

import logging
from typing import Any

from app.agents.skills.analyze_layer import run_layer2, run_layer3
from app.agents.skills.base import Skill
from app.agents.skills.registry import register

logger = logging.getLogger(__name__)


class AnalyzeSkillBase(Skill):
    """分析 Skill 基类。

    子类可覆盖：
    - analyze_layer2(): 第二层 LLM 分析（模式识别）
    - analyze_layer3(): 第三层 LLM 深度归因
    - execute(): 完整三层分析流程（默认实现组合 layer1 + layer2 + layer3）

    默认实现复用 analyze_layer.run_layer2 / run_layer3。
    方法签名与 run_layer2/run_layer3 对齐，方便节点直接替换。

    注意：Skill 不负责发 SSE 事件，事件发送由 graph.py 节点层处理。
    graph.py 的 analyze_node 既可以直接调用 analyze_layer2/analyze_layer3
    （保持细粒度事件推送），也可以调用 execute() 一键跑完三层。
    """

    node_type = "analyze"
    name: str = ""
    display_name: str = ""
    description: str = ""

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """执行完整三层分析流程。

        inputs 约定：
        - llm: LLMProtocol 实例（None 时只跑 Layer 1 规则分析）
        - topic: 工作流主题
        - search_results: search 节点的 results 列表

        返回：
        {
            "results": [...],          # 带 metrics 的结果
            "patterns": {...},         # Layer 2 输出
            "insights": {...},         # Layer 3 输出
            "layer1_stats": {...},     # Layer 1 统计
            "_source": "llm" | "fallback",
            "_skill": self.name,
        }

        注意：graph.py 的 analyze_node 目前直接调用 analyze_layer2/analyze_layer3
        而非 execute()，以保持细粒度的 SSE 事件推送。execute() 供第三方 Skill
        或独立调用场景使用。
        """
        from app.agents.skills.viral_analyzer import analyze_viral

        llm = inputs.get("llm")
        topic = inputs.get("topic", "")
        search_results = inputs.get("search_results", []) or []

        # Layer 1: 规则层
        with_metrics, layer1_stats = analyze_viral(search_results)

        if llm is None:
            return {
                "results": with_metrics,
                "patterns": {"_skipped": "no_llm"},
                "insights": {"_skipped": "no_llm"},
                "layer1_stats": layer1_stats,
                "_source": "fallback",
                "_skill": self.name,
            }

        # Layer 2: LLM 模式识别
        top5 = with_metrics[:5]
        patterns = await self.analyze_layer2(llm, top5, topic)

        # Layer 3: LLM 深度归因
        top2 = with_metrics[:2]
        insights = await self.analyze_layer3(
            llm, top2, with_metrics, patterns, topic
        )

        return {
            "results": with_metrics,
            "patterns": patterns,
            "insights": insights,
            "layer1_stats": layer1_stats,
            "_source": "llm",
            "_skill": self.name,
        }

    async def analyze_layer2(
        self,
        llm: Any,
        top_notes: list[dict],
        topic: str,
    ) -> dict:
        """Layer 2: LLM 模式识别（标题钩子 / 内容结构 / 情绪触发点）。

        默认实现委托给 analyze_layer.run_layer2。子类可覆盖以自定义分析逻辑。
        """
        return await run_layer2(llm, top_notes, topic)

    async def analyze_layer3(
        self,
        llm: Any,
        top2: list[dict],
        all_notes: list[dict],
        layer2_output: dict,
        topic: str,
        user_preferences: dict | None = None,
    ) -> dict:
        """Layer 3: LLM 深度归因（趋势信号 + 选题建议）。

        默认实现委托给 analyze_layer.run_layer3。子类可覆盖以自定义归因逻辑。

        Args:
            user_preferences: 用户级长期记忆中的偏好（preferred_topics / avoided_topics）。
        """
        return await run_layer3(
            llm, top2, all_notes, layer2_output, topic, user_preferences
        )


@register
class StandardAnalyzeSkill(AnalyzeSkillBase):
    """默认三层分析 Skill。"""

    name = "standard"
    display_name = "标准三层分析"
    description = "Layer1 规则分析 + Layer2 模式识别 + Layer3 深度归因"
