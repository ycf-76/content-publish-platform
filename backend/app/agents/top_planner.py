"""TopPlanner: 数据结构 + LLM 不可用时的正则 fallback。

ReAct 模式下不再需要 LLM 规划层——LoopExecutor 里的 LLM 自己选工具、自己执行、自己观察。
这个文件只保留：
  1. 数据结构（ToolName, ToolCall, TopPlan, ActionType, ParsedIntent）—— 向后兼容
  2. _keyword_fallback —— LLM 完全不可用时的正则兜底
  3. plan_to_action_type / plan_to_parsed_intent —— 向后兼容映射
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


logger = logging.getLogger(__name__)


class ToolName(str, Enum):
    TRENDING_SEARCH = "trending_search"
    ANALYZE = "analyze"
    COPYWRITE = "copywrite"
    COVER_DESIGN = "cover_design"
    IMAGE_GEN = "image_gen"
    CONTENT_AUDIT = "content_audit"
    CARD_GEN = "card_gen"
    WECHAT_PUSH = "wechat_push"
    FEISHU_PUSH = "feishu_push"
    TAG_GENERATION = "tag_generation"


TOOL_DESCRIPTIONS = {
    ToolName.TRENDING_SEARCH: "搜索小红书/抖音/微博的热门话题和爆款内容",
    ToolName.ANALYZE: "分析已有内容的爆款要素、数据趋势，或分析搜索结果中的规律",
    ToolName.COPYWRITE: "创作新的小红书文案/笔记——从零开始写一篇新内容",
    ToolName.COVER_DESIGN: "为已有文案设计封面图",
    ToolName.IMAGE_GEN: "为已有文案生成配图/插图",
    ToolName.CONTENT_AUDIT: "审核已有文案是否合规",
    ToolName.CARD_GEN: "把已有文案排版成小红书卡片",
    ToolName.WECHAT_PUSH: "把已有文案发送到微信对话",
    ToolName.FEISHU_PUSH: "把已有文案发送到飞书群",
    ToolName.TAG_GENERATION: "为已有文案生成标签",
}


@dataclass
class ToolCall:
    tool: ToolName
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class TopPlan:
    intent_summary: str = ""
    topic: str = ""
    confidence: float = 0.0
    is_chat: bool = False
    direct_answer: str = ""
    intent: str = "other"
    context_used: str = ""
    tools: list[ToolCall] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    strategy: str = "sequential"
    rollback: dict[str, str] = field(default_factory=dict)
    optional_tools: list[ToolName] = field(default_factory=list)

    @property
    def needs_tools(self) -> bool:
        return not self.is_chat


class ActionType(str, Enum):
    FULL_PIPELINE = "full_pipeline"
    SEARCH_ONLY = "search_only"
    ANALYZE_ONLY = "analyze_only"
    COVER_DESIGN = "cover_design"
    COPYWRITE_ONLY = "copywrite_only"
    TAG_GENERATION = "tag_generation"
    REFINE = "refine"
    FOLLOW_UP = "follow_up"
    EXPLORE = "explore"
    CHAT = "chat"
    CARD_AND_PUSH = "card_and_push"


def plan_to_action_type(plan: TopPlan) -> ActionType:
    if plan.is_chat or not plan.tools:
        return ActionType.CHAT
    tool_names = {tc.tool for tc in plan.tools}
    has_search = ToolName.TRENDING_SEARCH in tool_names
    has_analyze = ToolName.ANALYZE in tool_names
    has_copywrite = ToolName.COPYWRITE in tool_names
    has_image = ToolName.IMAGE_GEN in tool_names or ToolName.COVER_DESIGN in tool_names
    has_wechat = ToolName.WECHAT_PUSH in tool_names
    has_feishu = ToolName.FEISHU_PUSH in tool_names
    if has_wechat and (has_copywrite or has_search):
        return ActionType.CARD_AND_PUSH
    if has_feishu and (has_copywrite or has_search):
        return ActionType.CARD_AND_PUSH
    if has_search and has_analyze and has_copywrite:
        return ActionType.FULL_PIPELINE
    if has_search and not has_analyze and not has_copywrite:
        return ActionType.SEARCH_ONLY
    if has_analyze and not has_copywrite and not has_search:
        return ActionType.ANALYZE_ONLY
    if ToolName.COVER_DESIGN in tool_names and not has_copywrite and not has_search:
        return ActionType.COVER_DESIGN
    if has_copywrite and has_image and not has_search and not has_wechat:
        return ActionType.FULL_PIPELINE
    if has_copywrite and not has_search and not has_wechat:
        return ActionType.COPYWRITE_ONLY
    if ToolName.TAG_GENERATION in tool_names and len(tool_names) == 1:
        return ActionType.TAG_GENERATION
    if has_search and has_copywrite:
        return ActionType.FULL_PIPELINE
    return ActionType.FULL_PIPELINE


@dataclass
class ParsedIntent:
    tools: list[ToolCall] = field(default_factory=list)
    topic: str = ""
    confidence: float = 0.0
    is_chat: bool = False
    direct_answer: str = ""


def plan_to_parsed_intent(plan: TopPlan) -> ParsedIntent:
    return ParsedIntent(
        tools=plan.tools,
        topic=plan.topic,
        confidence=plan.confidence,
        is_chat=plan.is_chat,
        direct_answer=plan.direct_answer,
    )


_SEND_LATEST_ONLY_RE = re.compile(
    r"^(?:请|麻烦)?(?:把|将)?(?:刚才|刚|最近|上次)?"
    r"(?:写好的|写完的|写的|写出来|刚生成的|生成的|做完的|完成的)?"
    r"(?:那篇|这篇)?"
    r"(?:文案|内容|报告|稿子|文章|作品|笔记)?"
    r"(?:发(?:送)?(?:给)?我(?:微信)?|推送给我|推给我|发到(?:我)?微信)"
    r"[。.！!？?]?$"
)


def _keyword_fallback(message: str, context: dict[str, Any] | None = None) -> TopPlan:
    """LLM 完全不可用时的正则兜底。"""
    tools: list[ToolCall] = []
    topic = message
    last_topic = (context or {}).get("last_topic", "")

    if _SEND_LATEST_ONLY_RE.search(message):
        recent_copywrites = ((context or {}).get("user_memory") or {}).get(
            "recent_copywrites"
        ) or []
        if recent_copywrites and recent_copywrites[0].get("title"):
            topic = str(recent_copywrites[0].get("title", ""))
        elif last_topic:
            topic = last_topic
        return TopPlan(
            tools=[ToolCall(tool=ToolName.WECHAT_PUSH)],
            topic=topic,
            confidence=0.8,
            intent="publish",
            steps=["推送最近文案到微信"],
            context_used="fallback: 发给我",
        )

    if re.search(r"搜|搜索|查|查找|找一下", message) and re.search(r"热点|爆款|趋势|新闻|资讯", message):
        tools.append(ToolCall(tool=ToolName.TRENDING_SEARCH))
        m = re.search(r"(?:穿搭|美食|旅行|健身|护肤|数码|科技|AI)", message)
        topic = m.group(0) if m else "今日热点"

    if re.search(r"(?:分析|拆解).{0,10}?(?:这篇|这个|作品|热点|爆款|数据|文案|笔记|内容)", message):
        tools.append(ToolCall(tool=ToolName.ANALYZE))

    _full_create_pattern = r"(做|来|要|给).*?一期|做一篇|来一篇"
    if re.search(_full_create_pattern, message):
        return TopPlan(
            tools=[
                ToolCall(tool=ToolName.TRENDING_SEARCH),
                ToolCall(tool=ToolName.ANALYZE),
                ToolCall(tool=ToolName.COPYWRITE),
                ToolCall(tool=ToolName.IMAGE_GEN),
                ToolCall(tool=ToolName.CONTENT_AUDIT),
            ],
            topic=message, confidence=0.7,
            intent="full_create",
            steps=["搜索热点", "爆款分析", "撰写文案", "生成图片", "审核"],
            strategy="sequential",
            optional_tools=[ToolName.IMAGE_GEN, ToolName.CONTENT_AUDIT],
            rollback={"analyze": "trending_search"},
            context_used="fallback: 做一期/做一篇",
        )

    if re.search(r"封面", message) and re.search(r"做|设计|生成", message):
        tools.append(ToolCall(tool=ToolName.COVER_DESIGN))

    if re.search(r"写|撰写|生成|创作", message) and re.search(r"文案|笔记|报告|内容|文章|一篇|篇", message):
        tools.append(ToolCall(tool=ToolName.COPYWRITE))

    if re.search(r"发.*微信|推.*微信|送.*微信", message):
        tools.append(ToolCall(tool=ToolName.WECHAT_PUSH))

    if re.search(r"卡片", message):
        tools.append(ToolCall(tool=ToolName.CARD_GEN))

    if re.search(r"图文|配图|图片呢", message) and not tools:
        tools.extend([ToolCall(tool=ToolName.COPYWRITE), ToolCall(tool=ToolName.IMAGE_GEN)])

    if re.search(r"标签", message):
        tools.append(ToolCall(tool=ToolName.TAG_GENERATION))

    if not tools:
        if any(kw in message for kw in ["图文", "配图", "图片呢"]):
            return TopPlan(
                tools=[ToolCall(tool=ToolName.COPYWRITE), ToolCall(tool=ToolName.IMAGE_GEN)],
                topic=last_topic or message, confidence=0.8,
                intent="image",
                steps=["生成文案", "规划图片", "生成图片"],
                optional_tools=[ToolName.IMAGE_GEN],
                context_used=f"fallback: 图文/配图, last_topic={last_topic}",
            )
        if any(kw in message for kw in ["帮我发", "发一下"]):
            return TopPlan(
                tools=[ToolCall(tool=ToolName.WECHAT_PUSH)],
                topic=last_topic or message, confidence=0.8,
                intent="publish",
                steps=["推送到微信"],
                context_used=f"fallback: 发/发布, last_topic={last_topic}",
            )
        return TopPlan(is_chat=True, topic=message, confidence=0.5, intent="chat", direct_answer="")

    return TopPlan(
        tools=tools,
        topic=topic,
        confidence=0.7,
        intent="other",
        steps=[],
        strategy="sequential",
        context_used="fallback: 关键词匹配",
    )