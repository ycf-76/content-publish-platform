"""Agent Harness 工厂。

负责把 LLM 适配器 + Skill 集合 + Executor + Observer 装配成 AgentHarness
实例，供 graph.py 的节点调用。

红线：
- 不 import langgraph / fastapi。
- LLM 不可用时返回 None（节点会走兜底），不抛异常。
- Skill 实例化失败不影响其他 Skill。
- 每次 build 都返回新 harness 实例（避免跨 workflow 共享 memory）。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from app.engine.harness.executor.loop import LoopExecutor
from app.engine.harness.memory.memory import AgentMemory
from app.engine.harness.observer.observer import Observer
from app.engine.harness.runtime import AgentHarness
from app.tools.base import Skill

if TYPE_CHECKING:
    from app.adapters.llm_base import BaseLLM

logger = logging.getLogger(__name__)


# ----------------------------------------------------------------------
# 测试模式：Mock LLM（不连真实 API、不消耗 token）
# ----------------------------------------------------------------------
# 当用户在右侧配置选择 model 以 "mock-" 开头时启用，用于工作流链路联调。
# 返回按节点类型匹配的固定响应，让 search/analyze/copywrite/audit 全流程可跑通。


_MOCK_LLM_RESPONSES: dict[str, dict[str, Any]] = {
    "search": {
        "content": '{"final": true, "output": {"results": [{"note_id": "mock_1", "title": "mock 笔记", "likes": 1000}], "count": 1, "summary": "mock search result"}}',
        "reasoning_content": "搜索关键词已生成，准备调用 xhs_search 工具",
        "token_usage": 120,
    },
    "analyze": {
        "content": '{"factors": {"color": "暖色调", "composition": "俯拍", "topic": "手冲咖啡"}, "patterns": {"title_patterns": [{"type": "数字型", "template": "N个技巧"}], "content_structures": [{"structure": "总分总"}], "emotion_triggers": [{"emotion": "好奇"}]}, "insights": {"trend_signals": {"is_topic_trend": true, "trend_strength": "medium", "trend_basis": "mock 趋势依据"}, "recommendations": [{"direction": "mock 方向", "reason": "mock 理由"}]}}',
        "reasoning_content": "分析爆款因子：颜色 + 构图 + 主题",
        "token_usage": 200,
    },
    "copywrite": {
        "content": '{"title": "今日分享 | 3个让你效率翻倍的小技巧", "content": "这是 mock 文案内容，用于测试工作流链路。\\n\\n1. 第一个技巧\\n2. 第二个技巧\\n3. 第三个技巧", "tags": ["#mock", "#测试", "#效率"]}',
        "reasoning_content": "思考标题吸引力，构造文案结构，挑选标签",
        "token_usage": 350,
    },
    "audit": {
        "content": '{"passed": true, "issues": [], "suggestions": ["mock 审核建议"]}',
        "reasoning_content": "审核：无敏感词，无违规内容",
        "token_usage": 80,
    },
    "publish": {
        "content": '{"final": true, "output": {"post_id": "mock_post_001", "status": "published", "message": "发布成功"}}',
        "reasoning_content": "调用 xhs_publish 工具完成发布",
        "token_usage": 50,
    },
    "default": {
        "content": '{"result": "mock", "status": "ok"}',
        "reasoning_content": None,
        "token_usage": 100,
    },
}


class _MockLLM:
    """测试模式 LLM 适配器，返回固定响应，不连真实 API。

    实现 BaseLLM 接口（chat / stream_chat / model_name），
    根据调用方传入的 messages 内容匹配节点类型返回对应 mock 响应。
    """

    def __init__(self, model: str = "mock-llm") -> None:
        self.model = model

    @property
    def model_name(self) -> str:
        return self.model

    def _pick_response(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        text = ""
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                text += content + "\n"
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        text += str(item.get("text", "")) + "\n"
        text_lower = text.lower()
        for keyword in ("search", "analyze", "copywrite", "audit", "publish"):
            if keyword in text_lower:
                resp = _MOCK_LLM_RESPONSES[keyword]
                break
        else:
            resp = _MOCK_LLM_RESPONSES["default"]
        # R1/reasoner 模式保留 reasoning_content，否则置 None
        if "r1" in self.model.lower() or "reasoner" in self.model.lower():
            return dict(resp)
        return {**resp, "reasoning_content": None}

    async def _chat_impl(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._pick_response(messages)

    async def _stream_chat_impl(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        resp = self._pick_response(messages)
        if resp.get("reasoning_content"):
            yield {"content": None, "reasoning_content": resp["reasoning_content"], "is_final": False, "token_usage": None}
        yield {"content": resp["content"], "reasoning_content": None, "is_final": False, "token_usage": None}
        yield {"content": None, "reasoning_content": None, "is_final": True, "token_usage": resp["token_usage"]}


# ----------------------------------------------------------------------
# LLM 适配器懒加载
# ----------------------------------------------------------------------


_llm_cache: dict[str, BaseLLM] = {}


def get_deepseek_llm(
    temperature: float | None = None,
    model: str | None = None,
) -> BaseLLM | None:
    """获取 DeepSeek 适配器（按温度+模型缓存）。

    Args:
        temperature: 用户在右侧工作区调节的温度（0.0-1.0）。None 时使用默认 0.7。
        model: 模型名（如 "deepseek-chat"）。None 时使用配置默认值。

    不同 temperature/model 组合会生成不同实例，缓存键按 "deepseek|{temp}|{model}" 区分，
    避免覆盖系统默认实例。

    无 API key 返回 None。
    """
    temp_val = 0.7 if temperature is None else float(max(0.0, min(1.0, temperature)))
    model_val = model or ""  # 空字符串占位，下面会用 settings 默认值替换
    cache_key = f"deepseek|{temp_val:.3f}|{model_val}"
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    # 测试模式：model 以 "mock-" 开头时返回 _MockLLM，不连真实 API、不消耗 token
    # 用于工作流链路联调（搜索→分析→文案→审核→发布全流程），仅消耗本地计算
    if model_val.startswith("mock-"):
        adapter = _MockLLM(model=model_val)
        _llm_cache[cache_key] = adapter
        logger.info(f"[mock-mode] LLM 使用 _MockLLM (model={model_val})，不消耗 token")
        return adapter

    # 收敛：具体 adapter 由 ModelRouter 解析（含 api_key 校验与降级）
    normalized = _normalize_deepseek_model(model_val) if model_val else None
    from app.core.sandbox.model_router import get_model_router

    llm = get_model_router().resolve_llm(model=normalized, temperature=temp_val)
    if llm is not None:
        _llm_cache[cache_key] = llm
    return llm


def _normalize_deepseek_model(name: str) -> str:
    """把前端展示名映射成 DeepSeek API 的 model id。

    前端下拉框展示中文/英文别名，后端需要真实 model id。
    未知值原样返回（让 API 自己报错，便于排查）。
    """
    mapping = {
        "deepseek-v3": "deepseek-chat",
        "deepseek chat": "deepseek-chat",
        "gpt-4o": "deepseek-chat",  # 兜底：用户选了 GPT-4o 但后端只配了 DeepSeek
        "claude 3.5 sonnet": "deepseek-chat",
        "通义千问 max": "deepseek-chat",
        "deepseek-r1": "deepseek-reasoner",
        "deepseek reasoner": "deepseek-reasoner",
        "deepseek-reasoner": "deepseek-reasoner",
    }
    return mapping.get(name.strip().lower(), name)


# ----------------------------------------------------------------------
# Observer 工厂
# ----------------------------------------------------------------------


def _make_observer(workflow_id: str) -> Observer:
    """构造把 trace 事件转 SSE 的 Observer。"""
    from app.services.sse_bus import sse_bus

    async def _emit(node_id: str, event_type: str, payload: dict[str, Any]) -> None:
        await sse_bus.publish(
            workflow_id,
            event_type,
            {"node_id": node_id, **payload},
        )

    return Observer(emit_callback=_emit)


# ----------------------------------------------------------------------
# Recovery 装配
# ----------------------------------------------------------------------


def _make_recovery_loop(
    workflow_id: str,
    strategies: list[Any] | None = None,
    max_attempts: int = 3,
) -> Any:
    """构造 RecoveryLoop 并注入 Observer。

    策略默认配置：
    - search 节点：retry → broaden_keyword（搜索失败先重试，再拓宽关键词）
    - publish 节点：retry → refresh_token（发布失败先重试，再刷新 Token）
    - 其他节点：retry（简单重试）

    红线：
    - max_attempts 上限硬编码（红线 4.1）
    - 重试策略硬编码（不让 LLM 决策，红线 4.1）
    - 技术性恢复自动执行（红线 4.1）
    """
    from app.engine.harness.recovery import (
        BackoffPolicy,
        CircuitBreaker,
        RecoveryLoop,
    )

    observer = _make_observer(workflow_id)
    return RecoveryLoop(
        max_attempts=max_attempts,
        strategies=strategies,
        backoff=BackoffPolicy(base_delay=1.0, max_delay=10.0),
        circuit_breaker=CircuitBreaker(failure_threshold=5, recovery_timeout=60.0),
        observer=observer,
    )


def _make_search_recovery(workflow_id: str) -> Any:
    """search 节点的 recovery 策略：retry → broaden_keyword。"""
    from app.engine.harness.recovery import (
        BroadenKeywordStrategy,
        RetryStrategy,
    )

    return _make_recovery_loop(
        workflow_id,
        strategies=[RetryStrategy(), BroadenKeywordStrategy()],
        max_attempts=2,
    )


def _make_publish_recovery(workflow_id: str) -> Any:
    """publish 节点的 recovery 策略：retry → refresh_token。"""
    from app.engine.harness.recovery import (
        RefreshTokenStrategy,
        RetryStrategy,
    )

    return _make_recovery_loop(
        workflow_id,
        strategies=[RetryStrategy(), RefreshTokenStrategy()],
        max_attempts=2,
    )


# ----------------------------------------------------------------------
# 各节点 Harness 装配
# ----------------------------------------------------------------------


def build_search_harness(workflow_id: str) -> AgentHarness:
    """search 节点：LoopExecutor + TrendingSearchSkill + Bash/Glob/Grep 工具。

    多平台版本：通过 SourceManager 从 Reddit/HackerNews/小红书 等平台搜热门内容。
    LLM 没配也允许跑（LoopExecutor 会立刻走 final 兜底，但 Skills 还能
    被 SingleShot 调用——这里我们走 Loop，没 LLM 时基本就是空跑）。
    """
    from app.tools.dev_tools import BashSkill, GlobSkill, GrepSkill
    from app.tools.trending_search import TrendingSearchSkill

    skills: list[Skill] = []
    skills.append(TrendingSearchSkill())
    skills.append(GlobSkill())
    skills.append(GrepSkill())
    skills.append(BashSkill())  # 默认权限门控会拒绝，需 env PERMISSIONS_ALLOW=bash:exec

    return AgentHarness(
        agent_id="search",
        role="trending_search_agent",
        llm=get_deepseek_llm(),
        skills=skills,
        memory=AgentMemory(),
        prompt_template=_SEARCH_PROMPT,
        observer=_make_observer(workflow_id),
        executor=LoopExecutor(max_iterations=4),
        recovery_loop=_make_search_recovery(workflow_id),
    )


def build_publish_harness(workflow_id: str) -> AgentHarness:
    """publish 节点：LoopExecutor + XhsPublishSkill。

    发布虽是确定性动作，但走 Loop 让 LLM 拿到 tool 失败原因后能回报清晰状态。
    publish 权限高危，必须 env PERMISSIONS_ALLOW=xhs:publish 才会真正调用。
    """
    from app.tools.xhs_publish import XhsPublishSkill

    skills: list[Skill] = [XhsPublishSkill()]

    return AgentHarness(
        agent_id="publish",
        role="xhs_publish_agent",
        llm=get_deepseek_llm(),
        skills=skills,
        memory=AgentMemory(),
        prompt_template=_PUBLISH_PROMPT,
        observer=_make_observer(workflow_id),
        executor=LoopExecutor(max_iterations=2),
        recovery_loop=_make_publish_recovery(workflow_id),
    )


# ----------------------------------------------------------------------
# Prompts
# ----------------------------------------------------------------------


_SEARCH_PROMPT = (
    "你需要为以下主题搜出【热门和趋势话题】相关的有参考价值的爆款内容：\n"
    "主题：{topic}\n"
    "账号：{account_id}\n"
    "\n"
    "策略：\n"
    "1. 调用 trending_search 工具搜索，keyword 参数必须填上面的真实主题文字（不要写 {{topic}} 占位符），\n"
    "   limit=20，min_interactions=10（过滤低互动内容），time_range=week（最近一周热门）。\n"
    "   platform 参数留空（用默认平台），或指定 'reddit' / 'hackernews'。\n"
    "2. 工具会自动过滤低互动内容并按互动量（likes+comments+shares）降序排序，直接使用返回的 results。\n"
    "3. 如果结果为空或不够，可用 grep/glob 工具查本地参考资料补充。\n"
    "4. 拿到结果后，输出 JSON：\n"
    '   {{"final": true, "output": {{"results": [...], "count": N, "summary": "...", "platform": "..."}}}}\n'
    "\n"
    "重要：output.results 必须完整保留 trending_search 工具返回的每条内容的所有字段，\n"
    "包括 platform、content_id、title、summary、content、author、url、likes、comments、shares、cover_img、published_at、tags，\n"
    "直接原样复制工具返回的结果列表，不要精简或丢弃任何字段。\n"
)


_PUBLISH_PROMPT = (
    "请将以下内容发布到小红书：\n"
    "标题：{title}\n"
    "正文：{content}\n"
    "图片数：{image_count}\n"
    "账号：{account_id}\n"
    "\n"
    "调用 xhs_publish 工具完成发布，把工具返回的 post_id/status/message 原样回传。\n"
)


__all__ = [
    "build_search_harness",
    "build_publish_harness",
    "get_deepseek_llm",
]
