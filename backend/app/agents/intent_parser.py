"""意图解析器（理解层）。

从自然语言提取结构化意图（action + params + confidence）。
红线：这是「理解」，不是「守卫」。输入校验由 `ChatInputRule` 负责。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ActionType(str, Enum):
    FULL_PIPELINE = "full_pipeline"
    SEARCH_ONLY = "search_only"
    ANALYZE_ONLY = "analyze_only"
    FOLLOW_UP = "follow_up"
    EXPLORE = "explore"
    CHAT = "chat"


@dataclass
class ParsedIntent:
    action: ActionType
    params: dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    needs_confirmation: bool = False
    confirmation_prompt: str = ""


_INTENT_RULES = [
    # full_pipeline 优先级最高
    {
        "patterns": [
            r"写.*(?:文章|笔记|内容|帖子)",
            r"发布.*(?:小红书|笔记)",
            r"帮我(?:做|写|生成|创作)",
            r"来一篇",
            r"制作.*(?:内容|笔记)",
        ],
        "action": ActionType.FULL_PIPELINE,
        "confidence": 0.85,
    },
    {
        "patterns": [r"调研", r"研究一下", r"探索", r"竞品分析", r"摸清"],
        "action": ActionType.EXPLORE,
        "confidence": 0.75,
    },
    {
        "patterns": [r"搜(?:索|一下)", r"找.*(?:热点|爆款)"],
        "action": ActionType.SEARCH_ONLY,
        "confidence": 0.8,
    },
    {
        "patterns": [r"分析(?:一下)", r"拆解"],
        "action": ActionType.ANALYZE_ONLY,
        "confidence": 0.8,
    },
    {
        "patterns": [r"换个(?:风格|主题|方向)", r"重新(?:生成|来|写)", r"继续"],
        "action": ActionType.FOLLOW_UP,
        "confidence": 0.75,
    },
]


class RuleBasedIntentParser:
    """规则版意图解析器（Phase 2 可升级为 LLM 解析）。"""

    async def parse(self, message: str) -> ParsedIntent:
        if not message or not message.strip():
            return ParsedIntent(action=ActionType.CHAT, confidence=0.5)

        for rule in _INTENT_RULES:
            for pattern in rule["patterns"]:
                if re.search(pattern, message):
                    params = self._extract_params(message, rule["action"])
                    confidence = rule["confidence"]
                    needs_confirmation = confidence < 0.7
                    return ParsedIntent(
                        action=rule["action"],
                        params=params,
                        confidence=confidence,
                        needs_confirmation=needs_confirmation,
                        confirmation_prompt=(
                            "确认：要执行完整发布流程吗？" if needs_confirmation else ""
                        ),
                    )

        return ParsedIntent(action=ActionType.CHAT, confidence=0.6)

    @staticmethod
    def _extract_params(message: str, action: ActionType) -> dict[str, Any]:
        if action == ActionType.SEARCH_ONLY:
            topic = re.sub(r"^(搜(?:索|一下)|找)", "", message).strip()
            topic = re.sub(r"(?:的)?(?:热点|爆款)$", "", topic).strip()
            return {"topic": topic or message}

        if action == ActionType.ANALYZE_ONLY:
            topic = re.sub(r"^(分析(?:一下)|拆解)", "", message).strip()
            return {"topic": topic or message}

        if action == ActionType.FOLLOW_UP:
            return {"modifier": message.strip()}

        if action == ActionType.EXPLORE:
            topic = re.sub(
                r"^(调研(?:一下)?|研究一下|探索(?:一下)?|竞品分析|摸清)",
                "", message
            ).strip()
            return {"topic": topic or message}

        patterns = [
            r"(?:关于|有关)(.+?)(?:的|文章|笔记|内容|帖子)",
            r"写(?:一篇|个)?(.+?)(?:的|文章|笔记|内容|帖子|$)",
            r"帮我(?:写|做|生成|创作)(?:一篇|个)?(.+?)(?:的|文章|笔记|内容|帖子|$)",
        ]
        for pattern in patterns:
            m = re.search(pattern, message)
            if m:
                topic = m.group(1).strip()
                if topic:
                    return {"topic": topic}

        cleaned = re.sub(
            r"^(帮我|请|能不能|可以|写|发布|制作|来一篇)", "", message
        ).strip()
        return {"topic": cleaned or message}
