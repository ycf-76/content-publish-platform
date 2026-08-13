"""工作流节点包。

从各子模块 re-export 所有节点函数、状态定义和辅助工具，
保持向后兼容：from app.agents.graph import X 仍可用（graph.py 从这里 re-import）。

模块结构：
- _base.py: 共享基础设施（NodeStatus / WorkflowState / SSE helpers / _run_node_harness）
- search.py: 搜索节点
- analyze.py: 三层分析节点
- image_plan.py: 图片规划节点（含 card_draft 生成 + 模板推荐）
- image_gen.py: 图片生成节点（接收前端注入图片）
- image_review.py: 图片审核节点
- copywrite.py: 文案生成节点
- audit.py: 合规审核节点
- final_review.py: 终审节点
- publish.py: 发布节点
- quality_checks.py: 3 个软语义质量检查节点
- routing.py: 7 个路由函数 + rollback
"""

# 共享基础设施（保持 graph.py / workflow.py / tests 的 import 链不断）
from app.agents.nodes._base import (
    WorkflowState,
    NodeStatus,
    initial_state,
    _merge_dict,
    _dlog,
    emit_workflow_event,
    emit_node_event,
    _run_node_harness,
    logger,
)

# 9 个业务节点
from app.agents.nodes.search import search_node
from app.agents.nodes.analyze import analyze_node
from app.agents.nodes.image_plan import image_plan_node
from app.agents.nodes.image_gen import image_gen_node
from app.agents.nodes.image_review import image_review_node
from app.agents.nodes.copywrite import copywrite_node
from app.agents.nodes.audit import audit_node
from app.agents.nodes.final_review import final_review_node
from app.agents.nodes.publish import publish_node

# 3 个质量检查节点
from app.agents.nodes.quality_checks import (
    analyze_quality_check_node,
    copywrite_quality_check_node,
    audit_quality_check_node,
)

# 路由函数
from app.agents.nodes.routing import (
    route_after_search,
    route_after_image_gen,
    route_after_analyze,
    route_after_copywrite,
    route_after_image_review,
    route_after_final_review,
    route_after_audit,
    rollback_to_node,
)

__all__ = [
    # State
    "WorkflowState",
    "NodeStatus",
    "initial_state",
    # SSE helpers
    "emit_workflow_event",
    "emit_node_event",
    # Harness
    "_run_node_harness",
    # Debug
    "_dlog",
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
    # Quality check nodes
    "analyze_quality_check_node",
    "copywrite_quality_check_node",
    "audit_quality_check_node",
    # Routing
    "route_after_search",
    "route_after_image_gen",
    "route_after_analyze",
    "route_after_copywrite",
    "route_after_image_review",
    "route_after_final_review",
    "route_after_audit",
    "rollback_to_node",
]
