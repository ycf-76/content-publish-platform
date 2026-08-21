"""Workflow API schemas."""

from pydantic import BaseModel, Field


class StartWorkflowRequest(BaseModel):
    """Request to start a new workflow."""

    topic: str = Field(..., description="Workflow topic")
    search_keyword: str | None = Field(
        default=None,
        description="搜索用关键词；未传时兼容使用 topic",
    )
    creative_brief: str = Field(
        default="",
        description="用户创作要求；优先级高于热点分析和推荐方向",
    )
    account_id: str = Field(..., description="XHS account ID")
    # 用户在右侧工作区选择的模型/温度/风格配置（可选，缺省时使用系统默认）
    # 字段说明：
    #   text_model: 文本生成模型，如 "deepseek-chat" / "deepseek-reasoner"
    #   image_model: 图片生成模型，如 "wanx-v1"（预留，后续可扩展 flux/sd）
    #   temperature: 0.0-1.0，控制文本生成随机性
    #   writing_style: 文风，如 "活泼少女"/"知性优雅"/"专业干货"/"慵懒随性"
    #   image_style: 图片风格，如 "清新自然"/"日系胶片"/"暖阳滤镜"/"复古胶片"
    # 注：避免使用 model_config（Pydantic v2 保留属性）
    model_settings: dict = Field(
        default_factory=dict,
        description="用户在右侧工作区选择的模型/温度/风格配置",
    )
    # 选题池条目作为参考素材（可选）。从选题池"发起新工作流"时携带，
    # 包含 title/summary/url/platform/source_keyword/likes 等字段，
    # 注入 copywrite 节点的 LLM prompt 作为参考内容。
    reference: dict = Field(
        default_factory=dict,
        description="选题池参考素材（标题/摘要/URL/平台/互动数据等）",
    )


class WorkflowResponse(BaseModel):
    """Workflow status response."""

    workflow_id: str
    user_id: str
    account_id: str
    topic: str
    status: str
    current_node: str
    created_at: str


class WorkflowListItem(BaseModel):
    """Workflow list item (lighter than full response)."""

    workflow_id: str
    topic: str
    status: str
    current_node: str
    account_id: str
    created_at: str
    updated_at: str | None = None


class RollbackRequest(BaseModel):
    """Request to rollback to a previous checkpoint."""

    target_node: str = Field(..., description="Target node to rollback to")


class PauseRequest(BaseModel):
    """Request to pause workflow."""

    reason: str = Field(default="", description="Pause reason")


class ResumeWorkflowRequest(BaseModel):
    """Request to resume a workflow and optionally choose a direction."""

    selected_direction: int | None = Field(
        default=None,
        ge=0,
        description="analyze 推荐方向索引，从 0 开始",
    )
    direction_note: str = Field(
        default="",
        max_length=2000,
        description="用户对所选方向的补充要求",
    )


class UpdateNodeOutputRequest(BaseModel):
    """Request to update a node's output (manual edit).

    用于人工编辑节点输出（如 copywrite 的 title/content/tags），
    覆盖 LangGraph state 中的 node_outputs[node_id]，供后续节点使用。
    """

    output: dict = Field(
        ...,
        description="要覆盖写入的节点输出字段（如 {title, content, tags}），会与现有 output 合并",
    )
