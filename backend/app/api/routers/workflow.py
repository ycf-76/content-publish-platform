"""Workflow routers."""

import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse

_bearer_scheme_optional = HTTPBearer(auto_error=False)


async def _optional_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme_optional),
) -> str | None:
    if credentials is None:
        return None
    from app.security import decode_user_id
    try:
        return decode_user_id(credentials.credentials)
    except Exception:
        return None
from app.api.schemas.workflow import (
    PauseRequest,
    RollbackRequest,
    StartWorkflowRequest,
    ResumeWorkflowRequest,
    UpdateNodeOutputRequest,
    WorkflowListItem,
    WorkflowResponse,
)
from app.db.models import Workflow
from app.db.session import get_db
from app.services.workflow import get_workflow_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflow"])


@router.post("")
async def start_workflow(
    request: StartWorkflowRequest,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[WorkflowResponse]:
    """Start a new workflow."""
    logger.info(f"[start_workflow] user_id={user_id}, account_id={request.account_id}, topic={request.topic}")
    try:
        service = get_workflow_service(db)

        workflow = await service.start_workflow(
            user_id=user_id,
            account_id=request.account_id,
            topic=request.topic,
            search_keyword=request.search_keyword,
            creative_brief=request.creative_brief,
            model_settings=request.model_settings,
            reference=request.reference,
        )
    except Exception as e:
        logger.error(f"[start_workflow] FAILED: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"启动工作流失败: {e}")

    return StandardResponse(
        data=WorkflowResponse(
            workflow_id=workflow.id,
            user_id=workflow.user_id,
            account_id=workflow.account_id or "",
            topic=workflow.topic,
            status=workflow.status,
            current_node=workflow.current_node_id or "search",
            created_at=workflow.created_at.isoformat() if workflow.created_at else "",
        )
    )


@router.get("")
async def list_workflows(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> StandardResponse[list[WorkflowListItem]]:
    """List current user's workflows, newest first.

    Query params:
        status: filter by status (optional)
        limit: max items (default 50, max 200)
        offset: pagination offset
    """
    from sqlalchemy import select, func

    limit = min(limit, 200)
    stmt = (
        select(Workflow)
        .where(Workflow.user_id == user_id)
        .order_by(Workflow.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if status:
        stmt = stmt.where(Workflow.status == status)

    result = await db.execute(stmt)
    workflows = result.scalars().all()

    count_stmt = select(func.count()).select_from(Workflow).where(Workflow.user_id == user_id)
    if status:
        count_stmt = count_stmt.where(Workflow.status == status)
    total = (await db.scalar(count_stmt)) or 0

    items = [
        WorkflowListItem(
            workflow_id=w.id,
            topic=w.topic,
            status=w.status,
            current_node=w.current_node_id or "",
            account_id=w.account_id or "",
            created_at=w.created_at.isoformat() if w.created_at else "",
            updated_at=w.updated_at.isoformat() if w.updated_at else None,
        )
        for w in workflows
    ]
    return StandardResponse(data=items, message=f"total={total}")


@router.get("/{workflow_id}/nodes")
async def get_workflow_nodes(
    workflow_id: str,
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Depends(_optional_user_id),
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

    # ===== 补全：事件历史只包含部分节点时，从数据库补全缺失节点 =====
    # 事件历史可能只有 review_required 等少量事件，导致 nodes 不完整。
    # 从 workflow_nodes 表 + 事件历史推断的位置补全所有标准节点。
    _STANDARD_NODE_ORDER = [
        "search", "analyze", "copywrite", "image_plan", "image_gen",
        "image_review", "audit", "final_review", "publish",
    ]
    if nodes and len(nodes) < len(_STANDARD_NODE_ORDER):
        try:
            from sqlalchemy import select as sa_select
            from app.db.models import WorkflowNode
            wf_row = await db.scalar(sa_select(Workflow).where(Workflow.id == workflow_id))
            if wf_row:
                # 用事件历史中已出现的节点推断进度位置
                # 优先用 awaiting_review/running 节点，其次用 DB 的 current_node_id
                event_max_idx = -1
                for nid in nodes:
                    if nid in _STANDARD_NODE_ORDER:
                        idx = _STANDARD_NODE_ORDER.index(nid)
                        if idx > event_max_idx:
                            event_max_idx = idx
                wf_current_node = wf_row.current_node_id or ""
                db_idx = _STANDARD_NODE_ORDER.index(wf_current_node) if wf_current_node in _STANDARD_NODE_ORDER else -1
                # 取较大值作为当前进度位置
                current_idx = max(event_max_idx, db_idx)

                wf_nodes_rows = await db.scalars(sa_select(WorkflowNode).where(WorkflowNode.workflow_id == workflow_id))
                wf_nodes_map = {wn.node_key: wn for wn in wf_nodes_rows}
                for i, nid in enumerate(_STANDARD_NODE_ORDER):
                    if nid in nodes:
                        continue
                    if current_idx >= 0 and i < current_idx:
                        status = "completed"
                    elif i == current_idx:
                        status = "running"
                    else:
                        status = "pending"
                    entry: dict = {"node_id": nid, "status": status}
                    wn = wf_nodes_map.get(nid)
                    if wn and wn.output_data and isinstance(wn.output_data, dict):
                        safe_output = {k: v for k, v in wn.output_data.items() if k != "images_base64"}
                        entry.update(safe_output)
                        entry["has_output"] = True
                    nodes[nid] = entry
                if not workflow_status or workflow_status == "running":
                    workflow_status = wf_row.status or "running"
        except Exception:
            pass

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
                    "search", "analyze", "copywrite", "image_plan", "image_gen",
                    "image_review", "audit", "final_review", "publish",
                ]
                for nid in node_order:
                    status = node_statuses.get(nid, "pending")
                    if nid in next_nodes and nid in ("copywrite", "image_plan", "image_review", "publish"):
                        status = "awaiting_review"
                    node_entry: dict = {"node_id": nid, "status": status}
                    output = node_outputs.get(nid)
                    if output and isinstance(output, dict):
                        safe_output = {k: v for k, v in output.items() if k != "images_base64"}
                        node_entry.update(safe_output)
                        node_entry["output_keys"] = list(output.keys())
                        node_entry["has_output"] = True
                    nodes[nid] = node_entry

                # 从 next_nodes 推断 workflow_status
                if not next_nodes:
                    all_done = all(s == "completed" for s in node_statuses.values())
                    workflow_status = "completed" if all_done else "running"
        except Exception:
            pass

    # ===== 二次兜底：checkpoint 也丢失（MemorySaver 重启后清空）时，从数据库推断 =====
    # 当 MemorySaver 重启后丢失所有 checkpoint，上面的兜底会返回全 pending 节点。
    # 此时根据 Workflow 的 status 字段推断节点状态：
    #   - completed → 所有节点 completed
    #   - failed/error → current_node 之前的节点 completed，current_node 标记 error
    #   - running → current_node 之前的节点 completed，current_node 标记 running
    # 同时从 workflow_nodes 表读取 output_data 和元数据（duration_ms/model_used/token_usage），
    # 让前端卡片能展示已完成节点的结果。
    if not nodes or all(n.get("status") == "pending" for n in nodes.values()):
        try:
            from sqlalchemy import select as sa_select
            from app.db.models import WorkflowNode, NodeType, NodeStatus as DBNodeStatus
            wf_row = await db.scalar(sa_select(Workflow).where(Workflow.id == workflow_id))
            if wf_row:
                wf_db_status = wf_row.status
                wf_current_node = wf_row.current_node_id or ""
                node_order = [
                    "search", "analyze", "image_plan", "image_gen",
                    "image_review", "copywrite", "audit", "final_review", "publish",
                ]
                current_idx = node_order.index(wf_current_node) if wf_current_node in node_order else -1

                # 从 workflow_nodes 表读取所有节点的 output_data 和元数据
                wf_nodes_rows = await db.scalars(
                    sa_select(WorkflowNode).where(WorkflowNode.workflow_id == workflow_id)
                )
                wf_nodes_map: dict[str, WorkflowNode] = {}
                for wn in wf_nodes_rows:
                    wf_nodes_map[wn.node_key] = wn

                def _build_node_entry(nid: str, status: str) -> dict:
                    entry: dict = {"node_id": nid, "status": status}
                    wn = wf_nodes_map.get(nid)
                    if wn:
                        if wn.output_data and isinstance(wn.output_data, dict):
                            safe_output = {k: v for k, v in wn.output_data.items() if k != "images_base64"}
                            entry.update(safe_output)
                            entry["output"] = safe_output
                            entry["has_output"] = True
                        if wn.duration_ms:
                            entry["_duration_ms"] = wn.duration_ms
                        if wn.model_used:
                            entry["_model_used"] = wn.model_used
                        if wn.token_usage:
                            entry["_token_usage"] = {"total": wn.token_usage}
                        if wn.error_message:
                            entry["_error"] = wn.error_message
                            entry["error"] = wn.error_message
                    return entry

                if wf_db_status in ("completed",):
                    for nid in node_order:
                        nodes[nid] = _build_node_entry(nid, "completed")
                    workflow_status = "completed"
                elif wf_db_status in ("failed", "error"):
                    for i, nid in enumerate(node_order):
                        if current_idx >= 0 and i < current_idx:
                            nodes[nid] = _build_node_entry(nid, "completed")
                        elif i == current_idx:
                            nodes[nid] = _build_node_entry(nid, "error")
                        else:
                            nodes[nid] = {"node_id": nid, "status": "pending"}
                    workflow_status = str(wf_db_status)
                elif wf_db_status in ("running", "suspended"):
                    for i, nid in enumerate(node_order):
                        if current_idx >= 0 and i < current_idx:
                            nodes[nid] = _build_node_entry(nid, "completed")
                        elif i == current_idx:
                            if wf_db_status == "suspended" and nid in ("image_review", "final_review", "publish"):
                                nodes[nid] = _build_node_entry(nid, "awaiting_review")
                            else:
                                nodes[nid] = _build_node_entry(nid, "running")
                        else:
                            nodes[nid] = {"node_id": nid, "status": "pending"}
                    workflow_status = str(wf_db_status)
                else:
                    for nid in node_order:
                        if nid not in nodes:
                            nodes[nid] = {"node_id": nid, "status": "pending"}
                    workflow_status = str(wf_db_status)
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
    db: AsyncSession = Depends(get_db),
    user_id: str | None = Depends(_optional_user_id),
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
            account_id=workflow.account_id or "",
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
    request: ResumeWorkflowRequest | None = None,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """Resume workflow."""
    service = get_workflow_service(db)
    payload = request or ResumeWorkflowRequest()
    result = await service.resume_workflow(
        workflow_id,
        user_id,
        selected_direction=payload.selected_direction,
        direction_note=payload.direction_note,
    )
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
    from app.tools.mcp.xhs_client import mcp_manager
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
        if style.startswith("esther_"):
            from app.services.esther_card_renderer import render_esther_template_to_base64
            b64 = await render_esther_template_to_base64(template_type, data, style, size)
        else:
            b64 = await render_template_to_base64(template_type, data, style, size)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {e}")

    return StandardResponse(data={"base64": b64, "size": size})


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """删除工作流实例及其所有状态数据。"""
    from sqlalchemy import delete as sa_delete

    stmt = sa_delete(Workflow).where(
        Workflow.id == workflow_id,
        Workflow.user_id == user_id,
    )
    result = await db.execute(stmt)
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return StandardResponse(data={"deleted": True}, message="工作流已删除")


@router.get("/stats/weekly")
async def get_weekly_stats(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """Get current user's weekly workflow statistics.

    Returns:
        published_count: 本周已完成（completed）的工作流数量
        total_workflows: 本周创建的工作流总数
        completed_rate: 完成率 (published_count / total_workflows)
        active_count: 当前运行中的工作流数量
    """
    from sqlalchemy import select, func, and_
    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=now.weekday(), hours=now.hour, minutes=now.minute, seconds=now.second, microseconds=now.microsecond)
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

    total_stmt = select(func.count()).select_from(Workflow).where(
        and_(Workflow.user_id == user_id, Workflow.created_at >= week_start)
    )
    total_workflows = (await db.scalar(total_stmt)) or 0

    published_stmt = select(func.count()).select_from(Workflow).where(
        and_(Workflow.user_id == user_id, Workflow.created_at >= week_start, Workflow.status == "completed")
    )
    published_count = (await db.scalar(published_stmt)) or 0

    running_stmt = select(func.count()).select_from(Workflow).where(
        and_(Workflow.user_id == user_id, Workflow.status.in_(["running", "pending"]))
    )
    active_count = (await db.scalar(running_stmt)) or 0

    completed_rate = round(published_count / total_workflows, 2) if total_workflows > 0 else 0.0

    return StandardResponse(data={
        "published_count": published_count,
        "total_workflows": total_workflows,
        "completed_rate": completed_rate,
        "active_count": active_count,
    })