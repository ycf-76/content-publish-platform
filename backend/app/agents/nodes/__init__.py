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
- smart_routing.py: 三层智能路由（替代旧 routing.py）
- belief.py: 信念系统（每个节点维护信心分 + 判断）
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

# 后处理节点（可选，在 publish 之后执行）
from app.agents.nodes.card_gen import card_gen_node
from app.agents.nodes.wechat_push import wechat_push_node
from app.agents.nodes.feishu_push import feishu_push_node

# 路由函数（smart_routing 三层路由）
from app.agents.nodes.smart_routing import (
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
    # Post-processing nodes
    "card_gen_node",
    "wechat_push_node",
    "feishu_push_node",
    # Routing (smart_routing)
    "route_after_search",
    "route_after_analyze",
    "route_after_copywrite",
    "route_after_image_gen",
    "route_after_image_review",
    "route_after_audit",
    "route_after_final_review",
]