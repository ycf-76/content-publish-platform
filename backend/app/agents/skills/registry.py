"""Skill 注册表 + 第三方插件扫描加载器。

架构：
- 全局单例 SkillRegistry，按 (node_type, skill_name) 索引 Skill 子类
- 内置 Skill 在模块导入时显式注册（@register 装饰器或 register() 调用）
- 第三方 Skill 通过扫描 backend/skills/ 目录自动加载
- 节点运行时调用 get_skill(node_type, skill_name) 加载对应实现

第三方 Skill 开发约定：
1. 在 backend/skills/ 目录下创建 .py 文件（如 my_copywrite.py）
2. 文件内定义 Skill 子类，声明 node_type + name + display_name
3. 在文件末尾用 @register 装饰器注册（或调用 SkillRegistry.instance().register(MySkill)）
4. 重启后端即可生效，无需修改 app/ 内任何代码

示例第三方 Skill：

    # backend/skills/my_copywrite.py
    from app.agents.skills.base import Skill
    from app.agents.skills.registry import register

    @register
    class PoeticCopywriteSkill(Skill):
        node_type = "copywrite"
        name = "poetic"
        display_name = "诗意文案"
        description = "诗意化的文案风格，适合文艺类内容"

        async def execute(self, inputs):
            # 自定义实现
            return {"title": "...", "content": "...", "tags": [...]}
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

from app.agents.skills.base import Skill

logger = logging.getLogger(__name__)


BUILTIN_SKILL_MODULES = (
    "app.agents.skills.analyze_skill",
    "app.agents.skills.copywrite_builder",
    "app.agents.skills.audit_skill",
    "app.agents.skills.blueprint_skill",
    "app.agents.skills.trending_search",
    "app.agents.skills.vl_analyze",
    "app.agents.skills.xhs_search",
    "app.agents.skills.xhs_publish",
)


def ensure_builtin_skills_registered() -> None:
    """确保内置 Skill 模块已导入并完成 @register。"""
    for module_name in BUILTIN_SKILL_MODULES:
        importlib.import_module(module_name)


class SkillRegistry:
    """全局 Skill 注册表（单例）。

    索引结构：_skills[node_type][skill_name] = SkillClass
    同一个 node_type 下可注册多个 Skill 实现，运行时按 skill_name 路由。
    """

    def __init__(self) -> None:
        # _skills[node_type][skill_name] = SkillClass
        self._skills: dict[str, dict[str, type[Skill]]] = {}
        # 标记第三方扫描是否已执行（避免重复扫描）
        self._third_party_scanned: bool = False

    @classmethod
    def instance(cls) -> SkillRegistry:
        """获取全局单例。"""
        global _GLOBAL_REGISTRY
        if _GLOBAL_REGISTRY is None:
            _GLOBAL_REGISTRY = SkillRegistry()
        return _GLOBAL_REGISTRY

    def register(self, skill_cls: type[Skill]) -> type[Skill]:
        """注册一个 Skill 子类。

        也可作为装饰器使用：@registry.register

        校验：
        - 必须是 Skill 子类
        - 必须声明 node_type 和 name
        - 同 (node_type, name) 重复注册时覆盖旧值（热更新场景）
        """
        if not isinstance(skill_cls, type) or not issubclass(skill_cls, Skill):
            raise TypeError(f"register() expects Skill subclass, got {skill_cls!r}")
        node_type = skill_cls.node_type
        skill_name = skill_cls.name
        if not node_type or not skill_name:
            raise ValueError(
                f"Skill {skill_cls.__name__} must declare non-empty "
                f"node_type and name (got node_type={node_type!r}, name={skill_name!r})"
            )

        self._skills.setdefault(node_type, {})
        existing = self._skills[node_type].get(skill_name)
        if existing is not None and existing is not skill_cls:
            logger.info(
                f"[SkillRegistry] override existing skill: "
                f"{node_type}.{skill_name} {existing.__name__} -> {skill_cls.__name__}"
            )
        self._skills[node_type][skill_name] = skill_cls
        logger.debug(
            f"[SkillRegistry] registered: {node_type}.{skill_name} "
            f"-> {skill_cls.__name__}"
        )
        return skill_cls

    def get(self, node_type: str, skill_name: str) -> type[Skill] | None:
        """按 (node_type, skill_name) 获取 Skill 子类。未找到返回 None。"""
        return self._skills.get(node_type, {}).get(skill_name)

    def get_default(self, node_type: str) -> type[Skill] | None:
        """获取某 node_type 下第一个注册的 Skill（作为默认回退）。"""
        skills_map = self._skills.get(node_type)
        if not skills_map:
            return None
        # 返回第一个（按注册顺序），调用方需要时可以指定更精确的默认逻辑
        return next(iter(skills_map.values()))

    def list_by_node(self, node_type: str) -> list[dict[str, Any]]:
        """列出某 node_type 下所有 Skill 的元数据（供前端渲染下拉框）。"""
        skills_map = self._skills.get(node_type, {})
        return [cls.metadata() for cls in skills_map.values()]

    def list_all(self) -> dict[str, list[dict[str, Any]]]:
        """列出所有 node_type 下的所有 Skill 元数据。"""
        return {
            node_type: [cls.metadata() for cls in skills_map.values()]
            for node_type, skills_map in self._skills.items()
        }

    def find_by_name(self, name: str) -> list[type[Skill]]:
        """跨 node_type 按 skill name 查找所有匹配项。"""
        matches: list[type[Skill]] = []
        for skills_map in self._skills.values():
            skill_cls = skills_map.get(name)
            if skill_cls is not None:
                matches.append(skill_cls)
        return matches

    def scan_third_party(self, force: bool = False) -> int:
        """扫描 backend/skills/ 目录，自动加载第三方 Skill 模块。

        约定：
        - 目录：与 app/ 同级的下的 skills/ 目录（即 backend/skills/）
        - 每个 .py 文件作为一个模块导入
        - 模块内通过 @register 装饰器或 register() 调用完成注册
        - 子目录视为包（含 __init__.py 才会被导入）

        Args:
            force: True 时强制重新扫描（即使已扫描过）

        Returns:
            本次新加载的模块数量
        """
        if self._third_party_scanned and not force:
            return 0

        # 定位 backend/skills/ 目录（与 app/ 同级）
        # __file__ = backend/app/agents/skills/registry.py
        # 上溯 4 层：registry.py -> skills -> agents -> app -> backend
        backend_root = Path(__file__).resolve().parent.parent.parent.parent
        skills_dir = backend_root / "skills"

        if not skills_dir.exists():
            logger.info(f"[SkillRegistry] third-party skills dir not found: {skills_dir}")
            self._third_party_scanned = True
            return 0

        logger.info(f"[SkillRegistry] scanning third-party skills: {skills_dir}")
        loaded = 0
        for entry in sorted(skills_dir.iterdir()):
            # 跳过 __ 开头的文件/目录（__init__.py / __pycache__）
            if entry.name.startswith("__"):
                continue
            # 跳过非 .py 文件和非目录
            if entry.is_file() and not entry.name.endswith(".py"):
                continue
            # 子目录必须有 __init__.py 才作为包导入
            if entry.is_dir() and not (entry / "__init__.py").exists():
                continue

            module_name = self._load_module(entry)
            if module_name:
                loaded += 1

        self._third_party_scanned = True
        logger.info(f"[SkillRegistry] third-party scan done, loaded {loaded} module(s)")
        return loaded

    def _load_module(self, path: Path) -> str | None:
        """动态加载一个 .py 文件或包作为模块。

        模块名前缀 _third_party_skill_ 避免与 app 内模块冲突。
        """
        if path.is_file():
            module_name = f"_third_party_skill_{path.stem}"
            file_path = path
        else:
            module_name = f"_third_party_skill_{path.name}"
            file_path = path / "__init__.py"

        try:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                logger.warning(f"[SkillRegistry] cannot load module: {file_path}")
                return None
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            logger.info(f"[SkillRegistry] loaded third-party module: {module_name}")
            return module_name
        except Exception as e:
            logger.exception(
                f"[SkillRegistry] failed to load third-party skill {file_path}: {e}"
            )
            return None

    def reset(self) -> None:
        """清空注册表（仅用于测试）。"""
        self._skills.clear()
        self._third_party_scanned = False


# 全局单例
_GLOBAL_REGISTRY: SkillRegistry | None = None


def register(skill_cls: type[Skill]) -> type[Skill]:
    """模块级 register 装饰器，方便第三方 Skill 注册。

    用法：
        from app.agents.skills.base import Skill
        from app.agents.skills.registry import register

        @register
        class MySkill(Skill):
            node_type = "copywrite"
            name = "my_style"
            ...
    """
    return SkillRegistry.instance().register(skill_cls)


def get_skill_class(node_type: str, skill_name: str | None) -> type[Skill] | None:
    """便捷查询：按 node_type + skill_name 获取 Skill 子类。

    skill_name 为 None/空时返回该 node_type 的默认 Skill。
    第三方 Skill 在首次调用时懒加载扫描。
    """
    registry = _ensure_registry_loaded()

    if skill_name:
        return registry.get(node_type, skill_name)
    return registry.get_default(node_type)


def get_skill_class_by_name(name: str) -> type[Skill] | None:
    """按 skill name 全局查找唯一 Skill 子类，供 AgentRegistry 装配用。"""
    registry = _ensure_registry_loaded()
    matches = registry.find_by_name(name)
    if not matches:
        return None
    if len(matches) > 1:
        names = ", ".join(f"{cls.node_type}.{cls.name}" for cls in matches)
        raise ValueError(f"ambiguous skill name '{name}': {names}")
    return matches[0]


def _ensure_registry_loaded() -> SkillRegistry:
    """导入内置 Skill 并扫描第三方 Skill，返回全局注册表。"""
    ensure_builtin_skills_registered()
    registry = SkillRegistry.instance()
    registry.scan_third_party()
    return registry
