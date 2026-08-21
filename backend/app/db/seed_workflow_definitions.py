"""预置内置工作流模板到数据库。

在应用 lifespan 启动时调用，确保 DB 中有可用的内置模板。
使用 upsert 逻辑：按 name+is_builtin 匹配，存在则跳过，不存在则插入。
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

BUILTIN_TEMPLATES: list[dict[str, Any]] = [
    {
        "name": "完整创作流程",
        "description": "搜索 → 分析 → 文案 → 图片规划 → 生图 → 审核 → 合规 → 终审 → 发布",
        "icon": "🎯",
        "category": "full_pipeline",
        "graph_definition": {
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
                {"id": "e1", "source": "node_1", "target": "node_2"},
                {"id": "e2", "source": "node_2", "target": "node_3"},
                {"id": "e3", "source": "node_3", "target": "node_4"},
                {"id": "e4", "source": "node_4", "target": "node_5"},
                {"id": "e5", "source": "node_5", "target": "node_6"},
                {"id": "e6", "source": "node_6", "target": "node_7"},
                {"id": "e7", "source": "node_7", "target": "node_8"},
                {"id": "e8", "source": "node_8", "target": "node_9"},
            ],
        },
    },
    {
        "name": "仅搜索分析",
        "description": "搜索热点 → 要素分析，不生成内容",
        "icon": "🔍",
        "category": "search_only",
        "graph_definition": {
            "nodes": [
                {"id": "node_1", "type": "search", "config": {}, "position": {"x": 50, "y": 50}},
                {"id": "node_2", "type": "analyze", "config": {}, "position": {"x": 250, "y": 50}},
            ],
            "edges": [
                {"id": "e1", "source": "node_1", "target": "node_2"},
            ],
        },
    },
    {
        "name": "快速图文",
        "description": "搜索 → 文案 → 图片规划 → 生图 → 发布（跳过审核）",
        "icon": "⚡",
        "category": "quick_publish",
        "graph_definition": {
            "nodes": [
                {"id": "node_1", "type": "search", "config": {}, "position": {"x": 50, "y": 50}},
                {"id": "node_2", "type": "copywrite", "config": {}, "position": {"x": 250, "y": 50}},
                {"id": "node_3", "type": "image_plan", "config": {}, "position": {"x": 450, "y": 50}},
                {"id": "node_4", "type": "image_gen", "config": {}, "position": {"x": 650, "y": 50}},
                {"id": "node_5", "type": "publish", "config": {}, "position": {"x": 850, "y": 50}},
            ],
            "edges": [
                {"id": "e1", "source": "node_1", "target": "node_2"},
                {"id": "e2", "source": "node_2", "target": "node_3"},
                {"id": "e3", "source": "node_3", "target": "node_4"},
                {"id": "e4", "source": "node_4", "target": "node_5"},
            ],
        },
    },
    {
        "name": "纯搜索",
        "description": "仅执行搜索，获取热点数据",
        "icon": "🔎",
        "category": "search_raw",
        "graph_definition": {
            "nodes": [
                {"id": "node_1", "type": "search", "config": {}, "position": {"x": 50, "y": 50}},
            ],
            "edges": [],
        },
    },
    {
        "name": "搜索加文案",
        "description": "搜索 → 分析 → 文案生成，不生成图片",
        "icon": "✍️",
        "category": "search_copywrite",
        "graph_definition": {
            "nodes": [
                {"id": "node_1", "type": "search", "config": {}, "position": {"x": 50, "y": 50}},
                {"id": "node_2", "type": "analyze", "config": {}, "position": {"x": 250, "y": 50}},
                {"id": "node_3", "type": "copywrite", "config": {}, "position": {"x": 450, "y": 50}},
            ],
            "edges": [
                {"id": "e1", "source": "node_1", "target": "node_2"},
                {"id": "e2", "source": "node_2", "target": "node_3"},
            ],
        },
    },
    {
        "name": "文案加发布",
        "description": "文案生成 → 发布（纯文字笔记）",
        "icon": "📝",
        "category": "copywrite_publish",
        "graph_definition": {
            "nodes": [
                {"id": "node_1", "type": "copywrite", "config": {}, "position": {"x": 50, "y": 50}},
                {"id": "node_2", "type": "publish", "config": {}, "position": {"x": 250, "y": 50}},
            ],
            "edges": [
                {"id": "e1", "source": "node_1", "target": "node_2"},
            ],
        },
    },
]


async def seed_builtin_workflow_definitions(db: AsyncSession) -> dict[str, int]:
    """将内置模板 upsert 到 DB。

    Returns:
        {"seeded": N, "skipped": M} — seeded 为新插入数，skipped 为已存在跳过数
    """
    from app.db.models import WorkflowDefinition, WorkflowDefinitionStatus

    seeded = 0
    skipped = 0

    for template in BUILTIN_TEMPLATES:
        stmt = select(WorkflowDefinition).where(
            WorkflowDefinition.name == template["name"],
            WorkflowDefinition.is_builtin == True,
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            skipped += 1
            continue

        definition = WorkflowDefinition(
            name=template["name"],
            description=template["description"],
            icon=template["icon"],
            category=template["category"],
            graph_definition=template["graph_definition"],
            is_builtin=True,
            is_public=True,
            status=WorkflowDefinitionStatus.ACTIVE,
            user_id="system",
            tags=["builtin"],
            version=1,
            usage_count=0,
            success_count=0,
        )
        db.add(definition)
        seeded += 1

    if seeded > 0:
        await db.commit()

    logger.info(f"[seed] Builtin workflow definitions: {seeded} seeded, {skipped} skipped")
    return {"seeded": seeded, "skipped": skipped}