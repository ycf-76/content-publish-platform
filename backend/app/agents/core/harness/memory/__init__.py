"""任务内上下文 Memory（占位）。

对应 PRD D7：仅任务内上下文传递，不做跨任务记忆/向量化。
Phase 2 实现 AgentMemory：set/get/to_dict，仅内存，不持久化。
"""
from app.agents.core.harness.memory.memory import AgentMemory

__all__ = ["AgentMemory"]
