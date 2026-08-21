"""
Phase 2: 动态工作流编排支持

Revision ID: 002
Revises: 001
Create Date: 2026-08-16

功能：
1. 新增 workflow_definitions 表（工作流定义模板）
2. 新增 workflow_edges 表（节点连接关系）
3. workflows 表新增字段：definition_id, execution_mode

向后兼容：
- definition_id 可为 NULL，NULL 时使用默认固定流程
- 现有代码无需修改即可继续工作
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite, postgresql


revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    执行升级迁移
    """
    
    # ===== 1. 创建工作流定义表 =====
    op.create_table(
        'workflow_definitions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, comment='工作流名称'),
        sa.Column('description', sa.Text(), nullable=True, comment='描述'),
        sa.Column('icon', sa.String(10), server_default='⚙️', comment='图标emoji'),
        sa.Column('category', sa.String(50), server_default='custom', comment='分类'),
        sa.Column('version', sa.Integer(), server_default='1', comment='版本号'),
        sa.Column('user_id', sa.String(50), nullable=False, index=True, comment='创建者ID'),
        
        # DAG图定义（JSON）
        sa.Column(
            'graph_definition',
            sa.JSON(),
            nullable=False,
            comment='DAG图定义（nodes + edges）'
        ),
        
        # 状态和可见性
        sa.Column(
            'status',
            sa.Enum('draft', 'active', 'archived', 'deprecated', name='wf_def_status'),
            server_default='draft',
            nullable=False,
            comment='状态'
        ),
        sa.Column('is_builtin', sa.Boolean(), server_default='0', comment='是否内置模板'),
        sa.Column('is_public', sa.Boolean(), server_default='0', comment='是否公开分享'),
        
        # 统计
        sa.Column('usage_count', sa.Integer(), server_default='0', comment='使用次数'),
        sa.Column('success_count', sa.Integer(), server_default='0', comment='成功执行次数'),
        sa.Column('avg_duration_ms', sa.Integer(), nullable=True, comment='平均执行时长(ms)'),
        
        # 元数据
        sa.Column('tags', sa.JSON(), nullable=True, comment='标签列表'),
        sa.Column('author_name', sa.String(100), nullable=True, comment='作者显示名'),
        sa.Column('thumbnail_url', sa.String(500), nullable=True, comment='缩略图URL'),
        
        # 时间戳
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now()
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now()
        ),
    )
    
    # 添加索引
    op.create_index(
        'ix_workflow_definitions_user_id',
        'workflow_definitions',
        ['user_id']
    )
    op.create_index(
        'ix_workflow_definitions_category',
        'workflow_definitions',
        ['category']
    )
    op.create_index(
        'ix_workflow_definitions_status',
        'workflow_definitions',
        ['status']
    )
    
    print("✅ 已创建 workflow_definitions 表")
    
    
    # ===== 2. 创建工作流边关系表 =====
    op.create_table(
        'workflow_edges',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column(
            'workflow_id',
            sa.String(36),
            sa.ForeignKey('workflows.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
            comment='所属工作流实例ID'
        ),
        sa.Column(
            'source_node_id',
            sa.String(36),
            sa.ForeignKey('workflow_nodes.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
            comment='源节点ID'
        ),
        sa.Column(
            'target_node_id',
            sa.String(36),
            sa.ForeignKey('workflow_nodes.id', ondelete='CASCADE'),
            nullable=False,
            index=True,
            comment='目标节点ID'
        ),
        sa.Column('source_handle', sa.String(100), nullable=True, comment='源输出端口标识'),
        sa.Column('target_handle', sa.String(100), nullable=True, comment='目标输入端口标识'),
        sa.Column('condition', sa.Text(), nullable=True, comment='条件表达式'),
        sa.Column('label', sa.String(100), nullable=True, comment='边标签'),
        sa.Column('data_mapping', sa.JSON(), nullable=True, comment='数据映射规则'),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now()
        ),
    )
    
    print("✅ 已创建 workflow_edges 表")
    
    
    # ===== 3. 修改 workflows 表，添加新字段 =====
    
    # 添加 definition_id 字段（关联工作流定义，可为空）
    op.add_column(
        'workflows',
        sa.Column(
            'definition_id',
            sa.String(36),
            sa.ForeignKey('workflow_definitions.id', ondelete='SET NULL'),
            nullable=True,
            index=True,
            comment='使用的工作流定义ID（NULL=使用默认流程）'
        )
    )
    
    # 添加 execution_mode 字段
    op.add_column(
        'workflows',
        sa.Column(
            'execution_mode',
            sa.String(20),
            server_default='sequential',
            comment='执行模式：sequential/dynamic'
        )
    )
    
    print("✅ 已修改 workflows 表（新增 definition_id, execution_mode）")
    
    
    # ===== 4. 插入默认的工作流定义模板 =====
    
    # 定义默认的9节点顺序流水线
    default_graph_definition = {
        "nodes": [
            {"id": "node_1", "type": "search", "config": {}, "position": {"x": 50, "y": 50}},
            {"id": "node_2", "type": "analyze", "config": {}, "position": {"x": 250, "y": 50}},
            {"id": "node_3", "type": "copywrite", "config": {}, "position": {"x": 450, "y": 50}},
            {"id": "node_4", "type": "image_plan", "config": {}, "position": {"x": 650, "y": 50}},
            {"id": "node_5", "type": "image_gen", "config": {}, "position": {"x": 850, "y": 50}},
            {"id": "node_6", "type": "image_review", "config": {}, "position": {"x": 1050, "y": 50}},
            {"id": "node_7", "type": "audit", "config": {}, "position": {"x": 1250, "y": 50}},
            {"id": "node_8", "type": "final_review", "config": {}, "position": {"x": 1450, "y": 50}},
            {"id": "node_9", "type": "publish", "config": {}, "position": {"x": 1650, "y": 50}},
        ],
        "edges": [
            {"id": "edge_1", "source": "node_1", "target": "node_2"},
            {"id": "edge_2", "source": "node_2", "target": "node_3"},
            {"id": "edge_3", "source": "node_3", "target": "node_4"},
            {"id": "edge_4", "source": "node_4", "target": "node_5"},
            {"id": "edge_5", "source": "node_5", "target": "node_6"},
            {"id": "edge_6", "source": "node_6", "target": "node_7"},
            {"id": "edge_7", "source": "node_7", "target": "node_8"},
            {"id": "edge_8", "source": "node_8", "target": "node_9"},
        ]
    }
    
    op.execute("""
        INSERT INTO workflow_definitions (
            id, name, description, icon, category, version,
            user_id, graph_definition, status, is_builtin,
            usage_count, success_count, created_at, updated_at
        ) VALUES (
            'default-full-workflow',
            '🎯 完整创作流程（默认）',
            '标准的AI内容创作全流程：搜索→分析→文案→图片规划→生图→审核→合规→终审→发布',
            '🎯',
            'builtin',
            1,
            'system',
            :graph_def,
            'active',
            1,
            0,
            0,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        )
    """, {
        'graph_def': sa.text("'{}'".format(str(default_graph_definition).replace("'", "\"")))
    })
    
    print("✅ 已插入默认工作流模板")
    
    print("\n" + "=" * 60)
    print("✅ Phase 2 迁移完成！动态工作流编排支持已启用")
    print("=" * 60)


def downgrade() -> None:
    """
    回滚迁移
    """
    
    # 删除默认模板数据
    op.execute("DELETE FROM workflow_definitions WHERE id = 'default-full-workflow'")
    
    # 删除边关系表
    op.drop_table('workflow_edges')
    
    # 删除工作流定义表
    op.drop_table('workflow_definitions')
    
    # 从 workflows 表删除新字段
    op.drop_column('workflows', 'definition_id')
    op.drop_column('workflows', 'execution_mode')
    
    print("✅ 已回滚 Phase 2 迁移")