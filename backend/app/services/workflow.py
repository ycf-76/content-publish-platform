"""工作流服务：封装 LangGraph 编排、启动、状态机。

对应 PRD 5.2 / 技术架构文档第3章 Layer A。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    NodeType,
    NodeStatus,
    PendingSuggestion,
    SuggestionSeverity,
    SuggestionStatus,
    SuggestionType,
    Workflow,
    WorkflowNode,
    WorkflowStatus,
    XhsAccount,
)
from app.services.sse_bus import sse_bus

MAX_CONCURRENT_WORKFLOWS = 10

# LangGraph imports (optional - PostgresSaver 单独 try，避免 psycopg_binary 缺失阻塞 StateGraph)
try:
    from langgraph.graph import END  # noqa: F401  仅探测 langgraph 是否可用
    from app.agents.graph import build_workflow_graph, initial_state, get_global_checkpointer
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False
    build_workflow_graph = None
    initial_state = None
    get_global_checkpointer = None


def _dlog(msg: str) -> None:
    """发布流程诊断日志（写到 backend/logs/publish_debug.log）。"""
    try:
        from app.agents.graph import _dlog as _g_dlog
        _g_dlog(msg)
    except Exception:
        pass

logger = logging.getLogger(__name__)


class WorkflowService:
    """工作流编排服务。

    封装 LangGraph 状态图、启动、恢复、回退。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        # 保存后台 task 引用，防止被 GC 回收（Python asyncio 官方警告）
        self._background_tasks: set = set()

    def _create_background_task(self, coro: Any) -> None:
        """创建后台 task 并保存引用，完成后自动移除。

        Python asyncio 官方文档明确警告：
        > Save a reference to the result of this function,
        > to avoid a task disappearing mid-execution.
        """
        import asyncio
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        _dlog(f"[_create_background_task] task created: id={id(task)}, pending={not task.done()}, tasks_count={len(self._background_tasks)}")

    async def _get_graph_for_workflow(
        self,
        workflow: Workflow,
    ) -> tuple[Any, dict | None]:
        """按 Workflow.definition_id 重建同一张 LangGraph 图。"""
        graph_definition: dict | None = None
        if workflow.definition_id:
            from app.db.models import WorkflowDefinition

            result = await self.db.execute(
                select(WorkflowDefinition).where(
                    WorkflowDefinition.id == workflow.definition_id
                )
            )
            definition = result.scalar_one_or_none()
            if definition and definition.graph_definition:
                graph_definition = definition.graph_definition
                from app.agents.graph import build_dynamic_workflow_graph

                dynamic_graph = build_dynamic_workflow_graph(
                    graph_definition,
                    checkpointer=get_global_checkpointer(),
                )
                if dynamic_graph is not None:
                    return dynamic_graph, graph_definition

        graph = build_workflow_graph(checkpointer=None)
        return graph, graph_definition

    async def _check_concurrency_limit(self) -> None:
        """P0: 检查当前并发工作流数量，超限则拒绝启动。

        使用 Redis 计数器（降级到内存计数器）跟踪活跃工作流数。
        防止大量并发工作流同时启动导致 LLM API 429 雪崩。
        
        每次检查时先校准 Redis 计数器：用 DB 中实际 running 状态的工作流数
        替代可能因进程重启而漂移的 Redis 值。
        """
        from app.cache import redis_client
        from app.db.models import Workflow
        
        # 校准：用 DB 中实际 running 的工作流数重置 Redis 计数器
        actual_count = await self.db.scalar(
            select(func.count()).select_from(Workflow).where(Workflow.status == "running")
        )
        actual_count = actual_count or 0
        await redis_client.set("count:active_workflows", actual_count)
        
        if actual_count >= MAX_CONCURRENT_WORKFLOWS:
            logger.warning(
                f"[concurrency] workflow rejected: {actual_count} already running "
                f"(limit={MAX_CONCURRENT_WORKFLOWS})"
            )
            raise HTTPException(
                429,
                f"当前有 {actual_count} 个工作流正在运行，请稍后再试",
            )
        logger.info(f"[concurrency] workflow count: {actual_count}/{MAX_CONCURRENT_WORKFLOWS}")

    @staticmethod
    async def _decrement_workflow_count() -> None:
        """P0: 工作流结束后递减活跃计数器。"""
        from app.cache import redis_client
        current = await redis_client.incrby("count:active_workflows", -1)
        logger.info(f"[concurrency] workflow ended, count: {max(0, current)}")

    @staticmethod
    async def _increment_workflow_count() -> None:
        """工作流恢复运行时递增活跃计数器。"""
        from app.cache import redis_client
        current = await redis_client.incrby("count:active_workflows", 1)
        logger.info(f"[concurrency] workflow resumed, count: {current}")

    async def _pause_workflow(self, workflow_id: str) -> None:
        """工作流进入 review_required 等待状态：DB 置 PAUSED + 递减计数器。

        review_required 不是终态，但工作流不再占用并发名额。
        resume 时由 _unpause_workflow 恢复。
        """
        from sqlalchemy import update as sa_update
        await self.db.execute(
            sa_update(Workflow)
            .where(Workflow.id == workflow_id)
            .values(status=WorkflowStatus.PAUSED)
        )
        await self.db.commit()
        await self._decrement_workflow_count()
        logger.info(f"[{workflow_id}] workflow paused (review_required), count decremented")

    async def _unpause_workflow(self, workflow_id: str) -> None:
        """工作流从 PAUSED 恢复运行：DB 置 RUNNING + 递增计数器。"""
        from sqlalchemy import update as sa_update
        from datetime import UTC, datetime as dt
        await self.db.execute(
            sa_update(Workflow)
            .where(Workflow.id == workflow_id)
            .values(status=WorkflowStatus.RUNNING)
        )
        await self.db.commit()
        await self._increment_workflow_count()
        logger.info(f"[{workflow_id}] workflow unpaused, count incremented")

    async def start_workflow(
        self,
        user_id: str,
        account_id: str,
        topic: str,
        search_keyword: str | None = None,
        creative_brief: str = "",
        model_settings: dict | None = None,
        reference: dict | None = None,
        definition_id: str | None = None,
    ) -> Workflow:
        """启动新工作流。

        Args:
            user_id: 平台用户ID
            account_id: 小红书账号ID
            topic: 内容主题
            model_settings: 用户在右侧工作区选择的模型/温度/风格配置，
                           字段：text_model, image_model, temperature,
                                writing_style, image_style。None 时使用系统默认。
            reference: 选题池参考素材（可选），包含 title/summary/url/platform 等，
                       注入 copywrite 节点的 LLM prompt 作为参考内容。
            definition_id: 工作流定义ID（可选）。传入后，工作流将按定义中的
                          graph_definition 动态执行，而非使用硬编码的9节点流程。

        Returns:
            Workflow 实例
        """
        # P0: 工作流并发上限检查（防止 LLM API 雪崩）
        await self._check_concurrency_limit()

        # P0.5: 确保 user_id 在 users 表中存在（外键约束）
        # 如果不存在，自动创建一条记录
        from app.db.models import User
        existing_user = await self.db.scalar(select(User).where(User.id == user_id))
        if not existing_user:
            logger.info(f"[start_workflow] user_id={user_id} not found, auto-creating")
            new_user = User(
                id=user_id,
                email=f"{user_id}@platform.local",
                nickname=user_id,
            )
            self.db.add(new_user)
            await self.db.flush()

        # 加载用户级长期记忆（跨工作流），注入 state 供各节点读取
        # 失败时返回空 dict，不阻塞工作流启动
        from app.services import agent_memory
        user_memory = await agent_memory.load_for_workflow(user_id)

        # 验证 account_id 是否在 xhs_accounts 表中存在
        # 邮箱登录用户传 'email_user' 等占位值，不存在于 xhs_accounts 表
        # 外键约束要求 account_id 必须引用真实记录或为 NULL
        resolved_account_id: str | None = account_id
        if not account_id or account_id == "":
            resolved_account_id = None
        else:
            stmt = select(XhsAccount).where(XhsAccount.id == account_id)
            existing_account = await self.db.scalar(stmt)
            if not existing_account:
                logger.info(
                    f"[start_workflow] account_id={account_id} not found in xhs_accounts, "
                    f"setting to None (email-only user)"
                )
                resolved_account_id = None

        # 创建 Workflow 记录
        workflow = Workflow(
            user_id=user_id,
            account_id=resolved_account_id,
            topic=topic,
            status="running",
            definition_id=definition_id,
        )
        self.db.add(workflow)
        await self.db.flush()  # 获取 workflow_id

        # 创建节点记录（动态 or 硬编码）
        graph_definition = None
        if definition_id:
            # 从 DB 加载 graph_definition
            from app.db.models import WorkflowDefinition, WorkflowDefinitionStatus
            defn_result = await self.db.execute(
                select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
            )
            defn = defn_result.scalar_one_or_none()
            if defn and defn.graph_definition:
                graph_definition = defn.graph_definition
                logger.info(f"[start_workflow] Using dynamic graph from definition: {definition_id}")

        if graph_definition and graph_definition.get("nodes"):
            # 动态节点：从 graph_definition 创建节点记录
            for node_def in graph_definition["nodes"]:
                node_type_str = node_def.get("type", "search")
                try:
                    node_type_enum = NodeType(node_type_str)
                except ValueError:
                    logger.warning(f"[start_workflow] Unknown node type: {node_type_str}, skipping")
                    continue
                node = WorkflowNode(
                    workflow_id=workflow.id,
                    node_type=node_type_enum,
                    node_key=node_type_str,
                    node_status=NodeStatus.PENDING,
                    input_data=node_def.get("config", {}),
                )
                self.db.add(node)
        else:
            # 硬编码9节点（向后兼容）
            node_types = [
                NodeType.SEARCH,
                NodeType.ANALYZE,
                NodeType.COPYWRITE,
                NodeType.IMAGE_PLAN,
                NodeType.IMAGE_GEN,
                NodeType.IMAGE_REVIEW,
                NodeType.AUDIT,
                NodeType.FINAL_REVIEW,
                NodeType.PUBLISH,
            ]
            for node_type in node_types:
                node = WorkflowNode(
                    workflow_id=workflow.id,
                    node_type=node_type,
                    node_key=node_type.value,
                    node_status=NodeStatus.PENDING,
                )
                self.db.add(node)

        await self.db.commit()
        await self.db.refresh(workflow)

        # 发布 workflow_started 事件
        await sse_bus.publish(
            workflow.id,
            "workflow_started",
            {
                "workflow_id": workflow.id,
                "topic": topic,
                "account_id": account_id,
                "started_at": datetime.now(UTC).isoformat(),
            },
        )

        logger.info(f"Workflow started: {workflow.id}, topic={topic}")

        # 异步启动图执行（不阻塞 HTTP 响应）
        if LANGGRAPH_AVAILABLE:
            import asyncio
            asyncio.create_task(
                self._execute_graph_safely(
                    workflow_id=workflow.id,
                    user_id=user_id,
                    account_id=account_id,
                    topic=topic,
                    search_keyword=search_keyword,
                    creative_brief=creative_brief,
                    model_settings=model_settings,
                    reference=reference,
                    user_memory=user_memory,
                    graph_definition=graph_definition,
                )
            )
        else:
            logger.warning("LangGraph not available, workflow will not execute")
            await self._decrement_workflow_count()

        return workflow

    async def _execute_graph_safely(
        self,
        workflow_id: str,
        user_id: str,
        account_id: str,
        topic: str,
        search_keyword: str | None = None,
        creative_brief: str = "",
        model_settings: dict | None = None,
        reference: dict | None = None,
        user_memory: dict | None = None,
        graph_definition: dict | None = None,
    ) -> None:
        """异步执行 graph，捕获所有异常防止 task 静默失败。

        红线：后台 task 不能共享请求的 db session（请求结束后 session 被 close，
        会导致 IllegalStateChangeError）。这里创建独立的 session 供整个 graph 执行使用。
        """
        # 创建独立 db session，避免共享请求的 session
        from app.db.session import AsyncSessionLocal
        async with AsyncSessionLocal() as bg_db:
            original_db = self.db
            self.db = bg_db
            try:
                await self.execute_graph(
                    workflow_id, user_id, account_id, topic, search_keyword,
                    creative_brief, model_settings,
                    reference, user_memory=user_memory,
                    graph_definition=graph_definition,
                )
            except Exception as e:
                logger.exception(f"[{workflow_id}] graph execution failed: {e}")
                await sse_bus.publish(
                    workflow_id,
                    "workflow_error",
                    {
                        "workflow_id": workflow_id,
                        "message": f"Graph execution failed: {e}",
                        "fatal": True,
                    },
                )
                await self._decrement_workflow_count()
            finally:
                self.db = original_db

    async def execute_graph(
        self,
        workflow_id: str,
        user_id: str,
        account_id: str,
        topic: str,
        search_keyword: str | None = None,
        creative_brief: str = "",
        model_settings: dict | None = None,
        reference: dict | None = None,
        user_memory: dict | None = None,
        graph_definition: dict | None = None,
    ) -> None:
        """执行 LangGraph，流式处理节点事件。

        红线：
        - 节点函数内不直接调 MCP/LLM，全部走 Harness（软语义节点除外）
        - 路由硬编码（conditional_edges），不让 LLM 决定
        - 用 MemorySaver 持久化 checkpoint（支持 interrupt/resume）
        - 失败节点走 fallback_output，单点失败不阻断工作流
        - 软语义 fail 时把 pending_suggestion 写 DB + 置 workflow=suspended

        interrupt/resume 机制：
        - graph 编译时设置 interrupt_before=["copywrite", "image_gen", "image_review", "final_review", "publish"]
        - astream 执行到审核节点前会自然退出循环（不执行节点函数）
        - 此时 workflow 状态保持 running，等待 POST /api/workflows/{id}/review
        - submit_review 调 graph.astream(None, config) resume 继续执行
        """
        if not LANGGRAPH_AVAILABLE:
            logger.warning(f"[{workflow_id}] LangGraph unavailable, skip")
            return

        # 从 DB 加载账号 cookies 并注入到 MCP client（供 search 节点使用）
        # 邮箱登录用户 account_id 为 None，跳过 cookie 加载
        if account_id:
            await self._load_account_cookies_for_mcp(workflow_id, account_id)
        else:
            logger.info(f"[{workflow_id}] no account_id, skipping cookie loading (email-only user)")

        # 构建 graph（动态 or 硬编码）
        if graph_definition and graph_definition.get("nodes"):
            from app.agents.graph import build_dynamic_workflow_graph
            graph = build_dynamic_workflow_graph(graph_definition, checkpointer=None)
            if graph is None:
                logger.warning(f"[{workflow_id}] dynamic graph build failed, falling back to default")
                graph = build_workflow_graph(checkpointer=None)
            
            # 动态节点类型列表
            dynamic_node_types = [n.get("type", "search") for n in graph_definition.get("nodes", [])]
            state = initial_state(
                workflow_id, user_id, account_id, topic, search_keyword,
                creative_brief, model_settings,
                reference, user_memory=user_memory,
                node_types=dynamic_node_types,
            )
        else:
            graph = build_workflow_graph(checkpointer=None)
            state = initial_state(
                workflow_id, user_id, account_id, topic, search_keyword,
                creative_brief, model_settings,
                reference, user_memory=user_memory,
            )

        if graph is None:
            logger.warning(f"[{workflow_id}] graph build failed")
            return

        # thread_id 配置：checkpointer 通过 thread_id 关联 state
        # submit_review 时使用相同 thread_id 才能恢复执行
        config = {
            "configurable": {"thread_id": workflow_id},
            "recursion_limit": 50,
            "metadata": {"workflow_id": workflow_id},
        }

        # 跟踪已写 DB 的 suggestion 数量，避免重复写
        seen_suggestion_count = 0
        # 是否触发了 suspend（软语义 fail）
        suspended = False
        # 跟踪所有节点最终状态（用于判断是否有 ERROR 提前终止）
        all_node_statuses: dict[str, str] = {}

        try:
            # astream 按节点流式输出 state 增量
            # 到达 interrupt_before 节点前会自然退出循环
            async for chunk in graph.astream(state, config):
                # chunk 是 dict[node_key, state_delta]
                for node_key, delta in chunk.items():
                    if not isinstance(delta, dict):
                        continue
                    node_statuses = delta.get("node_statuses", {})
                    node_outputs = delta.get("node_outputs", {})
                    # 合并到 all_node_statuses（跟踪最新状态）
                    all_node_statuses.update(node_statuses)
                    if node_statuses or node_outputs:
                        await sse_bus.publish(
                            workflow_id,
                            "workflow_snapshot",
                            {
                                "workflow_id": workflow_id,
                                "current_node": delta.get("current_node", node_key),
                                "node_statuses": node_statuses,
                                "node_outputs_keys": list(node_outputs.keys()),
                            },
                        )

                    # 持久化节点状态和输出到 workflow_nodes 表
                    # 保证后端重启后 get_workflow_nodes 二次兜底能从 DB 恢复数据
                    for nid, nstatus in node_statuses.items():
                        noutput = node_outputs.get(nid)
                        nerror = delta.get("node_errors", {}).get(nid)
                        await self._persist_node_output(
                            workflow_id=workflow_id,
                            node_id=nid,
                            status=nstatus,
                            output=noutput,
                            error_message=nerror.get("error") if nerror else None,
                            duration_ms=noutput.get("_duration_ms") if noutput else None,
                            model_used=noutput.get("_model_used") if noutput else None,
                            token_usage=noutput.get("_token_usage", {}).get("total") if noutput and isinstance(noutput.get("_token_usage"), dict) else None,
                        )
                    for nid, noutput in node_outputs.items():
                        if nid not in node_statuses:
                            await self._persist_node_output(
                                workflow_id=workflow_id,
                                node_id=nid,
                                status="completed",
                                output=noutput,
                                duration_ms=noutput.get("_duration_ms"),
                                model_used=noutput.get("_model_used"),
                                token_usage=noutput.get("_token_usage", {}).get("total") if isinstance(noutput.get("_token_usage"), dict) else None,
                            )

                    # 检测新 pending_suggestion（软语义 fail 时追加）
                    # MVP 阶段：suggestion 仅作为建议权，不挂起工作流。
                    # 用户在 final_review 审核时可参考 suggestion 决定是否通过。
                    current_suggestions = delta.get("pending_suggestions")
                    if current_suggestions and len(current_suggestions) > seen_suggestion_count:
                        new_ones = current_suggestions[seen_suggestion_count:]
                        for s in new_ones:
                            await self._persist_pending_suggestion(
                                workflow_id, s
                            )
                        seen_suggestion_count = len(current_suggestions)
        except Exception as e:
            logger.exception(f"[{workflow_id}] graph astream failed: {e}")
            raise

        # ===== 检测是否处于 interrupt 暂停状态 =====
        # 通过 await graph.aget_state(config) 检查 LangGraph 内部状态
        # interrupt_before=["copywrite", "image_gen", "image_review", "final_review", "publish"]
        # - copywrite 前 interrupt：analyze 完成后，用户选方向/调性（resume_workflow resume）
        # - image_gen 前 interrupt：image_plan 完成后，前端卡片编辑器加载 card_draft，用户编辑出图后 inject
        # - image_review 前 interrupt：image_gen 完成后，用户调图片（resume_workflow resume）
        # - final_review 前 interrupt：audit 完成后，手机预览+终审确认
        # - publish 前 interrupt：安全门，用户确认发布
        is_awaiting_direction_choice = False
        is_awaiting_card_editor = False
        is_awaiting_image_review = False
        is_awaiting_final_review = False
        is_awaiting_publish = False
        try:
            graph_state = await graph.aget_state(config)
            # graph_state.next 是 tuple，包含下一个待执行的节点
            next_nodes = getattr(graph_state, "next", None) or ()
            for n in next_nodes:
                if n == "copywrite":
                    is_awaiting_direction_choice = True
                    break
                if n == "image_gen":
                    is_awaiting_card_editor = True
                    break
                if n == "image_review":
                    is_awaiting_image_review = True
                    break
                if n == "final_review":
                    is_awaiting_final_review = True
                    break
                if n == "publish":
                    is_awaiting_publish = True
                    break
            logger.info(
                f"[{workflow_id}] graph state after astream: next={next_nodes}, "
                f"awaiting_direction_choice={is_awaiting_direction_choice}, "
                f"awaiting_card_editor={is_awaiting_card_editor}, "
                f"awaiting_image_review={is_awaiting_image_review}, "
                f"awaiting_final_review={is_awaiting_final_review}, "
                f"awaiting_publish={is_awaiting_publish}"
            )
        except Exception as e:
            logger.warning(f"[{workflow_id}] get graph state failed: {e}")

        if is_awaiting_direction_choice:
            # analyze 完成后暂停，等待用户选方向/调性
            # 推送 SSE 事件告知前端 analyze 已完成，显示方向选择面板
            await sse_bus.publish(
                workflow_id,
                "review_required",
                {
                    "review_node": "copywrite",
                    "review_type": "direction_choice",
                    "message": "分析完成，请选择创作方向",
                },
            )
            logger.info(
                f"[{workflow_id}] workflow paused at copywrite interrupt, "
                f"waiting for user to choose direction"
            )
            await self._pause_workflow(workflow_id)
            return

        if is_awaiting_card_editor:
            # image_plan 完成后暂停，等待用户在卡片编辑器中调整并生成图片
            # 推送 SSE 事件告知前端 image_gen 节点等待用户操作
            # review_node 必须是 "image_gen"，前端才能把 image_gen 节点设为 awaiting_review
            await sse_bus.publish(
                workflow_id,
                "review_required",
                {
                    "review_node": "image_gen",
                    "review_type": "card_editor",
                    "message": "图片规划完成，请在卡片编辑器中调整并生成图片",
                },
            )
            logger.info(
                f"[{workflow_id}] workflow paused at image_gen interrupt, "
                f"waiting for user to edit cards and generate images"
            )
            await self._pause_workflow(workflow_id)
            return

        if is_awaiting_image_review:
            # image_gen 完成后暂停，等待用户调图片
            # 推送 review_required 事件，前端显示图片编辑面板
            await self._emit_review_required(workflow_id, "image_review", graph, config)
            logger.info(
                f"[{workflow_id}] workflow paused at image_review interrupt, "
                f"waiting for user to review images"
            )
            await self._pause_workflow(workflow_id)
            return

        if is_awaiting_final_review:
            # audit 完成后暂停，等待用户在手机预览中终审确认
            await self._emit_review_required(workflow_id, "final_review", graph, config)
            logger.info(
                f"[{workflow_id}] workflow paused at final_review interrupt, "
                f"waiting for user to review in phone preview"
            )
            await self._pause_workflow(workflow_id)
            return

        if is_awaiting_publish:
            # publish 前 interrupt：按 auto_publish 开关决定自动 resume 还是等待手动
            # auto_publish=True（默认）→ 自动 resume，用户无感（行为同加 interrupt 前）
            # auto_publish=False → 推送 review_required(publish)，前端显示"发布"按钮
            model_settings = graph_state.values.get("model_settings", {}) or {}
            auto_publish = model_settings.get("auto_publish", True)
            if auto_publish:
                logger.info(f"[{workflow_id}] publish interrupt + auto_publish=True, auto resuming")
                self._create_background_task(
                    self._resume_graph_safely(workflow_id, graph, config)
                )
            else:
                logger.info(f"[{workflow_id}] publish interrupt + auto_publish=False, waiting for manual publish")
                await self._emit_review_required(workflow_id, "publish", graph, config)
                await self._pause_workflow(workflow_id)
            return

        # 根据 suspended 标记决定终态
        from sqlalchemy import update as sa_update
        from datetime import UTC, datetime as dt

        # 检查是否有节点 ERROR（关键节点失败提前终止）
        has_node_error = any(
            s == "error" for s in all_node_statuses.values()
        )

        if suspended:
            # 软语义 fail → 挂起工作流（30min 计时器由 RecoveryService 启动）
            suspended_until = dt.now(UTC) + timedelta(hours=24)
            await self.db.execute(
                sa_update(Workflow)
                .where(Workflow.id == workflow_id)
                .values(
                    status=WorkflowStatus.SUSPENDED,
                    suspended_until=suspended_until,
                    suspension_reason="软语义判断未通过，等待用户拍板",
                )
            )
            await self.db.commit()
            await sse_bus.publish(
                workflow_id,
                "workflow_suspended",
                {
                    "workflow_id": workflow_id,
                    "reason": "软语义判断未通过，等待用户拍板",
                    "suspended_until": suspended_until.isoformat(),
                },
            )
            logger.info(f"[{workflow_id}] workflow suspended (soft semantic fail)")
            await self._decrement_workflow_count()
        elif has_node_error:
            # 关键节点 ERROR（search 空结果 / image_gen 欠费等）→ 标记 FAILED
            error_nodes = [
                n for n, s in all_node_statuses.items() if s == "error"
            ]
            await self.db.execute(
                sa_update(Workflow)
                .where(Workflow.id == workflow_id)
                .values(
                    status=WorkflowStatus.FAILED,
                    completed_at=dt.now(UTC),
                )
            )
            await self.db.commit()
            await sse_bus.publish(
                workflow_id,
                "workflow_failed",
                {
                    "workflow_id": workflow_id,
                    "error_nodes": error_nodes,
                    "message": f"工作流因节点失败终止: {', '.join(error_nodes)}",
                    "completed_at": dt.now(UTC).isoformat(),
                },
            )
            logger.info(
                f"[{workflow_id}] workflow failed (node error: {error_nodes})"
            )
            await self._decrement_workflow_count()
        else:
            # 标记 workflow 完成
            await self.db.execute(
                sa_update(Workflow)
                .where(Workflow.id == workflow_id)
                .values(
                    status=WorkflowStatus.COMPLETED,
                    completed_at=dt.now(UTC),
                )
            )
            await self.db.commit()

            await sse_bus.publish(
                workflow_id,
                "workflow_completed",
                {
                    "workflow_id": workflow_id,
                    "completed_at": dt.now(UTC).isoformat(),
                },
            )
            logger.info(f"[{workflow_id}] workflow completed")

            # 记录用户级长期记忆（topic_history + copywrite_history + 推断偏好）
            # 失败不阻塞工作流完成
            try:
                from app.services import agent_memory
                # 从 graph state 读取 copywrite 节点输出（用于记忆摘要）
                copywrite_output = None
                try:
                    graph_state = await graph.aget_state(config)
                    node_outputs = (graph_state.values or {}).get("node_outputs", {})
                    copywrite_output = node_outputs.get("copywrite", {})
                except Exception:
                    pass
                await agent_memory.record_workflow_result(
                    user_id=user_id,
                    workflow_id=workflow_id,
                    topic=topic,
                    copywrite_output=copywrite_output,
                    model_settings=model_settings,
                )
            except Exception as mem_err:
                logger.warning(
                    f"[{workflow_id}] record_workflow_result failed: {mem_err}"
                )

            await self._decrement_workflow_count()

    async def _load_account_cookies_for_mcp(
        self, workflow_id: str, account_id: str
    ) -> None:
        """从 DB 加载账号的 cookies，解密后注入到 MCP local client。

        让 search 节点能用已登录的 cookies 调 worker 创建工作会话。
        """
        try:
            from sqlalchemy import select
            from app.db.models import XhsAccount
            from app.crypto.token_crypto import TokenCrypto
            from app.tools.mcp.xhs_client import sync_cookies_to_local_client

            stmt = select(XhsAccount).where(XhsAccount.id == account_id)
            account = await self.db.scalar(stmt)
            if not account:
                logger.warning(f"[{workflow_id}] account {account_id} not found")
                return
            if not account.session_data_encrypted:
                logger.warning(
                    f"[{workflow_id}] account {account_id} has no session cookies"
                )
                return

            crypto = TokenCrypto()
            session_data = crypto.decrypt_dict(account.session_data_encrypted)
            # session_data 是 {"cookies": [list[dict]]}（Playwright export 格式）
            cookies = (
                session_data.get("cookies", [])
                if isinstance(session_data, dict)
                else session_data
            )
            if not cookies:
                logger.warning(
                    f"[{workflow_id}] account {account_id} cookies empty after decrypt"
                )
                return
            sync_cookies_to_local_client(cookies)
            logger.info(
                f"[{workflow_id}] cookies loaded for account {account_id} "
                f"({len(cookies)} items)"
            )
        except Exception as e:
            logger.warning(
                f"[{workflow_id}] load account cookies failed: {e}"
            )

    async def _persist_node_output(
        self,
        workflow_id: str,
        node_id: str,
        status: str,
        output: dict | None = None,
        error_message: str | None = None,
        duration_ms: int | None = None,
        model_used: str | None = None,
        token_usage: int | None = None,
    ) -> None:
        """把节点状态和输出持久化到 workflow_nodes 表。

        LangGraph checkpoint 是主要存储，但重启后可能丢失（MemorySaver）。
        此方法作为数据库层面的持久化备份，保证 get_workflow_nodes 二次兜底
        能从 DB 恢复节点输出数据，让前端卡片能展示已完成节点的结果。
        """
        try:
            from sqlalchemy import update as sa_update
            values: dict[str, Any] = {}
            try:
                values["node_status"] = NodeStatus(status)
            except ValueError:
                values["node_status"] = NodeStatus.PENDING
            if output and isinstance(output, dict):
                safe_output = {k: v for k, v in output.items() if k != "images_base64"}
                if safe_output:
                    values["output_data"] = safe_output
            if error_message:
                values["error_message"] = error_message
            if duration_ms is not None:
                values["duration_ms"] = duration_ms
            if model_used:
                values["model_used"] = model_used
            if token_usage is not None:
                values["token_usage"] = token_usage
            if status in ("completed", "passed"):
                values["completed_at"] = datetime.now(UTC)
            elif status == "running" and not values.get("completed_at"):
                values["started_at"] = datetime.now(UTC)
            if not values:
                return
            result = await self.db.execute(
                sa_update(WorkflowNode)
                .where(
                    WorkflowNode.workflow_id == workflow_id,
                    WorkflowNode.node_key == node_id,
                )
                .values(**values)
            )
            if result.rowcount > 0:
                await self.db.commit()
        except Exception as e:
            logger.warning(f"[{workflow_id}] _persist_node_output failed for {node_id}: {e}")

    async def _persist_pending_suggestion(
        self,
        workflow_id: str,
        suggestion_data: dict[str, Any],
    ) -> None:
        """把软语义 fail 的 suggestion 写入 pending_suggestions 表。

        红线 4.1：结构性恢复必须经用户确认。
        30min 超时计时器由 RecoveryService 在用户调用 confirm/reject 时启动；
        此处仅持久化建议记录。
        """
        try:
            # severity 映射：LLM 输出 low/medium/high，DB 枚举是 info/warning/error
            severity_raw = str(suggestion_data.get("severity", "medium")).lower()
            severity_map = {
                "low": "info",
                "medium": "warning",
                "high": "error",
                # 直接匹配枚举值
                "info": "info",
                "warning": "warning",
                "error": "error",
            }
            severity_str = severity_map.get(severity_raw, "warning")
            try:
                severity = SuggestionSeverity(severity_str)
            except ValueError:
                severity = SuggestionSeverity.warning

            suggestion = PendingSuggestion(
                workflow_id=workflow_id,
                node_id=None,  # 软语义产生的建议不绑定具体 WorkflowNode
                severity=severity,
                suggestion_type=SuggestionType.structural,
                message=str(suggestion_data.get("message", "软语义判断未通过")),
                trace={
                    "source_node": suggestion_data.get("source_node", ""),
                    "suggestions": suggestion_data.get("suggestions", []),
                },
                proposed_action={
                    "target_node": suggestion_data.get("target_node", ""),
                    "action_type": "structural_rollback",
                },
                status=SuggestionStatus.pending,
            )
            self.db.add(suggestion)
            await self.db.commit()
            await self.db.refresh(suggestion)

            # 推送 suggestion_created 事件（前端展示待办）
            await sse_bus.publish(
                workflow_id,
                "suggestion_created",
                {
                    "workflow_id": workflow_id,
                    "suggestion_id": suggestion.id,
                    "severity": severity.value,
                    "message": suggestion.message,
                    "target_node": suggestion_data.get("target_node", ""),
                    "require_user_confirm": True,
                },
            )
            logger.info(
                f"[{workflow_id}] pending_suggestion created: {suggestion.id} "
                f"target={suggestion_data.get('target_node', '')}"
            )
        except Exception as e:
            logger.exception(
                f"[{workflow_id}] persist pending_suggestion failed: {e}"
            )

    async def _emit_review_required(
        self,
        workflow_id: str,
        review_node: str,
        graph: Any,
        config: dict,
    ) -> None:
        """推送 review_required 事件，前端显示审核按钮。

        Args:
            review_node: "image_review" 或 "final_review"
            graph: 已编译的 LangGraph 实例
            config: 包含 thread_id 的配置
        """
        try:
            # 从 graph state 读取上游节点输出，作为审核数据
            graph_state = await graph.aget_state(config)
            state_values = graph_state.values or {}

            node_outputs = state_values.get("node_outputs", {})
            review_data: dict[str, Any] = {
                "workflow_id": workflow_id,
                "review_node": review_node,
                "review_type": "image" if review_node == "image_review" else "final",
            }

            if review_node == "image_review":
                image_gen_output = node_outputs.get("image_gen", {})
                images_base64 = image_gen_output.get("images_base64", []) or []
                review_data.update({
                    # image_gen_node 不输出 image_count 字段，用 images_base64 长度计算
                    # 否则 markdown_card 路径会被误判为 0 张图片
                    "image_count": image_gen_output.get("image_count") or len(images_base64),
                    "style": image_gen_output.get("style", ""),
                    "image_details": image_gen_output.get("image_details", []),
                    # images_base64 通过专门的图片接口获取，避免 SSE payload 过大
                    "has_images": bool(images_base64),
                    "message": "请审核生成的图片",
                })
            elif review_node == "final_review":
                copywrite_output = node_outputs.get("copywrite", {})
                image_gen_output = node_outputs.get("image_gen", {})
                review_data.update({
                    "title": copywrite_output.get("title", ""),
                    "content": copywrite_output.get("content", ""),
                    "tags": copywrite_output.get("tags", []),
                    "has_images": bool(image_gen_output.get("images_base64")),
                    "message": "请审核最终文案",
                })
            elif review_node == "publish":
                # 终审通过后、发布前的手动确认节点
                # auto_publish=False 时触发，前端显示"确认发布"按钮
                # 点击后调 resume_workflow 恢复执行 publish_node
                final_review_output = node_outputs.get("final_review", {})
                copywrite_output = node_outputs.get("copywrite", {})
                image_gen_output = node_outputs.get("image_gen", {})
                review_data.update({
                    "review_type": "publish",
                    "title": final_review_output.get("title") or copywrite_output.get("title", ""),
                    "content": final_review_output.get("content") or copywrite_output.get("content", ""),
                    "tags": copywrite_output.get("tags", []),
                    "has_images": bool(image_gen_output.get("images_base64")),
                    "message": "终审已通过，确认发布到小红书？",
                })

            # 更新 DB：workflow 状态保持 running，但记录 current_node
            from sqlalchemy import update as sa_update
            await self.db.execute(
                sa_update(Workflow)
                .where(Workflow.id == workflow_id)
                .values(current_node_id=review_node)
            )
            await self.db.commit()

            # 推送 review_required 事件
            await sse_bus.publish(
                workflow_id,
                "review_required",
                review_data,
            )
            logger.info(
                f"[{workflow_id}] review_required emitted: node={review_node}"
            )
        except Exception as e:
            logger.exception(
                f"[{workflow_id}] emit review_required failed: {e}"
            )

    async def submit_review(
        self,
        workflow_id: str,
        action: str,
        user_id: str,
        feedback: str = "",
        selected_candidate: str = "",
    ) -> dict[str, Any]:
        """提交人工审核结果，恢复或回退工作流。

        Args:
            workflow_id: 工作流ID
            action: "pass"（通过，resume）或 "reject"（打回，回退到上游节点重新执行）
            user_id: 用户ID
            feedback: 审核反馈（可选）
            selected_candidate: 候选模式下用户选中的 candidate id（如 list_fresh_natural）

        interrupt/resume 机制：
        - action=pass: 调 graph.astream(None, config) resume，工作流继续执行
        - action=reject: 通过 graph.update_state 设置被打回节点为 rejected，
          然后 resume，路由函数根据 rejected 状态走回退路径：
          - image_review reject → image_gen 重新生成图片
          - final_review reject → copywrite 重新生成文案

        关键：必须使用与 execute_graph 相同的 thread_id 才能恢复 checkpoint。
        """
        workflow = await self.get_workflow(workflow_id, user_id)
        if not workflow:
            return {"success": False, "message": "Workflow not found"}

        if action not in ("pass", "reject"):
            return {"success": False, "message": f"Invalid action: {action}"}

        # 推送 review_processed 事件（前端隐藏审核按钮）
        await sse_bus.publish(
            workflow_id,
            "review_processed",
            {"workflow_id": workflow_id, "action": action, "feedback": feedback},
        )

        if action == "reject":
            # 打回：不终止工作流，而是设置被打回节点为 rejected，然后 resume
            # 路由函数会根据 rejected 状态走回退路径：
            # - image_review reject → image_gen 重新生成图片
            # - final_review reject → copywrite 重新生成文案
            if not LANGGRAPH_AVAILABLE:
                return {"success": False, "message": "LangGraph unavailable"}

            graph, _ = await self._get_graph_for_workflow(workflow)
            if graph is None:
                return {"success": False, "message": "Graph build failed"}

            config = {
            "configurable": {"thread_id": workflow_id},
            "recursion_limit": 50,
            "metadata": {"workflow_id": workflow_id},
        }

            # 验证当前确实处于 interrupt 状态，并获取被打回的节点名
            try:
                graph_state = await graph.aget_state(config)
                next_nodes = getattr(graph_state, "next", None) or ()
                if not next_nodes:
                    return {
                        "success": False,
                        "message": f"Workflow not in interrupt state (next={next_nodes})"
                    }
                # interrupt_before 暂停时，next_nodes 包含即将执行的节点
                # （image_review 或 final_review）
                review_node = next_nodes[0]
                logger.info(
                    f"[{workflow_id}] reject from interrupt: next={next_nodes}, "
                    f"review_node={review_node}"
                )
            except Exception as e:
                return {"success": False, "message": f"Get graph state failed: {e}"}

            # 通过 update_state 设置被打回节点状态为 rejected
            # 节点函数执行时会读到这个状态，设置 review_status="rejected"
            # 路由函数看到 non-passed 状态，走回退路径
            from app.agents.graph import NodeStatus
            try:
                await graph.aupdate_state(
                    config,
                    {"node_statuses": {review_node: NodeStatus.REJECTED.value}},
                )
                logger.info(
                    f"[{workflow_id}] update_state OK: "
                    f"{review_node}={NodeStatus.REJECTED.value}"
                )
            except Exception as e:
                logger.exception(f"[{workflow_id}] update_state failed: {e}")
                return {
                    "success": False,
                    "message": f"Update state failed: {e}",
                }

            # 推送节点状态变更事件（前端更新 UI）
            await sse_bus.publish(
                workflow_id,
                "node_status_changed",
                {"node_id": review_node, "status": NodeStatus.REJECTED.value},
            )

            await self._unpause_workflow(workflow_id)

            self._create_background_task(
                self._resume_graph_safely(workflow_id, graph, config)
            )

            logger.info(
                f"[{workflow_id}] workflow rejected, rolling back from {review_node}"
            )
            return {
                "success": True,
                "message": f"Workflow rejected, rolling back from {review_node}",
            }

        # 通过：resume 工作流
        if not LANGGRAPH_AVAILABLE:
            return {"success": False, "message": "LangGraph unavailable"}

        # 使用全局 checkpointer 重新构建 graph（保证与 execute_graph 共享 state）
        graph, _ = await self._get_graph_for_workflow(workflow)
        if graph is None:
            return {"success": False, "message": "Graph build failed"}

        config = {
            "configurable": {"thread_id": workflow_id},
            "recursion_limit": 50,
            "metadata": {"workflow_id": workflow_id},
        }

        # 验证当前确实处于 interrupt 状态，并获取审核节点名
        try:
            graph_state = await graph.aget_state(config)
            next_nodes = getattr(graph_state, "next", None) or ()
            _dlog(f"[{workflow_id}] submit_review(pass) BEFORE update: next={next_nodes}")
            if not next_nodes:
                return {
                    "success": False,
                    "message": f"Workflow not in interrupt state (next={next_nodes})"
                }
            # interrupt_before 暂停时，next_nodes 包含即将执行的节点
            # （image_review 或 final_review）
            review_node = next_nodes[0]
            logger.info(
                f"[{workflow_id}] resume from interrupt: next={next_nodes}, "
                f"review_node={review_node}"
            )
        except Exception as e:
            return {"success": False, "message": f"Get graph state failed: {e}"}

        # ===== 关键：pass 时必须重置审核节点状态为 passed =====
        # 否则如果之前 reject 过，checkpoint 里残留的 rejected 状态会导致
        # image_review_node 读到 rejected → route_after_image_review 又走回退路径
        # → 无限循环 → recursion_limit 触发报错
        from app.agents.graph import NodeStatus
        try:
            update_payload: dict = {
                "node_statuses": {review_node: NodeStatus.PASSED.value},
            }
            # 候选模式：把用户选中的 candidate_id 写入 node_outputs，
            # image_review_node resume 后从这里读取
            if selected_candidate and review_node == "image_review":
                update_payload["node_outputs"] = {
                    "image_review": {"selected_candidate": selected_candidate}
                }
                logger.info(
                    f"[{workflow_id}] update_state (pass) with selected_candidate: "
                    f"{selected_candidate}"
                )
            await graph.aupdate_state(config, update_payload)
            logger.info(
                f"[{workflow_id}] update_state OK (pass): "
                f"{review_node}={NodeStatus.PASSED.value}"
            )
            # 检查 update_state 后 next 的变化
            try:
                gs_after = await graph.aget_state(config)
                next_after = getattr(gs_after, "next", None) or ()
                _dlog(f"[{workflow_id}] submit_review(pass) AFTER update: next={next_after}")
            except Exception as _e:
                _dlog(f"[{workflow_id}] submit_review(pass) get_state after update failed: {_e}")
        except Exception as e:
            logger.exception(f"[{workflow_id}] update_state (pass) failed: {e}")
            return {
                "success": False,
                "message": f"Update state failed: {e}",
            }

        # 推送节点状态变更事件（前端更新 UI）
        await sse_bus.publish(
            workflow_id,
            "node_status_changed",
            {"node_id": review_node, "status": NodeStatus.PASSED.value},
        )

        await self._unpause_workflow(workflow_id)

        self._create_background_task(
            self._resume_graph_safely(workflow_id, graph, config)
        )

        return {"success": True, "message": "Workflow resumed"}

    async def inject_card_images(
        self,
        workflow_id: str,
        images_base64: list[str],
        image_details: list[dict] | None = None,
        style: str = "",
        plan_context: dict | None = None,
        user_id: str = "",
    ) -> dict[str, Any]:
        """前端卡片编辑器出图后，注入图片到 image_gen 节点并 resume 工作流。

        机制：
        - image_plan 完成后，工作流在 image_gen 前 interrupt 暂停
        - 前端 html2canvas 生成图片 base64
        - 调用本方法，把图片写入 state（node_outputs['image_gen']）
        - resume 工作流，image_gen_node 检测到注入的图片直接透传
        - 工作流继续到 image_review 前 interrupt

        必须使用与 execute_graph 相同的 thread_id 才能恢复 checkpoint。
        """
        workflow = await self.get_workflow(workflow_id, user_id)
        if not workflow:
            return {"success": False, "message": "Workflow not found"}

        if not images_base64:
            return {"success": False, "message": "No images provided"}

        if not LANGGRAPH_AVAILABLE:
            return {"success": False, "message": "LangGraph unavailable"}

        graph, _ = await self._get_graph_for_workflow(workflow)
        if graph is None:
            return {"success": False, "message": "Graph build failed"}

        config = {
            "configurable": {"thread_id": workflow_id},
            "recursion_limit": 50,
            "metadata": {"workflow_id": workflow_id},
        }

        # 验证当前处于 interrupt 状态，确定是否允许注入
        # - next 包含 image_gen → 正常首次注入
        # - next 包含 image_review / final_review / publish → 工作流已过 image_gen，允许重新注入
        #   （update_state 覆盖 image_gen 输出 → resume 从当前 interrupt 继续或回退到 image_review）
        try:
            graph_state = await graph.aget_state(config)
            next_nodes = getattr(graph_state, "next", None) or ()
            if not next_nodes:
                return {
                    "success": False,
                    "message": f"Workflow not in interrupt state (next={next_nodes})"
                }
            _RE_INJECT_NODES = {"image_review", "final_review", "publish"}
            is_reinject = "image_gen" not in next_nodes and bool(set(next_nodes) & _RE_INJECT_NODES)
            if "image_gen" not in next_nodes and not is_reinject:
                return {
                    "success": False,
                    "message": f"Not waiting for image_gen (next={next_nodes})"
                }
            if is_reinject:
                logger.info(
                    f"[{workflow_id}] inject_card_images: re-inject at {next_nodes}, "
                    f"will overwrite image_gen output"
                )
            logger.info(
                f"[{workflow_id}] inject_card_images: next={next_nodes}, "
                f"images={len(images_base64)}, reinject={is_reinject}"
            )
        except Exception as e:
            return {"success": False, "message": f"Get graph state failed: {e}"}

        from app.agents.graph import NodeStatus

        # 防御性修复：如果 workflow 之前被 _resume_graph_stream 误判为 completed
        # （image_gen interrupt 未检测到，误进终态判断），这里改回 running，
        # 否则前端轮询检测到 status=completed 会立即停止，导致 inject 后"没反应"。
        from sqlalchemy import update as sa_update
        from datetime import UTC, datetime as dt
        try:
            await self.db.execute(
                sa_update(Workflow)
                .where(Workflow.id == workflow_id)
                .where(Workflow.status.in_([WorkflowStatus.COMPLETED, WorkflowStatus.FAILED]))
                .values(status=WorkflowStatus.RUNNING, completed_at=None)
            )
            await self.db.commit()
        except Exception:
            pass

        # 推送 image_gen running 事件（前端更新 UI）
        await sse_bus.publish(
            workflow_id,
            "node_status_changed",
            {"node_id": "image_gen", "status": NodeStatus.RUNNING.value},
        )

        # 把注入的图片写入 state
        try:
            update_payload = {
                "node_outputs": {
                    "image_gen": {
                        "images_base64": images_base64,
                        "image_count": len(images_base64),
                        "image_details": image_details or [],
                        "style": style or "卡片编辑器",
                        "plan_context": plan_context or {},
                    }
                },
            }
            if is_reinject:
                # re-inject: 用 as_node="image_gen" 声明这是 image_gen 的输出
                # LangGraph 会认为 image_gen 刚完成，resume 后从 image_review 重新开始
                await graph.aupdate_state(config, update_payload, as_node="image_gen")
                logger.info(
                    f"[{workflow_id}] inject_card_images re-inject update_state OK "
                    f"(as_node=image_gen): {len(images_base64)} images"
                )
            else:
                await graph.aupdate_state(config, update_payload)
                logger.info(
                    f"[{workflow_id}] inject_card_images update_state OK: "
                    f"{len(images_base64)} images"
                )
        except Exception as e:
            logger.exception(f"[{workflow_id}] inject_card_images update_state failed: {e}")
            return {"success": False, "message": f"Update state failed: {e}"}

        # 异步 resume
        _dlog(f"[{workflow_id}] inject_card_images: about to resume, is_reinject={is_reinject}")
        await self._unpause_workflow(workflow_id)
        if is_reinject:
            # re-inject: 推送 image_gen completed + image_review awaiting_review
            await sse_bus.publish(
                workflow_id,
                "node_status_changed",
                {"node_id": "image_gen", "status": NodeStatus.COMPLETED.value},
            )
            await sse_bus.publish(
                workflow_id,
                "node_status_changed",
                {"node_id": "image_review", "status": NodeStatus.AWAITING_REVIEW.value},
            )
            _dlog(f"[{workflow_id}] inject_card_images: creating _resume_graph_safely task (re-inject)")
            self._create_background_task(
                self._resume_graph_safely(workflow_id, graph, config)
            )
        else:
            # 首次注入: resume 后 image_gen_node 会检测到注入的图片直接透传
            _dlog(f"[{workflow_id}] inject_card_images: creating _resume_graph_safely task (first inject)")
            self._create_background_task(
                self._resume_graph_safely(workflow_id, graph, config)
            )

        return {
            "success": True,
            "message": f"Injected {len(images_base64)} images, workflow resumed",
            "image_count": len(images_base64),
        }

    async def _resume_graph_safely(
        self,
        workflow_id: str,
        graph: Any,
        config: dict,
    ) -> None:
        """安全 resume graph 执行（异步 task）。

        与 _execute_graph_safely 类似，使用独立 db session。
        resume 后可能再次 interrupt（final_review 前），需要递归处理。
        """
        logger.info(f"[{workflow_id}] _resume_graph_safely STARTED")
        _dlog(f"[{workflow_id}] _resume_graph_safely STARTED")
        from app.db.session import AsyncSessionLocal
        try:
            async with AsyncSessionLocal() as bg_db:
                original_db = self.db
                self.db = bg_db
                try:
                    await self._resume_graph_stream(workflow_id, graph, config)
                    logger.info(f"[{workflow_id}] _resume_graph_safely COMPLETED")
                    _dlog(f"[{workflow_id}] _resume_graph_safely COMPLETED")
                except Exception as e:
                    logger.exception(f"[{workflow_id}] graph resume failed: {e}")
                    _dlog(f"[{workflow_id}] _resume_graph_safely FAILED: {e}")
                    await sse_bus.publish(
                        workflow_id,
                        "workflow_error",
                        {
                            "workflow_id": workflow_id,
                            "message": f"Graph resume failed: {e}",
                            "fatal": True,
                        },
                    )
                    await self._decrement_workflow_count()
                finally:
                    self.db = original_db
        except Exception as outer_e:
            _dlog(f"[{workflow_id}] _resume_graph_safely OUTER FAIL (AsyncSessionLocal?): {outer_e}")
            logger.exception(f"[{workflow_id}] _resume_graph_safely outer failed: {outer_e}")

    async def _resume_graph_stream(
        self,
        workflow_id: str,
        graph: Any,
        config: dict,
    ) -> None:
        """执行 graph.astream(None, config) resume，处理事件流。

        resume 后可能再次 interrupt（image_review 通过后 → final_review 前），
        需要检测并推送 review_required。
        """
        seen_suggestion_count = 0
        suspended = False
        all_node_statuses: dict[str, str] = {}

        # 获取当前 state 中已有的 suggestion 数量（避免重复写）
        try:
            graph_state = await graph.aget_state(config)
            state_values = graph_state.values or {}
            existing_suggestions = state_values.get("pending_suggestions", [])
            seen_suggestion_count = len(existing_suggestions)
        except Exception:
            pass

        _dlog(f"[{workflow_id}] _resume_graph_stream: starting astream(None)...")
        chunk_count = 0
        async for chunk in graph.astream(None, config):
            for node_key, delta in chunk.items():
                if not isinstance(delta, dict):
                    continue
                node_statuses = delta.get("node_statuses", {})
                node_outputs = delta.get("node_outputs", {})
                all_node_statuses.update(node_statuses)
                _dlog(f"[{workflow_id}] _resume_graph_stream CHUNK #{chunk_count}: node_key={node_key}, "
                      f"node_statuses={node_statuses}, output_keys={list(node_outputs.keys())}, "
                      f"current_node={delta.get('current_node')}")
                chunk_count += 1
                if node_statuses or node_outputs:
                    await sse_bus.publish(
                        workflow_id,
                        "workflow_snapshot",
                        {
                            "workflow_id": workflow_id,
                            "current_node": delta.get("current_node", node_key),
                            "node_statuses": node_statuses,
                            "node_outputs_keys": list(node_outputs.keys()),
                            # 补 status 字段，让前端 workflow_snapshot case 能触发 currentWorkflow 更新
                            "status": "running",
                        },
                    )

                # 持久化节点状态和输出到 workflow_nodes 表
                for nid, nstatus in node_statuses.items():
                    noutput = node_outputs.get(nid)
                    nerror = delta.get("node_errors", {}).get(nid)
                    await self._persist_node_output(
                        workflow_id=workflow_id,
                        node_id=nid,
                        status=nstatus,
                        output=noutput,
                        error_message=nerror.get("error") if nerror else None,
                        duration_ms=noutput.get("_duration_ms") if noutput else None,
                        model_used=noutput.get("_model_used") if noutput else None,
                        token_usage=noutput.get("_token_usage", {}).get("total") if noutput and isinstance(noutput.get("_token_usage"), dict) else None,
                    )
                for nid, noutput in node_outputs.items():
                    if nid not in node_statuses:
                        await self._persist_node_output(
                            workflow_id=workflow_id,
                            node_id=nid,
                            status="completed",
                            output=noutput,
                            duration_ms=noutput.get("_duration_ms"),
                            model_used=noutput.get("_model_used"),
                            token_usage=noutput.get("_token_usage", {}).get("total") if isinstance(noutput.get("_token_usage"), dict) else None,
                        )

                current_suggestions = delta.get("pending_suggestions")
                if current_suggestions and len(current_suggestions) > seen_suggestion_count:
                    new_ones = current_suggestions[seen_suggestion_count:]
                    for s in new_ones:
                        await self._persist_pending_suggestion(workflow_id, s)
                    seen_suggestion_count = len(current_suggestions)
                    # MVP 阶段：suggestion 不挂起工作流，继续到 final_review 让用户审核

        # ===== 再次检测是否处于 interrupt =====
        # 与 execute_graph 保持一致：检测 copywrite（方向选择）、image_gen（卡片编辑器）、
        # image_review（图片审核）、final_review（手机预览终审）、publish（安全门）五种 interrupt 点。
        _dlog(f"[{workflow_id}] _resume_graph_stream: astream ended, total_chunks={chunk_count}, "
              f"all_node_statuses={all_node_statuses}")
        is_awaiting_direction_choice = False
        is_awaiting_card_editor = False
        is_awaiting_image_review = False
        is_awaiting_final_review = False
        is_awaiting_publish = False
        try:
            graph_state = await graph.aget_state(config)
            next_nodes = getattr(graph_state, "next", None) or ()
            for n in next_nodes:
                if n == "copywrite":
                    is_awaiting_direction_choice = True
                    break
                if n == "image_gen":
                    is_awaiting_card_editor = True
                    break
                if n == "image_review":
                    is_awaiting_image_review = True
                    break
                if n == "final_review":
                    is_awaiting_final_review = True
                    break
                if n == "publish":
                    is_awaiting_publish = True
                    break
            logger.info(
                f"[{workflow_id}] graph state after resume: next={next_nodes}, "
                f"awaiting_direction_choice={is_awaiting_direction_choice}, "
                f"awaiting_card_editor={is_awaiting_card_editor}, "
                f"awaiting_image_review={is_awaiting_image_review}, "
                f"awaiting_final_review={is_awaiting_final_review}, "
                f"awaiting_publish={is_awaiting_publish}"
            )
            _dlog(f"[{workflow_id}] _resume_graph_stream: post-astream next={next_nodes}, "
                  f"awaiting_direction_choice={is_awaiting_direction_choice}, "
                  f"awaiting_card_editor={is_awaiting_card_editor}, "
                  f"awaiting_image_review={is_awaiting_image_review}, "
                  f"awaiting_final_review={is_awaiting_final_review}, "
                  f"awaiting_publish={is_awaiting_publish}")
        except Exception as e:
            logger.warning(f"[{workflow_id}] get graph state after resume failed: {e}")

        if is_awaiting_direction_choice:
            await sse_bus.publish(
                workflow_id,
                "review_required",
                {
                    "review_node": "copywrite",
                    "review_type": "direction_choice",
                    "message": "分析完成，请选择创作方向",
                },
            )
            logger.info(f"[{workflow_id}] workflow paused at copywrite interrupt after resume")
            await self._pause_workflow(workflow_id)
            return

        if is_awaiting_card_editor:
            await sse_bus.publish(
                workflow_id,
                "review_required",
                {
                    "review_node": "image_gen",
                    "review_type": "card_editor",
                    "message": "图片规划完成，请在卡片编辑器中调整并生成图片",
                },
            )
            logger.info(f"[{workflow_id}] workflow paused at image_gen interrupt after resume")
            await self._pause_workflow(workflow_id)
            return

        if is_awaiting_image_review:
            await self._emit_review_required(workflow_id, "image_review", graph, config)
            await self._pause_workflow(workflow_id)
            return

        if is_awaiting_final_review:
            await self._emit_review_required(workflow_id, "final_review", graph, config)
            logger.info(f"[{workflow_id}] workflow paused at final_review interrupt after resume")
            await self._pause_workflow(workflow_id)
            return

        if is_awaiting_publish:
            model_settings = (graph_state.values or {}).get("model_settings", {}) or {}
            auto_publish = model_settings.get("auto_publish", True)
            if auto_publish:
                logger.info(f"[{workflow_id}] publish interrupt + auto_publish=True, auto resuming")
                self._create_background_task(
                    self._resume_graph_safely(workflow_id, graph, config)
                )
            else:
                logger.info(f"[{workflow_id}] publish interrupt + auto_publish=False, waiting for manual publish")
                await self._emit_review_required(workflow_id, "publish", graph, config)
                await self._pause_workflow(workflow_id)
            return

        # 进入终态判断
        _dlog(f"[{workflow_id}] _resume_graph_stream: entering terminal state judgment, "
              f"all_node_statuses={all_node_statuses}")
        from sqlalchemy import update as sa_update
        from datetime import UTC, datetime as dt

        has_node_error = any(s == "error" for s in all_node_statuses.values())

        if suspended:
            suspended_until = dt.now(UTC) + timedelta(hours=24)
            await self.db.execute(
                sa_update(Workflow)
                .where(Workflow.id == workflow_id)
                .values(
                    status=WorkflowStatus.SUSPENDED,
                    suspended_until=suspended_until,
                    suspension_reason="软语义判断未通过，等待用户拍板",
                )
            )
            await self.db.commit()
            await sse_bus.publish(
                workflow_id,
                "workflow_suspended",
                {
                    "workflow_id": workflow_id,
                    "reason": "软语义判断未通过，等待用户拍板",
                    "suspended_until": suspended_until.isoformat(),
                },
            )
            await self._decrement_workflow_count()
        elif has_node_error:
            error_nodes = [n for n, s in all_node_statuses.items() if s == "error"]
            await self.db.execute(
                sa_update(Workflow)
                .where(Workflow.id == workflow_id)
                .values(status=WorkflowStatus.FAILED, completed_at=dt.now(UTC))
            )
            await self.db.commit()
            await sse_bus.publish(
                workflow_id,
                "workflow_failed",
                {
                    "workflow_id": workflow_id,
                    "error_nodes": error_nodes,
                    "message": f"工作流因节点失败终止: {', '.join(error_nodes)}",
                    "completed_at": dt.now(UTC).isoformat(),
                },
            )
            await self._decrement_workflow_count()
        else:
            await self.db.execute(
                sa_update(Workflow)
                .where(Workflow.id == workflow_id)
                .values(status=WorkflowStatus.COMPLETED, completed_at=dt.now(UTC))
            )
            await self.db.commit()
            await sse_bus.publish(
                workflow_id,
                "workflow_completed",
                {
                    "workflow_id": workflow_id,
                    "completed_at": dt.now(UTC).isoformat(),
                },
            )
            logger.info(f"[{workflow_id}] workflow completed (after resume)")

            # 记录用户级长期记忆（resume 路径完成，例如 final_review 通过后）
            # 从 graph state 读取 user_id/topic/model_settings/copywrite_output
            try:
                from app.services import agent_memory
                mem_state = await graph.aget_state(config)
                mem_values = mem_state.values or {}
                mem_user_id = str(mem_values.get("user_id", ""))
                mem_topic = str(mem_values.get("topic", ""))
                mem_model_settings = mem_values.get("model_settings", {}) or {}
                mem_copywrite = (mem_values.get("node_outputs", {}) or {}).get("copywrite", {})
                if mem_user_id and mem_topic:
                    await agent_memory.record_workflow_result(
                        user_id=mem_user_id,
                        workflow_id=workflow_id,
                        topic=mem_topic,
                        copywrite_output=mem_copywrite,
                        model_settings=mem_model_settings,
                    )
            except Exception as mem_err:
                logger.warning(
                    f"[{workflow_id}] record_workflow_result (resume) failed: {mem_err}"
                )

            await self._decrement_workflow_count()

    async def get_workflow(self, workflow_id: str, user_id: str | None = None) -> Workflow | None:
        """获取工作流详情。"""
        conditions = [Workflow.id == workflow_id]
        if user_id:
            conditions.append(Workflow.user_id == user_id)
        stmt = select(Workflow).where(*conditions)
        return await self.db.scalar(stmt)

    async def pause_workflow(self, workflow_id: str, user_id: str) -> dict[str, Any]:
        """暂停工作流。"""
        workflow = await self.get_workflow(workflow_id, user_id)
        if not workflow:
            return {"success": False, "message": "Workflow not found"}

        workflow.status = "paused"
        await self.db.commit()

        await sse_bus.publish(
            workflow_id,
            "workflow_paused",
            {"workflow_id": workflow_id},
        )

        return {"success": True, "message": "Workflow paused"}

    async def resume_workflow(
        self,
        workflow_id: str,
        user_id: str,
        selected_direction: int | None = None,
        direction_note: str = "",
    ) -> dict[str, Any]:
        """恢复工作流（从中断点继续执行 graph）。

        用于 analyze 等非审核节点的 interrupt_before 暂停后恢复。
        审核节点（image_review/final_review）用 submit_review 恢复（需要设置 PASSED）。
        本方法直接 astream(None) 让 graph 继续执行下一个节点。
        selected_direction / direction_note 仅在 copywrite 前暂停点生效。
        """
        workflow = await self.get_workflow(workflow_id, user_id)
        if not workflow:
            return {"success": False, "message": "Workflow not found"}

        if not LANGGRAPH_AVAILABLE:
            return {"success": False, "message": "LangGraph unavailable"}

        graph, _ = await self._get_graph_for_workflow(workflow)
        if graph is None:
            return {"success": False, "message": "Graph build failed"}

        config = {
            "configurable": {"thread_id": workflow_id},
            "recursion_limit": 50,
            "metadata": {"workflow_id": workflow_id},
        }

        # 验证当前确实处于 interrupt 状态
        try:
            graph_state = await graph.aget_state(config)
            next_nodes = getattr(graph_state, "next", None) or ()
            if not next_nodes:
                return {
                    "success": False,
                    "message": f"Workflow not in interrupt state (next={next_nodes})"
                }
            logger.info(
                f"[{workflow_id}] resume_workflow from interrupt: next={next_nodes}"
            )
        except Exception as e:
            return {"success": False, "message": f"Get graph state failed: {e}"}

        # copywrite 前的暂停点：先把用户选择写入 analyze 输出，再 resume。
        # node_outputs 使用 merge reducer，不会覆盖已有分析结果。
        if next_nodes and next_nodes[0] == "copywrite":
            recommendation_count = 0
            analyze_values = (getattr(graph_state, "values", None) or {}).get("node_outputs", {})
            recommendations = ((analyze_values.get("analyze") or {}).get("insights") or {}).get("recommendations")
            if isinstance(recommendations, list):
                recommendation_count = len(recommendations)
            chosen_index = selected_direction if selected_direction is not None else 0
            if recommendation_count and not 0 <= chosen_index < recommendation_count:
                return {
                    "success": False,
                    "message": f"Invalid direction index: {chosen_index} (0-{recommendation_count - 1})",
                }
            try:
                await graph.aupdate_state(
                    config,
                    {
                        "node_outputs": {
                            "analyze": {
                                "selected_direction": chosen_index,
                                "direction_note": (direction_note or "").strip(),
                            }
                        }
                    },
                )
            except Exception as e:
                logger.exception(f"[{workflow_id}] update direction choice failed: {e}")
                return {"success": False, "message": f"Update direction choice failed: {e}"}

        await self._unpause_workflow(workflow_id)

        await sse_bus.publish(
            workflow_id,
            "workflow_resumed",
            {"workflow_id": workflow_id},
        )

        self._create_background_task(
            self._resume_graph_safely(workflow_id, graph, config)
        )

        return {"success": True, "message": "Workflow resumed"}


    async def cancel_workflow(self, workflow_id: str, user_id: str) -> dict[str, Any]:
        """用户主动取消工作流（区别于系统 terminate）。
        
        将工作流标记为 cancelled，断开 SSE 连接，清理后台任务。
        与 terminate 的区别：
        - terminate：系统/管理员终止
        - cancel：用户主动取消（刷新/重新搜索等场景）
        """
        workflow = await self.get_workflow(workflow_id, user_id)
        if not workflow:
            return {"success": False, "message": "Workflow not found"}

        was_paused = workflow.status == WorkflowStatus.PAUSED

        workflow.status = WorkflowStatus.CANCELLED
        await self.db.commit()

        await sse_bus.publish(
            workflow_id,
            "workflow_cancelled",
            {"workflow_id": workflow_id, "message": "Workflow cancelled by user"},
        )

        if not was_paused:
            await self._decrement_workflow_count()

        return {"success": True, "message": "Workflow cancelled"}
    async def terminate_workflow(self, workflow_id: str, user_id: str) -> dict[str, Any]:
        """终止工作流。"""
        workflow = await self.get_workflow(workflow_id, user_id)
        if not workflow:
            return {"success": False, "message": "Workflow not found"}

        was_paused = workflow.status == WorkflowStatus.PAUSED

        workflow.status = "terminated"
        await self.db.commit()

        await sse_bus.publish(
            workflow_id,
            "workflow_error",
            {"workflow_id": workflow_id, "message": "Workflow terminated by user"},
        )

        if not was_paused:
            await self._decrement_workflow_count()

        return {"success": True, "message": "Workflow terminated"}

    async def rollback_workflow(
        self,
        workflow_id: str,
        user_id: str,
        target_node: str,
    ) -> dict[str, Any]:
        """回退到指定节点。"""
        workflow = await self.get_workflow(workflow_id, user_id)
        if not workflow:
            return {"success": False, "message": "Workflow not found"}

        # TODO: 使用 LangGraph checkpoint 回退
        # 需要从 PostgresSaver 加载 checkpoint 并恢复状态

        await sse_bus.publish(
            workflow_id,
            "workflow_rollback",
            {"workflow_id": workflow_id, "target_node": target_node},
        )

        return {"success": True, "message": f"Rolled back to {target_node}"}

    async def update_node_output(
        self,
        workflow_id: str,
        node_id: str,
        user_output: dict,
        user_id: str,
    ) -> dict[str, Any]:
        """人工编辑节点输出，覆盖 LangGraph state 中的 node_outputs[node_id]。

        用于 copywrite 节点完成后用户编辑 title/content/tags，
        后续 image_plan/image_gen 节点会读到编辑后的内容。

        机制：graph.update_state 触发 _merge_dict reducer，
        把 node_outputs[node_id] 替换为合并后的完整 output。

        Args:
            workflow_id: 工作流ID
            node_id: 节点ID（如 "copywrite"）
            user_output: 用户编辑的字段（如 {title, content, tags}），与现有 output 合并
            user_id: 用户ID
        """
        workflow = await self.get_workflow(workflow_id, user_id)
        if not workflow:
            return {"success": False, "message": "Workflow not found"}

        if not LANGGRAPH_AVAILABLE:
            return {"success": False, "message": "LangGraph unavailable"}

        graph, _ = await self._get_graph_for_workflow(workflow)
        if graph is None:
            return {"success": False, "message": "Graph build failed"}

        config = {
            "configurable": {"thread_id": workflow_id},
            "recursion_limit": 50,
            "metadata": {"workflow_id": workflow_id},
        }

        try:
            graph_state = await graph.aget_state(config)
            # 获取现有 node_outputs，合并用户编辑的字段
            existing_outputs = (graph_state.values or {}).get("node_outputs", {})
            existing_node_output = dict(existing_outputs.get(node_id, {}))
            # 用户传来的字段覆盖现有字段（保留元数据如 _model_used/_duration_ms）
            merged_output = {**existing_node_output, **user_output, "_edited": True}

            # update_state 触发 _merge_dict reducer：
            # 把 node_outputs[node_id] 的值替换为 merged_output
            await graph.aupdate_state(
                config,
                {"node_outputs": {node_id: merged_output}},
            )
            logger.info(
                f"[{workflow_id}] node_output updated: node={node_id}, "
                f"fields={list(user_output.keys())}"
            )

            # 推送 SSE 事件，前端即时刷新展示
            await sse_bus.publish(
                workflow_id,
                "node_output_updated",
                {
                    "workflow_id": workflow_id,
                    "node_id": node_id,
                    "output": merged_output,
                },
            )

            return {
                "success": True,
                "message": f"Node {node_id} output updated",
                "output": merged_output,
            }
        except Exception as e:
            logger.exception(f"[{workflow_id}] update_node_output failed: {e}")
            return {"success": False, "message": f"Update failed: {e}"}


def get_workflow_service(db: AsyncSession) -> WorkflowService:
    """获取工作流服务实例。"""
    return WorkflowService(db)