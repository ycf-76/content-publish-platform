"""Chat Agent：把自然语言请求跑进 AgentHarness + LoopExecutor。

流程：输入守卫 → 意图解析 → 分流执行。
职责是编排，不直接调用 LLM / Skill / 模型路由（analyze 单步除外，
它需要复用 DAG 的搜索+三层分析逻辑，无法走通用 prompt harness）。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from app.agents.core.schemas import AgentOutput, LLMProtocol, WorkflowContext
from app.agents.input_rules import ChatInputRule
from app.agents.intent_parser import ActionType, ParsedIntent, RuleBasedIntentParser
from app.agents.registry import AgentRegistry

logger = logging.getLogger(__name__)


@dataclass
class ChatResult:
    status: str  # blocked / chat / agent_output
    intent: ParsedIntent | None = None
    output: AgentOutput | None = None
    message: str = ""


class ChatAgent:
    """编排 Chat 请求：守卫 → 意图 → 分流执行。"""

    _ACTION_TO_AGENT = {
        ActionType.SEARCH_ONLY: "search",
        ActionType.EXPLORE: "explore",
    }

    def __init__(
        self,
        registry: AgentRegistry | None = None,
        intent_parser: RuleBasedIntentParser | None = None,
        input_rule: ChatInputRule | None = None,
        llm: LLMProtocol | None = None,
    ) -> None:
        self._registry = registry or AgentRegistry()
        self._intent_parser = intent_parser or RuleBasedIntentParser()
        self._input_rule = input_rule or ChatInputRule()
        self._llm = llm

    async def process(
        self,
        message: str,
        session_id: str,
        user_id: str,
        workflow_id: str | None = None,
    ) -> ChatResult:
        context = WorkflowContext(
            workflow_id=workflow_id or "",
            node_id="chat",
            user_id=user_id,
            account_id="",
        )

        # 1. 输入守卫
        if not await self._input_rule.check_pre({"message": message}, context):
            return ChatResult(status="blocked", message="输入未通过安全校验")

        # 2. 意图解析
        intent = await self._intent_parser.parse(message)
        if intent.action == ActionType.CHAT:
            return ChatResult(status="chat", intent=intent)

        # full_pipeline / follow_up 由路由走 DAG，ChatAgent 只处理单步
        if intent.action in (ActionType.FULL_PIPELINE, ActionType.FOLLOW_UP):
            return ChatResult(
                status="chat",
                intent=intent,
                message="该意图由工作流处理",
            )

        # 3. analyze 单步：搜索 + 三层分析（复用 DAG 逻辑）
        if intent.action == ActionType.ANALYZE_ONLY:
            return await self._run_analyze_standalone(intent, context, workflow_id)

        # 4. 其他单步（search / explore）：走通用 harness
        agent_id = self._ACTION_TO_AGENT.get(intent.action)
        if agent_id is None:
            return ChatResult(
                status="chat",
                intent=intent,
                message="无法识别的意图类型",
            )

        harness = self._registry.build_harness(agent_id, workflow_id=workflow_id)
        if self._llm is not None:
            harness.llm = self._llm

        output = await harness.run(
            {"topic": intent.params.get("topic", message)},
            context,
        )
        return ChatResult(status="agent_output", intent=intent, output=output)

    async def _run_analyze_standalone(
        self,
        intent: ParsedIntent,
        context: WorkflowContext,
        workflow_id: str | None = None,
    ) -> ChatResult:
        """analyze 单步：先搜索再三层分析，复用 DAG 的 analyze_node 逻辑。

        为什么不走通用 prompt harness：
        - 通用 harness 的 prompt_template 只告诉 LLM "请分析主题"，没有搜索数据
        - DAG 管线中 analyze_node 拿到的是 search 节点的真实搜索结果
        - 三层分析（规则层 + LLM粗分析 + LLM深度归因）需要搜索数据才有意义
        - 所以这里复用搜索+分析的完整链路，和 DAG 行为对齐
        """
        topic = str(intent.params.get("topic", "")).strip()
        if not topic:
            return ChatResult(status="chat", intent=intent, message="请提供要分析的主题")

        start_time = time.time()

        try:
            # Step 1: 搜索
            from app.agents.skills.trending_search import TrendingSearchSkill

            search_skill = TrendingSearchSkill()
            search_result = await search_skill.execute({
                "keyword": topic,
                "limit": 20,
                "min_interactions": 10,
                "time_range": "week",
            })
            raw_results = search_result.get("results", [])
            filter_stats = search_result.get("filter_stats", {})

            if not raw_results:
                return ChatResult(
                    status="agent_output",
                    intent=intent,
                    output=AgentOutput(
                        output={
                            "results": [],
                            "patterns": {"_skipped": "no_search_results"},
                            "insights": {"_skipped": "no_search_results"},
                            "filter_stats": filter_stats,
                            "layer1_stats": {"total": 0},
                            "_model_used": "none",
                            "_duration_ms": int((time.time() - start_time) * 1000),
                            "_message": f"主题「{topic}」未搜到足够数据，无法分析",
                        },
                        token_usage=0,
                        duration_ms=int((time.time() - start_time) * 1000),
                        model_used="none",
                    ),
                    message=f"主题「{topic}」未搜到足够数据，无法分析",
                )

            # Step 2: Layer 1 规则层（0 LLM 成本）
            from app.agents.skills.viral_analyzer import analyze_viral

            with_metrics, layer1_stats = analyze_viral(raw_results)

            # Step 3: LLM 分析（Layer 2 + Layer 3）
            from app.agents.harnesses.factory import get_deepseek_llm

            llm = self._llm or get_deepseek_llm(model="deepseek-v3")

            if llm is None:
                output_data = {
                    "results": with_metrics,
                    "patterns": {"_skipped": "no_llm"},
                    "insights": {"_skipped": "no_llm"},
                    "filter_stats": filter_stats,
                    "layer1_stats": layer1_stats,
                    "_model_used": "layer1_only",
                    "_duration_ms": int((time.time() - start_time) * 1000),
                }
                return ChatResult(
                    status="agent_output",
                    intent=intent,
                    output=AgentOutput(
                        output=output_data,
                        token_usage=0,
                        duration_ms=int((time.time() - start_time) * 1000),
                        model_used="layer1_only",
                    ),
                )

            # Layer 2: LLM 粗分析
            from app.agents.skills.analyze_layer import run_layer2, run_layer3

            top5 = with_metrics[:5]
            patterns = await run_layer2(llm, top5, topic)

            # Layer 3: LLM 深度归因
            top2 = with_metrics[:2]
            insights = await run_layer3(llm, top2, with_metrics, patterns, topic)

            model_used = "deepseek-v3 (3-layer)"
            output_data = {
                "results": with_metrics,
                "patterns": patterns,
                "insights": insights,
                "filter_stats": filter_stats,
                "layer1_stats": layer1_stats,
                "_model_used": model_used,
                "_duration_ms": int((time.time() - start_time) * 1000),
            }

            return ChatResult(
                status="agent_output",
                intent=intent,
                output=AgentOutput(
                    output=output_data,
                    token_usage=0,
                    duration_ms=int((time.time() - start_time) * 1000),
                    model_used=model_used,
                ),
            )

        except Exception as e:
            logger.exception(f"[ChatAgent] analyze standalone failed: {e}")
            return ChatResult(
                status="agent_output",
                intent=intent,
                output=AgentOutput(
                    output={
                        "results": [],
                        "patterns": {"_error": str(e)},
                        "insights": {"_error": str(e)},
                        "_model_used": "error_fallback",
                        "_duration_ms": int((time.time() - start_time) * 1000),
                        "_error": str(e),
                    },
                    token_usage=0,
                    duration_ms=int((time.time() - start_time) * 1000),
                    model_used="error_fallback",
                ),
                message=f"分析失败: {e}",
            )