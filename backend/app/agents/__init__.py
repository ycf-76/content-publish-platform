"""Agent orchestration layer.

Layer A: LangGraph orchestration (app/agents/graph.py)
Layer B: Harness runtime (app/engine/harness/)
Layer C: Tools + MCP (app/tools/)

智能路由：smart_routing.py 三层路由替代旧 routing.py。
信念系统：belief.py 每个节点维护信心分 + 判断。
"""

from app.agents.graph import (
    WorkflowState,
    NodeStatus,
    search_node,
    analyze_node,
    image_plan_node,
    image_gen_node,
    image_review_node,
    copywrite_node,
    audit_node,
    final_review_node,
    publish_node,
    route_after_search,
    route_after_analyze,
    route_after_copywrite,
    route_after_image_gen,
    route_after_image_review,
    route_after_audit,
    route_after_final_review,
)

__all__ = [
    # State
    "WorkflowState",
    "NodeStatus",
    # Nodes
    "search_node",
    "analyze_node",
    "image_plan_node",
    "image_gen_node",
    "image_review_node",
    "copywrite_node",
    "audit_node",
    "final_review_node",
    "publish_node",
    # Routing (smart_routing)
    "route_after_search",
    "route_after_analyze",
    "route_after_copywrite",
    "route_after_image_gen",
    "route_after_image_review",
    "route_after_audit",
    "route_after_final_review",
]