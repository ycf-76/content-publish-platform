"""Agent Pydantic 输出 Schema（占位）。

定义每个 Agent 节点的结构化输出模型，用于硬规则 Schema 校验。
Phase 4 按各 Agent 配置逐个实现。
"""

from typing import Any

from pydantic import BaseModel, Field


class AgentOutput(BaseModel):
    """Agent 通用输出基类（占位）。"""

    node_key: str = Field(description="节点标识")
    success: bool = Field(default=False, description="是否成功")
    data: dict[str, Any] = Field(default_factory=dict, description="输出数据")
    error: str | None = Field(default=None, description="错误信息")


class WorkflowContext(BaseModel):
    """工作流上下文（占位），随 LangGraph State 流转。"""

    workflow_id: str
    topic: str
    current_node: str | None = None
