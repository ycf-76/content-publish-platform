"""Prompt 组装器。

职责：把 persona / mode / user_memory / session context / skill 描述拼成一个
system prompt 字符串。

红线：
- 只做字符串组装，不涉及模型路由，不调用 LLM，不做 I/O。
- 模型路由相关逻辑不放在这里。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptContext:
    """组装 system prompt 所需的全部上下文。"""

    persona: str = ""
    mode: str = "chat"  # chat | agent
    user_memory: dict[str, Any] = field(default_factory=dict)
    session_context: dict[str, Any] = field(default_factory=dict)
    skills: list[dict[str, Any]] = field(default_factory=list)


class PromptAssembler:
    """把 PromptContext 组装成 system prompt。"""

    def assemble(self, ctx: PromptContext) -> str:
        sections: list[str] = []

        if ctx.persona.strip():
            sections.append(ctx.persona.strip())

        mode_hint = self._mode_hint(ctx.mode)
        if mode_hint:
            sections.append(mode_hint)

        memory = self._render_user_memory(ctx.user_memory)
        if memory:
            sections.append(memory)

        session = self._render_session_context(ctx.session_context)
        if session:
            sections.append(session)

        skills = self._render_skills(ctx.skills)
        if skills:
            sections.append(skills)

        return "\n\n".join(sections)

    @staticmethod
    def _mode_hint(mode: str) -> str:
        if mode == "agent":
            return (
                "你是自主 Agent，可以逐步推理并调用可用工具完成任务。"
                "只输出结构化结果或工具调用，不要编造工具输出。"
            )
        return "你是乐于助人的助手。"

    @staticmethod
    def _render_user_memory(memory: dict[str, Any]) -> str:
        if not memory:
            return ""
        lines = ["[用户记忆]"]
        for key, value in memory.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)

    @staticmethod
    def _render_session_context(session: dict[str, Any]) -> str:
        if not session:
            return ""
        return "[会话上下文]\n" + json.dumps(session, ensure_ascii=False, default=str)

    @staticmethod
    def _render_skills(skills: list[dict[str, Any]]) -> str:
        if not skills:
            return ""
        lines = ["[可用工具]"]
        for skill in skills:
            name = skill.get("name", "")
            description = skill.get("description", "")
            lines.append(f"- {name}: {description}" if description else f"- {name}")
        return "\n".join(lines)
