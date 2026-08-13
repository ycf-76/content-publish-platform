"""Workflow 上下文变量。

用于在异步调用链里传递 workflow_id，让底层 MCP client 等组件能感知当前 workflow 上下文，
发 SSE 事件时知道该发给哪个 workflow。
"""

from __future__ import annotations

from contextvars import ContextVar

# 当前 workflow_id（请求级上下文）
current_workflow_id: ContextVar[str | None] = ContextVar(
    "current_workflow_id", default=None
)
