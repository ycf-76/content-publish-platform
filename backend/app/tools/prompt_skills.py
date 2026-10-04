"""Prompt-driven Skill 自动扫描加载器。

扫描 prompts/skills/ 目录下的 *.md 文件，解析 YAML frontmatter，
自动创建 PromptDrivenSkill 子类并注册到 SkillRegistry。

新增策划/分析/审核类能力只需在 prompts/skills/ 下放一个 .md 文件：
  1. 文件头写 YAML frontmatter（node_type/name/description/...）
  2. 文件体写 SKILL.md（执行步骤 + 输出模板）
  3. 重启后端即生效，零 Python 代码

借鉴 Easel 的纯 SKILL.md 模式，但适配我们的 Skill 基类体系。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

import yaml

from app.tools.base import PromptDrivenSkill
from app.tools.registry import SkillRegistry
from app.agents.clarification_schema import ClarifyFieldMeta

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "agents" / "prompts" / "skills"

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


_scanned: bool = False


def scan_and_register_prompt_skills() -> list[type[PromptDrivenSkill]]:
    """扫描 prompts/skills/*.md，解析 frontmatter，动态创建并注册 Skill 类。

    幂等：多次调用只扫描一次，避免 ensure_builtin_skills_registered 被多处重复调用时重复读文件。
    """
    global _scanned
    if _scanned:
        return []
    _scanned = True

    registry = SkillRegistry.instance()
    registered: list[type[PromptDrivenSkill]] = []

    if not _SKILLS_DIR.exists():
        logger.debug(f"[prompt_skills] skills dir not found: {_SKILLS_DIR}")
        return registered

    for md_file in sorted(_SKILLS_DIR.glob("*.md")):
        try:
            skill_cls = _register_single_md(md_file, registry)
            if skill_cls:
                registered.append(skill_cls)
        except Exception as e:
            logger.exception(f"[prompt_skills] failed to load {md_file.name}: {e}")

    return registered


def _register_single_md(
    md_file: Path,
    registry: SkillRegistry,
) -> type[PromptDrivenSkill] | None:
    """解析单个 .md 文件并注册到 SkillRegistry。

    抽取为独立函数，供 scan_and_register_prompt_skills 和
    register_prompt_skill_from_content 共用。
    """
    raw = md_file.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if not match:
        logger.warning(f"[prompt_skills] no frontmatter in {md_file.name}, skipping")
        return None

    frontmatter = yaml.safe_load(match.group(1))
    if not frontmatter:
        logger.warning(f"[prompt_skills] empty frontmatter in {md_file.name}, skipping")
        return None

    node_type = frontmatter.get("node_type", "")
    name = frontmatter.get("name", "")
    if not node_type or not name:
        logger.warning(f"[prompt_skills] missing node_type/name in {md_file.name}, skipping")
        return None

    skill_body = raw[match.end():]

    clarify_schema_raw = frontmatter.get("clarify_schema", None)

    skill_cls = _create_skill_class(
        md_file=md_file,
        node_type=node_type,
        name=name,
        display_name=frontmatter.get("display_name", name),
        description=frontmatter.get("description", ""),
        trigger_words=frontmatter.get("trigger_words", []),
        reference_paths=frontmatter.get("references", []),
        prompt_guidance=frontmatter.get("prompt_guidance", ""),
        skill_body=skill_body,
        clarify_schema_raw=clarify_schema_raw,
        frontmatter=frontmatter,
    )

    registry.register(skill_cls)
    logger.info(f"[prompt_skills] registered: {node_type}.{name} from {md_file.name}")
    return skill_cls


def register_prompt_skill_from_content(
    filename: str,
    content: str,
) -> type[PromptDrivenSkill]:
    """从 .md 文件内容动态创建并注册 PromptDrivenSkill。

    供 API 层调用：用户在前端创建提示词型 Skill 时，
    后端保存 .md 文件到 prompts/skills/ 目录并即时注册。

    Args:
        filename: 保存的文件名（如 "my_checker.md"）
        content: .md 文件完整内容（含 YAML frontmatter + SKILL.md 正文）

    Returns:
        注册成功的 Skill 子类

    Raises:
        ValueError: frontmatter 缺少必填字段或格式错误
    """
    _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    target_path = _SKILLS_DIR / filename
    target_path.write_text(content, encoding="utf-8")

    registry = SkillRegistry.instance()
    skill_cls = _register_single_md(target_path, registry)
    if skill_cls is None:
        target_path.unlink(missing_ok=True)
        raise ValueError(
            "Skill 文件格式错误：需要合法的 YAML frontmatter（含 node_type 和 name），"
            "格式参考：\n---\nnode_type: xxx\nname: xxx\n---\n# Skill 正文"
        )
    return skill_cls


def _create_skill_class(
    md_file: Path,
    node_type: str,
    name: str,
    display_name: str,
    description: str,
    trigger_words: list[str],
    reference_paths: list[str],
    prompt_guidance: str,
    skill_body: str,
    clarify_schema_raw: dict[str, Any] | None = None,
    frontmatter: dict[str, Any] | None = None,
) -> type[PromptDrivenSkill]:
    """动态创建 PromptDrivenSkill 子类。"""

    class _DynamicSkill(PromptDrivenSkill):
        pass

    _DynamicSkill.node_type = node_type
    _DynamicSkill.name = name
    _DynamicSkill.display_name = display_name
    _DynamicSkill.description = description
    _DynamicSkill.trigger_words = trigger_words
    _DynamicSkill.reference_paths = reference_paths
    _DynamicSkill.prompt_guidance = prompt_guidance
    _DynamicSkill.skill_md_path = md_file.name
    _DynamicSkill.skill_category = frontmatter.get("category", "") if frontmatter else ""
    _DynamicSkill.skill_priority = frontmatter.get("priority", "") if frontmatter else ""
    _DynamicSkill.__name__ = f"PromptSkill_{node_type}_{name}"
    _DynamicSkill.__qualname__ = f"PromptSkill_{node_type}_{name}"

    _DynamicSkill._md_cache = None
    _DynamicSkill._ref_cache = None

    _DynamicSkill.__module__ = f"app.tools.prompt_skills.{md_file.stem}"

    # 解析 frontmatter 的 clarify_schema 并注入为类属性
    # try-except 包裹：解析失败 → clarify_meta = {}，不影响 Skill 注册
    if clarify_schema_raw and isinstance(clarify_schema_raw, dict):
        try:
            parsed_meta: dict[str, ClarifyFieldMeta] = {}
            for field_name, field_data in clarify_schema_raw.items():
                if isinstance(field_data, dict):
                    parsed_meta[str(field_name)] = ClarifyFieldMeta.from_dict(field_data)
            _DynamicSkill.clarify_meta = parsed_meta
            logger.debug(
                f"[prompt_skills] clarify_meta injected for {name}: "
                f"fields={list(parsed_meta.keys())}"
            )
        except Exception as e:
            logger.warning(
                f"[prompt_skills] clarify_schema parse failed for {name}: {e}, "
                f"falling back to empty"
            )
            _DynamicSkill.clarify_meta = {}
    else:
        _DynamicSkill.clarify_meta = {}

    return _DynamicSkill