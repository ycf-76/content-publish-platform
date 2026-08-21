"""审核 Skill 集合：对文案做合规性 / 平台规则 / 内容质量 / 品牌安全审核。

可插拔架构（v2）：
- AuditSkillBase：基类，封装 LLM 审核 + JSON 解析 + 降级
- 1 个内置 Skill 子类：StandardAuditSkill（默认四维度审核）
- 第三方可在 backend/skills/ 下新增自己的 AuditSkillBase 子类并 @register

红线：
- LLM 不可用时自动通过（不阻塞工作流）
- 输出 JSON 解析失败时自动通过
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.tools.base import Skill
from app.tools.registry import register

logger = logging.getLogger(__name__)

# prompts 目录（与 graph.py 的 _PROMPTS_DIR 保持一致）
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_audit_prompt() -> str:
    """加载审核 prompt 模板。文件不存在时返回空串。"""
    p = _PROMPTS_DIR / "audit.md"
    if not p.exists():
        logger.warning(f"audit prompt file not found: {p}")
        return ""
    return p.read_text(encoding="utf-8")


class AuditSkillBase(Skill):
    """审核 Skill 基类。

    子类可覆盖：
    - build_prompt(): 自定义审核 prompt 构造
    - parse_response(): 自定义 LLM 输出解析
    - fallback(): 自定义降级行为（默认自动通过）

    默认实现使用 app/agents/prompts/audit.md 作为模板，四维度审核。
    """

    node_type = "audit"
    name: str = ""
    display_name: str = ""
    description: str = ""

    async def execute(self, inputs: dict[str, Any]) -> dict[str, Any]:
        """执行审核。

        inputs 约定：
        - llm: LLMProtocol 实例（None 时自动通过）
        - topic: 工作流主题
        - copywrite: copywrite 节点的输出（含 title/content/tags）
        """
        llm = inputs.get("llm")
        topic = inputs.get("topic", "")
        copywrite = inputs.get("copywrite", {}) or {}

        if llm is None:
            logger.warning(
                f"[{self.__class__.__name__}] LLM unavailable, auto-pass"
            )
            return self.fallback("llm_unavailable")

        prompt_template = _load_audit_prompt()
        if not prompt_template:
            logger.warning(
                f"[{self.__class__.__name__}] audit prompt empty, auto-pass"
            )
            return self.fallback("no_prompt")

        prompt = self.build_prompt(topic, copywrite, prompt_template)

        try:
            resp = await llm.chat(
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
            raw = (resp.get("content") or "").strip()
            result = self.parse_response(raw)
            if result is None:
                logger.warning(
                    f"[{self.__class__.__name__}] LLM JSON parse failed, auto-pass"
                )
                return self.fallback("parse_failed")
            return result
        except Exception as e:
            logger.exception(f"[{self.__class__.__name__}] LLM call failed: {e}")
            return self.fallback("llm_error", error=str(e))

    def build_prompt(
        self,
        topic: str,
        copywrite: dict,
        template: str,
    ) -> str:
        """构造审核 prompt。子类可覆盖。"""
        copywrite_summary = json.dumps({
            "title": copywrite.get("title", ""),
            "content": copywrite.get("content", ""),
            "tags": copywrite.get("tags", []),
        }, ensure_ascii=False)
        try:
            return template.format(topic=topic, copywrite=copywrite_summary)
        except (KeyError, IndexError):
            return template

    def parse_response(self, raw: str) -> dict | None:
        """解析 LLM 输出的 JSON（容忍 markdown fence）。"""
        if not raw:
            return None
        content = raw.strip()
        # 去 markdown fence
        if content.startswith("```"):
            lines = content.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return None

        return {
            "passed": bool(parsed.get("passed", True)),
            "issues": list(parsed.get("issues", [])),
            "suggestions": list(parsed.get("suggestions", [])),
            "audit_method": "llm",
            "_skill": self.name,
        }

    def fallback(self, reason: str, error: str = "") -> dict:
        """降级：自动通过。子类可覆盖以实现更严格的降级行为。"""
        return {
            "passed": True,
            "issues": [],
            "suggestions": [],
            "audit_method": reason,
            "_error": error,
            "_skill": self.name,
        }


@register
class StandardAuditSkill(AuditSkillBase):
    """默认四维度审核 Skill。"""

    name = "standard"
    display_name = "标准四维度审核"
    description = "合规性 + 平台规则 + 内容质量 + 品牌安全四维度审核"
