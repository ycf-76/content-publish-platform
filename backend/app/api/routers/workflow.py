"""Workflow routers."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse
from app.api.schemas.workflow import (
    PauseRequest,
    RollbackRequest,
    StartWorkflowRequest,
    UpdateNodeOutputRequest,
    WorkflowResponse,
)
from app.db.session import get_db
from app.services.workflow import get_workflow_service

router = APIRouter(prefix="/api/workflows", tags=["workflow"])


@router.post("")
async def start_workflow(
    request: StartWorkflowRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[WorkflowResponse]:
    """Start a new workflow."""
    service = get_workflow_service(db)

    workflow = await service.start_workflow(
        user_id=user_id,
        account_id=request.account_id,
        topic=request.topic,
        model_settings=request.model_settings,
        reference=request.reference,
    )

    return StandardResponse(
        data=WorkflowResponse(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            account_id=workflow.account_id,
            topic=workflow.topic,
            status=workflow.status,
            current_node=workflow.current_node_id or "search",
            created_at=workflow.created_at.isoformat() if workflow.created_at else "",
        )
    )


@router.get("/{workflow_id}/nodes")
async def get_workflow_nodes(
    workflow_id: str,
) -> StandardResponse[dict]:
    """Get workflow node states + outputs (轮询兜底接口).

    优先从 sse_bus 事件历史重建节点状态（含 output 等完整信息）。
    若事件历史为空（后端重启后 in-memory 丢失），从 LangGraph checkpoint
    重建节点状态作为兜底，保证轮询在后端重启后仍能返回正确状态。
    """
    from app.services.sse_bus import sse_bus

    events = sse_bus._event_history.get(workflow_id, [])
    nodes: dict[str, dict] = {}
    workflow_status = "running"
    for event in events:
        etype = event.event_type
        payload = event.payload or {}
        node_id = payload.get("node_id") or payload.get("id") or ""

        # review_required 事件：工作流在审核节点前 interrupt 暂停
        # 此时审核节点函数还没执行（没有 node_started 事件），
        # 需要从 review_required 事件中提取节点信息，设置状态为 awaiting_review
        if etype == "review_required":
            review_node = payload.get("review_node") or node_id
            if review_node:
                if review_node not in nodes:
                    nodes[review_node] = {"node_id": review_node, "status": "pending"}
                nodes[review_node]["status"] = "awaiting_review"
                nodes[review_node].update(payload)
        elif etype == "review_processed":
            # 审核结果已提交，工作流 resume
            pass
        elif etype in ("node_started", "node_status_changed", "node_completed", "node_error"):
            if node_id:
                if node_id not in nodes:
                    nodes[node_id] = {"node_id": node_id, "status": "pending"}
                nodes[node_id].update(payload)
                if etype == "node_completed":
                    nodes[node_id]["status"] = "completed"
                elif etype == "node_error":
                    nodes[node_id]["status"] = "error"
                elif etype == "node_status_changed" and "status" in payload:
                    nodes[node_id]["status"] = payload["status"]
        elif etype == "workflow_completed":
            workflow_status = "completed"
        elif etype == "workflow_error":
            workflow_status = "error"
        elif etype == "workflow_suspended":
            workflow_status = "suspended"

    # ===== 兜底：事件历史为空时，从 LangGraph checkpoint 重建节点状态 =====
    # 后端重启后 sse_bus._event_history 清空（in-memory），轮询会返回空。
    # 从 AsyncSqliteSaver checkpoint 读取 node_statuses + next，重建节点列表。
    if not nodes:
        try:
            from app.agents.graph import build_workflow_graph
            graph = build_workflow_graph(checkpointer=None)
            if graph is not None:
                config = {"configurable": {"thread_id": workflow_id}, "recursion_limit": 50}
                graph_state = await graph.aget_state(config)
                state_values = graph_state.values or {}
                next_nodes = getattr(graph_state, "next", None) or ()
                node_statuses = state_values.get("node_statuses", {})
                node_outputs = state_values.get("node_outputs", {})

                # 节点顺序（与 graph.py initial_state 一致）
                node_order = [
                    "search", "analyze", "image_plan", "image_gen",
                    "image_review", "copywrite", "audit", "final_review", "publish",
                ]
                for nid in node_order:
                    status = node_statuses.get(nid, "pending")
                    # next_nodes 中的节点表示即将执行（interrupt 暂停在此前）
                    # 对于审核节点（image_review/final_review），应标记为 awaiting_review
                    # publish 节点也加入 interrupt_before，auto_publish=False 时标记 awaiting_review
                    if nid in next_nodes and nid in ("image_review", "final_review", "publish"):
                        status = "awaiting_review"
                    # image_gen 在 next_nodes 中表示 interrupt 暂停等待卡片注入
                    # 应标记为 idle 让前端显示卡片编辑器
                    if nid in next_nodes and nid == "image_gen":
                        status = "idle"
                    node_entry: dict = {"node_id": nid, "status": status}
                    # 附带 output（排除大体积字段 images_base64，避免 HTTP 响应过大）
                    # 前端需要完整 output 才能渲染卡片编辑器（card_draft）、
                    # 终审预览（title/content/tags）、分析结果等
                    # images_base64 通过专门的 GET /nodes/{node_id}/images 接口获取
                    output = node_outputs.get(nid)
                    if output and isinstance(output, dict):
                        safe_output = {k: v for k, v in output.items() if k != "images_base64"}
                        node_entry.update(safe_output)
                        node_entry["output_keys"] = list(output.keys())
                        node_entry["has_output"] = True
                    nodes[nid] = node_entry

                # 从 next_nodes 推断 workflow_status
                if not next_nodes:
                    # 无后续节点：检查是否全部 completed
                    all_done = all(s == "completed" for s in node_statuses.values())
                    workflow_status = "completed" if all_done else "running"
        except Exception:
            pass

    return StandardResponse(data={
        "workflow_id": workflow_id,
        "status": workflow_status,
        "nodes": list(nodes.values()),
    })


@router.get("/{workflow_id}/nodes/{node_id}/images")
async def get_node_images(
    workflow_id: str,
    node_id: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[dict]:
    """获取节点输出的图片 base64 列表。

    SSE 事件和 getNodes 接口都剥离了 images_base64（避免 payload 过大），
    前端在 image_review 审核阶段需要单独调本接口获取图片。
    """
    from app.agents.graph import build_workflow_graph

    graph = build_workflow_graph(checkpointer=None)
    if graph is None:
        raise HTTPException(status_code=500, detail="Graph build failed")

    config = {"configurable": {"thread_id": workflow_id}, "recursion_limit": 50}
    try:
        graph_state = await graph.aget_state(config)
        state_values = graph_state.values or {}
        node_outputs = state_values.get("node_outputs", {})
        node_output = node_outputs.get(node_id, {}) or {}
        images_base64 = node_output.get("images_base64", []) or []

        return StandardResponse(data={
            "node_id": node_id,
            "images_base64": images_base64,
            "image_count": len(images_base64),
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Get node images failed: {e}")


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[WorkflowResponse]:
    """Get workflow status."""
    service = get_workflow_service(db)

    workflow = await service.get_workflow(workflow_id, user_id)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return StandardResponse(
        data=WorkflowResponse(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            account_id=workflow.account_id,
            topic=workflow.topic,
            status=workflow.status,
            current_node=workflow.current_node_id or "search",
            created_at=workflow.created_at.isoformat() if workflow.created_at else "",
        )
    )


@router.post("/{workflow_id}/pause")
async def pause_workflow(
    workflow_id: str,
    request: PauseRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """Pause workflow."""
    service = get_workflow_service(db)
    result = await service.pause_workflow(workflow_id, user_id)
    return StandardResponse(data=result, message=result.get("message", ""))


@router.post("/{workflow_id}/resume")
async def resume_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """Resume workflow."""
    service = get_workflow_service(db)
    result = await service.resume_workflow(workflow_id, user_id)
    return StandardResponse(data=result, message=result.get("message", ""))


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """用户主动取消工作流（刷新/重新搜索等场景）。"""
    service = get_workflow_service(db)
    result = await service.cancel_workflow(workflow_id, user_id)
    return StandardResponse(data=result, message=result.get("message", ""))

@router.post("/{workflow_id}/terminate")
async def terminate_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """Terminate workflow."""
    service = get_workflow_service(db)
    result = await service.terminate_workflow(workflow_id, user_id)
    return StandardResponse(data=result, message=result.get("message", ""))


@router.post("/{workflow_id}/rollback")
async def rollback_workflow(
    workflow_id: str,
    request: RollbackRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """Rollback workflow to target node."""
    service = get_workflow_service(db)
    result = await service.rollback_workflow(workflow_id, user_id, request.target_node)
    return StandardResponse(data=result, message=result.get("message", ""))


@router.patch("/{workflow_id}/nodes/{node_id}/output")
async def update_node_output(
    workflow_id: str,
    node_id: str,
    request: UpdateNodeOutputRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """人工编辑节点输出（如 copywrite 的 title/content/tags）。

    覆盖 LangGraph state 中的 node_outputs[node_id]，供后续节点使用编辑后的内容。
    后端会推送 node_output_updated SSE 事件，前端即时刷新展示。
    """
    service = get_workflow_service(db)
    result = await service.update_node_output(
        workflow_id, node_id, request.output, user_id
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Update failed"))
    return StandardResponse(data=result, message=result.get("message", ""))


@router.post("/{workflow_id}/publish/check")
async def check_publish_result(
    workflow_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """回查半自动发布结果（前端轮询接口）。

    半自动发布：worker 填好标题/正文/图片后不点击，由用户在浏览器窗口
    手动点「发布」。前端收到 publish 节点 awaiting_manual 状态后轮询此接口，
    判断发布是否完成。

    返回 status:
      - pending: 仍在编辑器，等用户点击
      - published: 发布成功，页面已跳转（同时更新节点为 completed + 推 SSE）
      - failed: 发布失败（登录失效/页面错误提示）
      - session_invalid: 会话过期
      - not_applicable: 非半自动模式（无需轮询）
    """
    from app.agents.skills.mcp.xhs_client import mcp_manager
    from app.services.sse_bus import sse_bus
    from app.db.models import NodeType, NodeStatus, WorkflowNode
    from sqlalchemy import select

    result = await mcp_manager.check_publish_result()
    status = result.get("status", "pending")

    # published/failed 时更新 DB 节点状态 + 推 SSE
    if status in ("published", "failed"):
        try:
            node = await db.scalar(
                select(WorkflowNode).where(
                    WorkflowNode.workflow_id == workflow_id,
                    WorkflowNode.node_type == NodeType.PUBLISH,
                )
            )
            if node and node.node_status != NodeStatus.COMPLETED.value:
                node.node_status = NodeStatus.COMPLETED.value
                node_output = {
                    "post_id": "",
                    "status": "success" if status == "published" else "failed",
                    "message": result.get("message", ""),
                    "url": result.get("url", ""),
                }
                import json
                node.output = json.dumps(node_output, ensure_ascii=False)
                await db.commit()
                # 推送 node_completed SSE
                await sse_bus.publish(
                    workflow_id,
                    "node_completed",
                    {"node_id": "publish", **node_output},
                )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"[{workflow_id}] check_publish update node failed: {e}"
            )

    return StandardResponse(data=result)


@router.post("/{workflow_id}/images/render-template")
async def render_template_image(
    workflow_id: str,
    request: dict,
) -> StandardResponse[dict]:
    """渲染结构化图表模板为 base64 PNG。

    第一期新增接口：供前端预览 image_plan 生成的结构化模板。

    请求体：
        {
            "template_type": "flow" | "list" | "timeline",
            "data": {...},          # 模板数据（title + steps/items/events）
            "style": "fresh_natural",  # 可选，配色风格
            "size": "3:4"             # 可选，尺寸
        }

    返回：
        {
            "base64": "iVBORw0KGgo...",  # 裸 base64（不带 data: 前缀）
            "size": "3:4"
        }
    """
    from app.services.card_renderer import render_template_to_base64

    template_type = request.get("template_type", "")
    data = request.get("data", {})
    style = request.get("style", "fresh_natural")
    size = request.get("size", "3:4")

    if not template_type:
        raise HTTPException(status_code=400, detail="template_type is required")
    if not data:
        raise HTTPException(status_code=400, detail="data is required")

    try:
        b64 = await render_template_to_base64(template_type, data, style, size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {e}")

    return StandardResponse(data={"base64": b64, "size": size})