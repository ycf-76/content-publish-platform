"""Skill 列表查询 + 注册 API。

供前端右侧工作区动态拉取各节点可用的 Skill 清单，
渲染模型/风格下拉框。第三方 Skill 通过 backend/skills/ 目录扫描自动加载。
支持通过上传 .py 文件动态注册第三方 Skill。
"""

import importlib
import importlib.util
import logging
import sys
import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.tools.registry import SkillRegistry, ensure_builtin_skills_registered
from app.api.deps import get_current_user
from app.api.schemas.common import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "skills"


class SkillRegisterResult(BaseModel):
    filename: str
    skill_name: str
    node_type: str
    display_name: str
    description: str


def _ensure_builtin_skills_registered() -> None:
    """确保内置 Skill 模块已导入并注册。

    内置 Skill 用 @register 装饰器在模块 import 时注册到 SkillRegistry。
    但 Python 模块是懒加载的，如果不显式 import，@register 不会执行。
    这里统一触发内置 Skill 模块的 import，保证 /api/skills 能返回完整列表。
    """
    ensure_builtin_skills_registered()


@router.get("")
async def list_skills(
    node_type: str | None = Query(default=None, description="按节点类型过滤（如 copywrite/image_gen/analyze/audit）"),
    user_id: str = Depends(get_current_user),
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


@router.post("/register", response_model=StandardResponse[SkillRegisterResult])
async def register_skill(
    file: UploadFile = File(..., description="Skill Python 文件（.py）"),
    user_id: str = Depends(get_current_user),
) -> StandardResponse[SkillRegisterResult]:
    """上传 .py 文件注册第三方 Skill。

    文件保存到 backend/skills/ 目录，动态 import 并注册到 SkillRegistry。
    文件内须定义 Skill 子类并用 @register 装饰器注册。
    """
    if not file.filename or not file.filename.endswith(".py"):
        raise HTTPException(status_code=400, detail="仅支持 .py 文件")

    filename = file.filename
    target_path = SKILLS_DIR / filename

    content = await file.read()
    if len(content) > 64 * 1024:
        raise HTTPException(status_code=400, detail="文件不能超过 64KB")

    try:
        code = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码须为 UTF-8")

    safety_keywords = ["os.system", "subprocess", "eval(", "exec(", "__import__", "shutil.rmtree"]
    for kw in safety_keywords:
        if kw in code:
            raise HTTPException(status_code=400, detail=f"安全限制：代码包含禁止的关键字 '{kw}'")

    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(content)

    _ensure_builtin_skills_registered()
    registry = SkillRegistry.instance()

    before = set()
    for skills_map in registry._skills.values():
        before.update(skills_map.keys())

    module_name = f"_third_party_skill_{target_path.stem}"
    try:
        if module_name in sys.modules:
            del sys.modules[module_name]
        spec = importlib.util.spec_from_file_location(module_name, target_path)
        if spec is None or spec.loader is None:
            raise ValueError(f"cannot load module: {target_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    except Exception as e:
        if target_path.exists():
            target_path.unlink()
        tb = traceback.format_exc()
        logger.error(f"[register_skill] failed to load {filename}: {tb}")
        raise HTTPException(status_code=422, detail=f"加载失败：{e}")

    after = set()
    for skills_map in registry._skills.values():
        after.update(skills_map.keys())

    new_names = after - before
    if not new_names:
        if target_path.exists():
            target_path.unlink()
        raise HTTPException(
            status_code=422,
            detail="文件加载成功但未注册任何 Skill（请确保使用了 @register 装饰器）",
        )

    registered_name = next(iter(new_names))
    skill_cls = None
    for skills_map in registry._skills.values():
        if registered_name in skills_map:
            skill_cls = skills_map[registered_name]
            break

    if skill_cls is None:
        raise HTTPException(status_code=500, detail="注册成功但无法找到 Skill 类")

    result = SkillRegisterResult(
        filename=filename,
        skill_name=skill_cls.name,
        node_type=skill_cls.node_type,
        display_name=skill_cls.display_name or skill_cls.name,
        description=skill_cls.description,
    )
    return StandardResponse(data=result, message=f"Skill '{skill_cls.name}' 注册成功")


@router.delete("/{node_type}/{skill_name}", response_model=StandardResponse[str])
async def unregister_skill(
    node_type: str,
    skill_name: str,
    user_id: str = Depends(get_current_user),
) -> StandardResponse[str]:
    """注销第三方 Skill 并删除对应文件。

    内置 Skill（app/agents/skills/ 下的）不可删除。
    """
    _ensure_builtin_skills_registered()
    registry = SkillRegistry.instance()

    skill_cls = registry.get(node_type, skill_name)
    if skill_cls is None:
        raise HTTPException(status_code=404, detail=f"Skill '{node_type}.{skill_name}' 不存在")

    module_file = getattr(skill_cls, "__module__", "")
    if not module_file.startswith("_third_party_skill_"):
        raise HTTPException(status_code=403, detail="内置 Skill 不可删除")

    source_file = getattr(skill_cls, "__module__", None)
    if source_file and source_file in sys.modules:
        mod = sys.modules[source_file]
        file_path = getattr(mod, "__file__", None)
        if file_path and Path(file_path).exists():
            Path(file_path).unlink()
            logger.info(f"[unregister_skill] deleted {file_path}")

    if node_type in registry._skills and skill_name in registry._skills[node_type]:
        del registry._skills[node_type][skill_name]
        if not registry._skills[node_type]:
            del registry._skills[node_type]

    return StandardResponse(data=skill_name, message=f"Skill '{skill_name}' 已注销")