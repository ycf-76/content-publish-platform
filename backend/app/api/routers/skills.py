"""Skill 列表查询 API。

供前端右侧工作区动态拉取各节点可用的 Skill 清单，
渲染模型/风格下拉框。第三方 Skill 通过 backend/skills/ 目录扫描自动加载。
"""

from fastapi import APIRouter, Query

from app.agents.skills.registry import SkillRegistry
from app.api.schemas.common import StandardResponse

router = APIRouter(prefix="/api/skills", tags=["skills"])


def _ensure_builtin_skills_registered() -> None:
    """确保内置 Skill 模块已导入并注册。

    内置 Skill 用 @register 装饰器在模块 import 时注册到 SkillRegistry。
    但 Python 模块是懒加载的，如果不显式 import，@register 不会执行。
    这里统一触发 4 个内置 Skill 模块的 import，保证 /api/skills 能返回完整列表。
    """
    import importlib

    # 内置 Skill 模块（import 即触发 @register 注册）
    # image_gen 节点只保留 xhs_blueprint（动态布局生成），旧 skill 文件已删除
    builtin_modules = [
        "app.agents.skills.analyze_skill",
        "app.agents.skills.copywrite_builder",
        "app.agents.skills.audit_skill",
        "app.agents.skills.blueprint_skill",
    ]
    for mod_name in builtin_modules:
        importlib.import_module(mod_name)


@router.get("")
async def list_skills(
    node_type: str | None = Query(default=None, description="按节点类型过滤（如 copywrite/image_gen/analyze/audit）"),
) -> StandardResponse[dict[str, list[dict]]]:
    """列出所有可用的 Skill（按 node_type 分组）。

    可选 query 参数 node_type：只返回指定节点的 Skill 列表。
    例如 GET /api/skills?node_type=copywrite 只返回文案类 Skill。

    返回结构：
    {
      "copywrite": [
        {"node_type": "copywrite", "name": "lively_girl", "display_name": "活泼少女风", "description": "...", "default_config": {}},
        ...
      ],
      "image_gen": [...],
      "analyze": [...],
      "audit": [...]
    }

    内置 Skill 在接口调用时显式触发 import 注册。
    第三方 Skill（backend/skills/ 目录下的 .py 文件）会在首次调用时自动扫描注册。
    """
    # 1. 触发内置 Skill 注册（import 即注册）
    _ensure_builtin_skills_registered()

    # 2. 触发第三方 Skill 扫描（懒加载，首次调用时执行）
    registry = SkillRegistry.instance()
    registry.scan_third_party()

    if node_type:
        # 单节点查询：返回 {node_type: [...]}
        skills_list = registry.list_by_node(node_type)
        return StandardResponse(data={node_type: skills_list})

    # 全量查询
    return StandardResponse(data=registry.list_all())
