"""上下文层：会话级上下文 `SessionContext`（第 4 层记忆）。

层级关系（见方案 3.1）：
- `WorkflowContext`：单次节点执行（任务级）
- `SessionContext`：一次 Chat 会话（会话级，本文件）
- `agent_memory`：跨工作流长期记忆（用户级）

`SessionContext` 负责多轮追问：记录最近一次工作流 ID 与输出，追问时把上游输出
注入下一个工作流。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SessionContext(BaseModel):
    """会话级上下文。"""

    session_id: str
    user_id: str
    last_workflow_id: str | None = None
    upstream_outputs: dict[str, Any] = Field(default_factory=dict)
    working_state: dict[str, Any] = Field(default_factory=dict)

    def record_workflow(self, workflow_id: str, outputs: dict[str, Any]) -> None:
        """记录最近一次工作流，供追问时复用上游输出。"""
        self.last_workflow_id = workflow_id
        self.upstream_outputs = outputs

    def clear_workflow(self) -> None:
        self.last_workflow_id = None
        self.upstream_outputs = {}
