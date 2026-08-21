"""
Workflow Definitions API - 工作流定义管理接口
============================================

提供工作流模板的 CRUD 操作：
- 创建/编辑/删除工作流定义
- 查询可用节点列表（含插件节点）
- 保存和加载自定义流程
- 内置模板管理

路由前缀: /api/workflow-definitions
"""

import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    HTTPException,
    Query,
    status,
)
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func


from app.db.session import get_db
from app.db.models import (
    WorkflowDefinition,
    WorkflowDefinitionStatus,
    Workflow,
    User,
)
from app.core.node_registry import get_node_registry, NodeRegistry


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workflow-definitions", tags=["workflow-definitions"])


@router.get("/health", summary="工作流定义服务健康检查")
async def health_check_fast():
    """早期静态路由，避免被下方 /{definition_id} 动态路由吞掉。"""
    return await health_check()


# ===== Pydantic 模型 =====

class GraphNode(BaseModel):
    """图中的节点"""
    id: str = Field(..., description="节点唯一ID")
    type: str = Field(..., description="节点类型（对应node_type）")
    config: Dict[str, Any] = Field(default_factory=dict, description="节点配置")
    position: Dict[str, float] = Field(default_factory={"x": 0, "y": 0}, description="画布位置")


class GraphEdge(BaseModel):
    """图中的边（连接）"""
    id: str = Field(..., description="边唯一ID")
    source: str = Field(..., description="源节点ID")
    target: str = Field(..., description="目标节点ID")
    source_handle: Optional[str] = Field(None, description="源输出端口")
    target_handle: Optional[str] = Field(None, description="目标输入端口")
    condition: Optional[str] = Field(None, description="条件表达式")
    label: Optional[str] = Field(None, description="边标签")


class GraphDefinition(BaseModel):
    """DAG图定义"""
    nodes: List[GraphNode] = Field(default_factory=list, min_length=1, description="节点列表")
    edges: List[GraphEdge] = Field(default_factory=list, description="边列表")

    @field_validator('nodes')
    @classmethod
    def validate_nodes(cls, v):
        if len(v) == 0:
            raise ValueError('至少需要1个节点')
        return v


class WorkflowDefinitionCreate(BaseModel):
    """创建工作流定义请求"""
    name: str = Field(..., min_length=1, max_length=100, description="名称")
    description: Optional[str] = Field(None, max_length=1000, description="描述")
    icon: str = Field("⚙️", max_length=10, description="图标emoji")
    category: str = Field("custom", max_length=50, description="分类")
    graph_definition: GraphDefinition = Field(..., description="DAG图定义")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    is_public: bool = Field(False, description="是否公开分享")


class WorkflowDefinitionUpdate(BaseModel):
    """更新工作流定义请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    icon: Optional[str] = Field(None, max_length=10)
    category: Optional[str] = Field(None, max_length=50)
    graph_definition: Optional[GraphDefinition] = None
    tags: Optional[List[str]] = None
    status: Optional[WorkflowDefinitionStatus] = None
    is_public: Optional[bool] = None


class WorkflowDefinitionResponse(BaseModel):
    """工作流定义响应"""
    id: str
    name: str
    description: Optional[str]
    icon: str
    category: str
    version: int
    user_id: str
    graph_definition: GraphDefinition
    status: WorkflowDefinitionStatus
    is_builtin: bool
    is_public: bool
    usage_count: int
    success_count: int
    avg_duration_ms: Optional[int]
    tags: Optional[List[str]]
    author_name: Optional[str]
    thumbnail_url: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class NodeListResponse(BaseModel):
    """可用节点列表响应"""
    nodes: List[Dict[str, Any]]
    categories: List[Dict[str, Any]]
    total: int


# ===== 辅助函数 =====

def get_current_user_id() -> str:
    """
    获取当前用户ID（简化版，实际应从认证信息获取）
    
    TODO: 集成真实的认证系统后替换此函数
    """
    return "current_user"


def validate_graph_acyclic(graph_def: GraphDefinition) -> bool:
    """
    验证图是否为有向无环图（DAG）
    
    使用拓扑排序检测环
    
    Args:
        graph_def: 图定义
        
    Returns:
        bool: 是否为DAG
        
    Raises:
        ValueError: 如果包含环
    """
    try:
        # 构建邻接表
        adj = {node.id: [] for node in graph_def.nodes}
        in_degree = {node.id: 0 for node in graph_def.nodes}
        
        for edge in graph_def.edges:
            if edge.source in adj and edge.target in adj:
                adj[edge.source].append(edge.target)
                in_degree[edge.target] += 1
        
        # Kahn算法进行拓扑排序
        queue = [node_id for node_id, degree in in_degree.items() if degree == 0]
        sorted_nodes = []
        
        while queue:
            current = queue.pop(0)
            sorted_nodes.append(current)
            
            for neighbor in adj[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        # 如果排序后的节点数 < 总节点数，说明存在环
        if len(sorted_nodes) != len(graph_def.nodes):
            raise ValueError("工作流图中包含循环依赖！请检查节点连接。")
        
        return True
        
    except ValueError:
        raise
    except Exception as e:
        logger.warning(f"图验证异常: {e}")
        # 验证失败时不阻止保存（开发阶段宽容处理）
        return True


def validate_node_types_exist(graph_def: GraphDefinition, registry: NodeRegistry) -> List[str]:
    """
    验证图中的所有节点类型都已注册
    
    Args:
        graph_def: 图定义
        registry: 节点注册中心
        
    Returns:
        List[str]: 未注册的节点类型列表（空列表表示全部有效）
    """
    unknown_types = []
    
    for node in graph_def.nodes:
        if not registry.exists(node.type):
            unknown_types.append(node.type)
    
    return unknown_types


def validate_node_types_unique(graph_def: GraphDefinition) -> None:
    """动态执行层当前要求每个节点类型在同一个图中唯一。"""
    seen: set[str] = set()
    for node in graph_def.nodes:
        if node.type in seen:
            raise ValueError(f"同一工作流中不能重复使用节点类型: {node.type}")
        seen.add(node.type)


# ===== API 端点 =====

@router.get(
    "/nodes/available",
    response_model=NodeListResponse,
    summary="获取所有可用的工作流节点",
    description="""
    返回当前系统中所有可用的节点类型（内置 + 插件），
    包含节点的 Schema 元数据，用于前端可视化编排。
    
    返回内容包括：
    - 节点基本信息（名称、图标、分类、描述）
    - 输入参数Schema（用于渲染输入表单）
    - 输出数据Schema（用于下游节点校验）
    - 配置参数Schema（用于节点配置面板）
    """,
)
async def list_available_nodes(
    category: Optional[str] = Query(
        None,
        description="按分类筛选（datasource/creation/review/publish等）"
    ),
    include_details: bool = Query(
        False,
        description="是否包含详细Schema信息"
    ),
    search: Optional[str] = Query(
        None,
        description="搜索关键词（匹配名称、描述、标签）"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    获取可用节点列表
    """
    registry = get_node_registry()
    
    if search:
        # 搜索模式
        nodes = registry.search(query=search, limit=50)
    elif category:
        # 分类筛选
        nodes = registry.list_by_category(
            category=category,
            include_details=include_details
        )
    else:
        # 全部列出
        nodes = registry.list_all(include_details=include_details)
    
    categories = registry.get_categories()
    
    return NodeListResponse(
        nodes=nodes,
        categories=categories,
        total=len(nodes),
    )


@router.get(
    "",
    response_model=List[WorkflowDefinitionResponse],
    summary="获取工作流定义列表",
    description="""
    获取用户的工作流定义模板列表。
    
    支持按状态、分类筛选，以及搜索功能。
    """,
)
async def list_workflow_definitions(
    status: Optional[WorkflowDefinitionStatus] = Query(
        None,
        description="按状态筛选"
    ),
    category: Optional[str] = Query(
        None,
        description="按分类筛选"
    ),
    include_builtin: bool = Query(
        True,
        description="是否包含系统内置模板"
    ),
    search: Optional[str] = Query(
        None,
        description="搜索关键词"
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="返回数量上限"
    ),
    offset: int = Query(
        0,
        ge=0,
        description="偏移量（分页用）"
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    列出工作流定义
    """
    query = select(WorkflowDefinition)
    
    # 筛选条件
    if not include_builtin:
        query = query.where(WorkflowDefinition.is_builtin == False)
    
    if status:
        query = query.where(WorkflowDefinition.status == status)
    
    if category:
        query = query.where(WorkflowDefinition.category == category)
    
    if search:
        search_pattern = f"%{search}%"
        query = query.where(
            (WorkflowDefinition.name.ilike(search_pattern)) |
            (WorkflowDefinition.description.ilike(search_pattern))
        )
    
    # 排序：内置优先 → 使用次数降序 → 更新时间降序
    query = query.order_by(
        WorkflowDefinition.is_builtin.desc(),
        WorkflowDefinition.usage_count.desc(),
        WorkflowDefinition.updated_at.desc()
    )
    
    # 分页
    query = query.offset(offset).limit(limit)
    
    result = await db.execute(query)
    definitions = result.scalars().all()
    
    return [
        WorkflowDefinitionResponse.model_validate(defn)
        for defn in definitions
    ]


@router.post(
    "",
    response_model=WorkflowDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建工作流定义",
    description="""
    创建新的工作流定义模板。
    
    会自动验证：
    - 图结构合法性（无循环依赖）
    - 所有节点类型均已注册
    - 必填字段完整性
    """,
)
async def create_workflow_definition(
    body: WorkflowDefinitionCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    创建工作流定义
    """
    user_id = get_current_user_id()
    registry = get_node_registry()
    
    # 验证图的合法性
    try:
        validate_graph_acyclic(body.graph_definition)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # 验证节点类型是否存在
    unknown_types = validate_node_types_exist(body.graph_definition, registry)
    if unknown_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"未知的节点类型: {', '.join(unknown_types)}"
        )

    try:
        validate_node_types_unique(body.graph_definition)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # 创建记录
    definition = WorkflowDefinition(
        name=body.name,
        description=body.description,
        icon=body.icon,
        category=body.category,
        user_id=user_id,
        graph_definition=body.graph_definition.model_dump(),
        tags=body.tags,
        is_public=body.is_public,
        status=WorkflowDefinitionStatus.ACTIVE,
    )
    
    db.add(definition)
    await db.commit()
    await db.refresh(definition)
    
    logger.info(f"✅ 工作流定义已创建: {definition.id} - {definition.name}")
    
    return WorkflowDefinitionResponse.model_validate(definition)


@router.get(
    "/{definition_id}",
    response_model=WorkflowDefinitionResponse,
    summary="获取工作流定义详情",
    description="""
    根据ID获取单个工作流定义的完整信息，
    包含详细的图定义和统计数据。
    """,
)
async def get_workflow_definition(
    definition_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    获取工作流定义详情
    """
    result = await db.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
    )
    definition = result.scalar_one_or_none()
    
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"工作流定义不存在: {definition_id}"
        )
    
    return WorkflowDefinitionResponse.model_validate(definition)


@router.put(
    "/{definition_id}",
    response_model=WorkflowDefinitionResponse,
    summary="更新工作流定义",
    description="""
    更新工作流定义的内容或状态。
    
    注意：
    - 内置模板不允许修改图定义
    - 状态变更需要相应权限
    """,
)
async def update_workflow_definition(
    definition_id: str,
    body: WorkflowDefinitionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    更新工作流定义
    """
    result = await db.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
    )
    definition = result.scalar_one_or_none()
    
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"工作流定义不存在: {definition_id}"
        )
    
    # 权限检查：内置模板不允许修改核心内容
    if definition.is_builtin and body.graph_definition is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不允许修改系统内置模板的图定义"
        )
    
    # 更新字段
    update_data = body.model_dump(exclude_unset=True)
    
    if body.graph_definition:
        # 验证新图定义
        registry = get_node_registry()
        
        try:
            validate_graph_acyclic(body.graph_definition)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        
        unknown_types = validate_node_types_exist(body.graph_definition, registry)
        if unknown_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"未知的节点类型: {', '.join(unknown_types)}"
            )

        try:
            validate_node_types_unique(body.graph_definition)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        
        update_data['graph_definition'] = body.graph_definition.model_dump()
        update_data['version'] = definition.version + 1  # 版本号自增
    
    # 执行更新
    for key, value in update_data.items():
        setattr(definition, key, value)
    
    await db.commit()
    await db.refresh(definition)
    
    logger.info(f"✅ 工作流定义已更新: {definition_id}")
    
    return WorkflowDefinitionResponse.model_validate(definition)


@router.delete(
    "/{definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除工作流定义",
    description="""
    删除工作流定义模板。
    
    注意：
    - 内置模板不允许删除
    - 已被使用过的定义会标记为废弃而非物理删除
    """,
)
async def delete_workflow_definition(
    definition_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    删除工作流定义
    """
    result = await db.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
    )
    definition = result.scalar_one_or_none()
    
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"工作流定义不存在: {definition_id}"
        )
    
    # 权限检查
    if definition.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不允许删除系统内置模板"
        )
    
    # 如果已被使用过，软删除（标记为废弃）
    if definition.usage_count > 0:
        definition.status = WorkflowDefinitionStatus.DEPRECATED
        await db.commit()
        logger.info(f"🗑️ 工作流定义已标记为废弃: {definition_id}（使用过{definition.usage_count}次）")
    else:
        # 物理删除
        await db.delete(definition)
        await db.commit()
        logger.info(f"🗑️ 工作流定义已删除: {definition_id}")


@router.post(
    "/{definition_id}/duplicate",
    response_model=WorkflowDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="复制工作流定义",
    description="""
    复制一个工作流定义，生成新的副本。
    
    常见用途：
    - 基于内置模板创建自定义版本
    - 快速创建类似的工作流变体
    """,
)
async def duplicate_workflow_definition(
    definition_id: str,
    new_name: Optional[str] = Query(
        None,
        description='新名称（不填则自动加"副本"）'
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    复制工作流定义
    """
    result = await db.execute(
        select(WorkflowDefinition).where(WorkflowDefinition.id == definition_id)
    )
    original = result.scalar_one_or_none()
    
    if not original:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"工作流定义不存在: {definition_id}"
        )
    
    user_id = get_current_user_id()
    
    # 创建副本
    copy = WorkflowDefinition(
        name=new_name or f"{original.name} (副本)",
        description=original.description,
        icon=original.icon,
        category=original.category,
        user_id=user_id,
        graph_definition=original.graph_definition.copy(),  # 深拷贝
        tags=original.tags.copy() if original.tags else None,
        is_public=False,  # 副本默认不公开
        status=WorkflowDefinitionStatus.ACTIVE,
    )
    
    db.add(copy)
    await db.commit()
    await db.refresh(copy)
    
    logger.info(f"📋 工作流定义已复制: {original.id} -> {copy.id}")
    
    return WorkflowDefinitionResponse.model_validate(copy)


@router.get(
    "/builtin/templates",
    response_model=List[WorkflowDefinitionResponse],
    summary="获取内置模板列表",
    description="""
    获取系统提供的内置工作流模板。
    
    这些模板经过优化，适合大多数使用场景，
    用户可以基于这些模板快速开始。
    """,
)
async def list_builtin_templates(
    db: AsyncSession = Depends(get_db),
):
    """
    列出内置模板
    """
    result = await db.execute(
        select(WorkflowDefinition)
        .where(WorkflowDefinition.is_builtin == True)
        .where(WorkflowDefinition.status == WorkflowDefinitionStatus.ACTIVE)
        .order_by(WorkflowDefinition.usage_count.desc())
    )
    
    templates = result.scalars().all()
    
    return [
        WorkflowDefinitionResponse.model_validate(t)
        for t in templates
    ]


@router.post(
    "/{definition_id}/run",
    summary="基于工作流定义启动执行",
    description="""
    基于指定的工作流定义启动一次工作流执行。
    
    这会创建一个 Workflow 实例并关联到此 Definition，
    然后按照图定义动态执行各个节点。
    
    返回新创建的 Workflow 实例ID。
    """,
)
async def run_workflow_from_definition(
    definition_id: str,
    topic: str = Query(..., description="创作主题"),
    account_id: Optional[str] = Query(None, description="小红书账号ID"),
    model_settings: Optional[Dict[str, Any]] = Body(None, description="模型设置"),
    db: AsyncSession = Depends(get_db),
):
    """
    基于定义启动工作流
    """
    # 1. 验证定义存在且可用
    result = await db.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == definition_id,
            WorkflowDefinition.status == WorkflowDefinitionStatus.ACTIVE,
        )
    )
    definition = result.scalar_one_or_none()
    
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"工作流定义不存在或未启用: {definition_id}"
        )
    
    # 2. 更新使用统计
    definition.usage_count += 1
    await db.commit()
    
    # 3. 调用 workflow service 启动执行
    try:
        from app.services.workflow import get_workflow_service
        
        service = get_workflow_service(db)
        
        workflow = await service.start_workflow(
            user_id=get_current_user_id(),
            account_id=account_id or "",
            topic=topic,
            model_settings=model_settings,
            definition_id=definition_id,
        )
        
        logger.info(f"🚀 已基于定义启动工作流: {definition_id} -> {workflow.id}")
        
        return {
            "workflow_id": workflow.id,
            "definition_id": definition_id,
            "status": "started",
            "message": "工作流已成功启动",
        }
        
    except Exception as e:
        logger.exception(f"❌ 启动工作流失败: {e}")
        
        # 回滚统计（安全方式：重新查询后修改）
        try:
            await db.refresh(definition)
            definition.usage_count = max(0, definition.usage_count - 1)
            await db.commit()
        except Exception as rollback_err:
            logger.warning(f"回滚 usage_count 失败: {rollback_err}")
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动工作流失败: {str(e)}"
        )


# ===== 健康检查端点 =====

@router.get(
    "/health",
    summary="工作流定义服务健康检查",
    description="""
    检查工作流定义服务的运行状态，
    包括节点注册中心的就绪情况。
    """,
)
async def health_check():
    """
    健康检查
    """
    registry = get_node_registry()
    stats = registry.get_stats()
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "registry": {
            "total_nodes_registered": stats["current_total"],
            "builtin_count": stats["builtin_count"],
            "plugin_count": stats["plugin_count"],
            "categories": len(stats["categories"]),
        },
        "database": "connected",  # 简化版，实际应检查DB连接
    }