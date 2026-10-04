"""用户画像（D18 创作者画像）API Schema。

对应《技术架构设计文档》8.1.1 节 + PRD D18 决策。
红线（《开发红线手册》7.4）：
- primary_domain 必填
- 只存创作偏好，不存敏感个人信息（年龄/性别/真实姓名/联系方式）
- 画像作为 WorkflowState 一部分全流程注入
- 禁止提前实现 D19 经验库 / D20 流量分级
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

# 枚举直接复用 ORM 层定义（单一事实来源，避免两处漂移）
from app.db.models import CreatorTone, PrimaryDomain, VisualStyle

# 枚举值 → 中文标签（prompt 注入用）
_DOMAIN_LABELS: dict[str, str] = {
    "tech": "科技",
    "beauty": "美妆",
    "food": "美食",
    "travel": "旅行",
    "education": "教育",
    "parenting": "母婴",
    "fitness": "健身",
    "finance": "财经",
    "other": "其他",
}

_TONE_LABELS: dict[str, str] = {
    "professional": "专业",
    "friendly": "亲和",
    "lively": "活泼",
    "serious": "严肃",
    "humorous": "幽默",
}

_VISUAL_LABELS: dict[str, str] = {
    "warm": "暖色调",
    "cool": "冷色调",
    "minimal": "极简",
    "rich": "丰富",
}


class UserProfile(BaseModel):
    """创作者画像，D18 决策。MVP 核心 5 项。

    该模型是画像在各层流转的统一载体：
    - ProfileService 读 DB 后转换为本模型
    - model_dump() 注入 WorkflowState.user_profile
    - to_prompt_context() 供文案 Agent prompt 注入
    """

    primary_domain: PrimaryDomain  # 主领域（必填）
    sub_domain: str | None = None  # 子领域（可选，如 科技→AI编程）
    tone: CreatorTone = CreatorTone.PROFESSIONAL  # 调性
    visual_style: VisualStyle = VisualStyle.WARM  # 视觉风格
    taboo_topics: list[str] = Field(default_factory=list)  # 不碰的话题
    taboo_words: list[str] = Field(default_factory=list)  # 不用的词
    identity: str | None = None  # 身份定位（一句话描述核心定位）
    differentiation: str | None = None  # 差异化（跟同类账号比的独特之处）
    content_direction: str | None = None  # 内容方向（主要做什么类型的内容）
    target_audience: str | None = None  # 核心人群（年龄段/职业/特征）
    audience_pain_points: str | None = None  # 受众痛点（什么场景会搜索/刷到我的内容）
    opening_style: str | None = None  # 开头结构（提问式/冲突式/故事式/直入主题）
    content_rhythm: str | None = None  # 内容节奏（短平快/中等/深度长内容/图文为主）
    signature_elements: str | None = None  # 标志性元素（口头禅/固定栏目/BGM等辨识度元素）

    @field_validator("sub_domain")
    @classmethod
    def _clean_sub_domain(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            return None
        return cleaned[:50]

    def to_prompt_context(self) -> str:
        """序列化为 prompt 可读的文本块。

        供文案 Agent（全量注入）等场景使用。禁忌清单为空时对应行消失，
        避免 prompt 膨胀。
        """
        domain = self.primary_domain.value if isinstance(self.primary_domain, PrimaryDomain) else str(self.primary_domain)
        domain_label = _DOMAIN_LABELS.get(domain, domain)
        tone_val = self.tone.value if isinstance(self.tone, CreatorTone) else str(self.tone)
        visual_val = self.visual_style.value if isinstance(self.visual_style, VisualStyle) else str(self.visual_style)

        lines = [
            "【创作者画像】",
            f"主领域: {domain_label}"
            + (f" ({self.sub_domain})" if self.sub_domain else ""),
            f"调性: {_TONE_LABELS.get(tone_val, tone_val)}",
            f"视觉风格: {_VISUAL_LABELS.get(visual_val, visual_val)}",
        ]
        if self.identity:
            lines.append(f"身份定位: {self.identity}")
        if self.differentiation:
            lines.append(f"差异化: {self.differentiation}")
        if self.content_direction:
            lines.append(f"内容方向: {self.content_direction}")
        if self.target_audience:
            lines.append(f"核心受众: {self.target_audience}")
        if self.audience_pain_points:
            lines.append(f"受众痛点: {self.audience_pain_points}")
        if self.opening_style:
            lines.append(f"开头结构: {self.opening_style}")
        if self.content_rhythm:
            lines.append(f"内容节奏: {self.content_rhythm}")
        if self.signature_elements:
            lines.append(f"标志元素: {self.signature_elements}")
        if self.taboo_topics:
            lines.append(f"禁忌话题: {', '.join(self.taboo_topics)}")
        if self.taboo_words:
            lines.append(f"禁忌用词: {', '.join(self.taboo_words)}")
        lines.append("写作要求：调性必须符合上述画像；严禁出现禁忌用词；不涉及禁忌话题。")
        return "\n".join(lines)


class UpdateProfileRequest(BaseModel):
    """PUT /api/profile 请求体。primary_domain 必填（pydantic 天然校验）。"""

    primary_domain: PrimaryDomain  # 必填：缺失/非法值 → 422
    sub_domain: str | None = Field(default=None, max_length=50)
    tone: CreatorTone = CreatorTone.PROFESSIONAL
    visual_style: VisualStyle = VisualStyle.WARM
    taboo_topics: list[str] = Field(default_factory=list)
    taboo_words: list[str] = Field(default_factory=list)
    identity: str | None = Field(default=None, max_length=200)
    differentiation: str | None = Field(default=None, max_length=200)
    content_direction: str | None = Field(default=None, max_length=200)
    target_audience: str | None = Field(default=None, max_length=200)
    audience_pain_points: str | None = Field(default=None, max_length=200)
    opening_style: str | None = Field(default=None, max_length=100)
    content_rhythm: str | None = Field(default=None, max_length=100)
    signature_elements: str | None = Field(default=None, max_length=200)

    @field_validator("sub_domain")
    @classmethod
    def _clean_sub_domain(cls, v: str | None) -> str | None:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned[:50] if cleaned else None

    @field_validator("taboo_topics", "taboo_words")
    @classmethod
    def _clean_taboo_list(cls, v: list[str]) -> list[str]:
        """清洗禁忌清单：去首尾空白、去空项、去重、截断到合理长度。"""
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in v:
            text = (item or "").strip()[:100]
            if text and text not in seen:
                seen.add(text)
                cleaned.append(text)
        return cleaned[:20]


class ProfileValidationResponse(BaseModel):
    """POST /api/profile/validate 响应：启动工作流前的画像完整性检查。"""

    valid: bool
    reason: str | None = None  # 无效原因: profile_not_found / primary_domain_empty
    profile: UserProfile | None = None


class ProfileValidationError(Exception):
    """画像缺失或不完整（工作流启动前置检查抛出）。

    红线：画像注入失败必须 fail-fast，禁止降级启动工作流。
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason  # "profile_not_found" | "primary_domain_empty"
        super().__init__(f"user profile invalid: {reason}")