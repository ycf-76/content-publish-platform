"""Progressive Clarification Protocol — 类型定义。

对应 PROGRESSIVE_CLARIFICATION_PROTOCOL.md §3.1。

核心设计：
- Skill 通过 clarify_meta 声明哪些字段需要澄清
- 澄清按字段依赖图分批推送给用户
- 用户回答后编译为 clarification_result，注入 WorkflowState
- 优先级链：clarification_result > model_settings > default_config > 系统默认
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ClarifyWhen(str, Enum):
    missing = "missing"
    ambiguous = "ambiguous"
    always = "always"


class QuestionType(str, Enum):
    single_choice = "single_choice"
    multi_choice = "multi_choice"
    text_input = "text_input"
    slider = "slider"
    image_select = "image_select"


class ClarifyOption(BaseModel):
    label: str
    value: str
    description: str = ""
    preview_url: str = ""


class ClarifyDepends(BaseModel):
    field: str
    value: str


class ClarifyFieldMeta(BaseModel):
    """Skill 声明的单个字段澄清元数据。"""
    hint: str
    when: ClarifyWhen = ClarifyWhen.missing
    options: list[ClarifyOption] = []
    default: str = ""
    depends_on: list[ClarifyDepends] = []
    question_type: QuestionType = QuestionType.single_choice
    placeholder: str = ""
    min_value: float = 0
    max_value: float = 100
    required: bool = True
    auto_default: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClarifyFieldMeta:
        """从 frontmatter YAML dict 构建（容错：字段缺失用默认值）。"""
        when_raw = data.get("when", "missing")
        try:
            when = ClarifyWhen(when_raw)
        except ValueError:
            when = ClarifyWhen.missing

        qt_raw = data.get("question_type", "single_choice")
        try:
            question_type = QuestionType(qt_raw)
        except ValueError:
            question_type = QuestionType.single_choice

        options = []
        for opt in data.get("options", []):
            if isinstance(opt, dict):
                options.append(ClarifyOption(
                    label=str(opt.get("label", "")),
                    value=str(opt.get("value", "")),
                    description=str(opt.get("description", "")),
                    preview_url=str(opt.get("preview_url", opt.get("preview", ""))),
                ))

        depends_on = []
        for dep in data.get("depends_on", []):
            if isinstance(dep, dict):
                depends_on.append(ClarifyDepends(
                    field=str(dep.get("field", "")),
                    value=str(dep.get("value", "")),
                ))

        return cls(
            hint=str(data.get("hint", "")),
            when=when,
            options=options,
            default=str(data.get("default", "")),
            depends_on=depends_on,
            question_type=question_type,
            placeholder=str(data.get("placeholder", "")),
            min_value=float(data.get("min_value", 0)),
            max_value=float(data.get("max_value", 100)),
            required=bool(data.get("required", True)),
            auto_default=bool(data.get("auto_default", False)),
        )


class ClarificationQuestion(BaseModel):
    """发送给前端的具体问题实例。"""
    id: str
    source_skill: str
    question: str
    type: QuestionType = QuestionType.single_choice
    options: list[ClarifyOption] = []
    default: str = ""
    required: bool = True
    depends_on: list[ClarifyDepends] = []
    placeholder: str = ""
    min_value: float = 0
    max_value: float = 100


class ClarificationBatch(BaseModel):
    """一批问题。"""
    batch_id: str
    batch_index: int
    total_batches: int
    title: str
    description: str
    questions: list[ClarificationQuestion]
    next_batch_hint: str = ""
    requires_confirmation: bool = False


class ClarificationAnswer(BaseModel):
    question_id: str
    value: Any = ""


class ClarificationSubmitRequest(BaseModel):
    session_id: str
    batch_id: str
    answers: list[ClarificationAnswer] = []
    user_comment: str = ""
    action: str = "answer"


class ClarificationSubmitResponse(BaseModel):
    status: str
    batch: ClarificationBatch | None = None
    clarification_result: dict | None = None