"""Observer 观测层（占位）。

对应技术架构文档 4.1 + D16 过程透明化。
Phase 2 实现 6 种 trace 事件方法，通过依赖注入的 callback 推送，不直接 import SSE。
"""
from app.engine.harness.observer.observer import Observer

__all__ = ["Observer"]
