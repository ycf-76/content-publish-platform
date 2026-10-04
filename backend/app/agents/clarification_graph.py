"""Progressive Clarification Protocol — 字段依赖图与分批策略。

对应 PROGRESSIVE_CLARIFICATION_PROTOCOL.md §2.5。

核心逻辑：
1. 收集多个 Skill 的 clarify_meta，字段去重（同名取先注册的）
2. 构建字段依赖图（depends_on 声明）
3. 拓扑排序 → 检测循环依赖 → fallback 不分批
4. 按拓扑层级分批，每批 3-5 题
5. 评估 depends_on 条件（基于已收集的回答），过滤不满足条件的字段
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from app.agents.clarification_schema import (
    ClarifyFieldMeta,
    ClarificationBatch,
    ClarificationQuestion,
    QuestionType,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 5


def collect_clarify_fields(
    skills: list[Any],
    clarified_answers: dict[str, Any] | None = None,
) -> dict[str, tuple[ClarifyFieldMeta, str]]:
    """从多个 Skill 收集需要澄清的字段。

    Args:
        skills: 已注册的 Skill 实例列表
        clarified_answers: 本 session 已有的澄清回答（用于 when=always 去重）

    Returns:
        dict[field_name, (ClarifyFieldMeta, source_skill_name)]
        同名字段取先注册的 Skill（按 skills 列表顺序）
    """
    _answers = clarified_answers or {}
    result: dict[str, tuple[ClarifyFieldMeta, str]] = {}

    for skill in skills:
        meta = getattr(skill, "clarify_meta", None)
        if not meta or not isinstance(meta, dict):
            continue
        skill_name = getattr(skill, "name", "") or ""
        for field_name, field_meta in meta.items():
            if not isinstance(field_meta, ClarifyFieldMeta):
                continue
            if field_name in result:
                continue
            # when=always 去重：已回答过的字段不再重复提问
            if field_meta.when == "always" and field_name in _answers:
                continue
            result[field_name] = (field_meta, skill_name)

    return result


def filter_by_depends_on(
    fields: dict[str, tuple[ClarifyFieldMeta, str]],
    clarified_answers: dict[str, Any],
) -> dict[str, tuple[ClarifyFieldMeta, str]]:
    """过滤掉 depends_on 条件不满足的字段。

    depends_on 之间为 AND 关系：全部满足才保留。
    """
    filtered: dict[str, tuple[ClarifyFieldMeta, str]] = {}

    for field_name, (meta, skill_name) in fields.items():
        if not meta.depends_on:
            filtered[field_name] = (meta, skill_name)
            continue

        all_satisfied = True
        for dep in meta.depends_on:
            actual_value = str(clarified_answers.get(dep.field, ""))
            if actual_value != dep.value:
                all_satisfied = False
                break

        if all_satisfied:
            filtered[field_name] = (meta, skill_name)

    return filtered


def build_dependency_graph(
    fields: dict[str, tuple[ClarifyFieldMeta, str]],
) -> dict[str, set[str]]:
    """构建字段依赖图。

    Returns:
        adjacency list: field_name -> set of fields it depends on
    """
    graph: dict[str, set[str]] = {}
    for field_name, (meta, _) in fields.items():
        deps = set()
        for dep in meta.depends_on:
            if dep.field in fields:
                deps.add(dep.field)
        graph[field_name] = deps
    return graph


def topological_sort(graph: dict[str, set[str]]) -> list[list[str]] | None:
    """拓扑排序，返回按层级分组的字段列表。

    Returns:
        按层级分组的字段名列表（Batch 0, Batch 1, ...）
        如果检测到环 → 返回 None（调用方 fallback 不分批）
    """
    in_degree: dict[str, int] = {node: 0 for node in graph}
    for node, deps in graph.items():
        for dep in deps:
            if dep in in_degree:
                in_degree[dep] = in_degree.get(dep, 0)

    for node, deps in graph.items():
        for dep in deps:
            if dep in in_degree:
                pass

    in_degree = {node: 0 for node in graph}
    for node, deps in graph.items():
        for dep in deps:
            if dep in in_degree:
                in_degree[node] += 1

    levels: list[list[str]] = []
    remaining = set(graph.keys())

    while remaining:
        zero_in = [n for n in remaining if in_degree.get(n, 0) == 0]
        if not zero_in:
            logger.warning(
                f"[clarification_graph] cycle detected in dependency graph, "
                f"remaining nodes: {remaining}"
            )
            return None

        levels.append(sorted(zero_in))
        for n in zero_in:
            remaining.discard(n)
            for other in remaining:
                if n in graph.get(other, set()):
                    in_degree[other] -= 1

    return levels


def build_batches(
    fields: dict[str, tuple[ClarifyFieldMeta, str]],
    clarified_answers: dict[str, Any] | None = None,
    title_prefix: str = "创作偏好确认",
) -> list[ClarificationBatch]:
    """构建分批澄清问题列表。

    流程：
    1. 过滤 depends_on 不满足的字段
    2. 构建依赖图 → 拓扑排序
    3. 按层级分批（每批最多 _BATCH_SIZE 题）
    4. 组装 ClarificationBatch

    Args:
        fields: collect_clarify_fields 的输出
        clarified_answers: 已收集的回答（用于 depends_on 条件评估）
        title_prefix: 批次标题前缀

    Returns:
        分批后的 ClarificationBatch 列表
    """
    _answers = clarified_answers or {}

    filtered = filter_by_depends_on(fields, _answers)
    if not filtered:
        return []

    graph = build_dependency_graph(filtered)
    levels = topological_sort(graph)

    if levels is None:
        levels = [sorted(filtered.keys())]

    question_groups: list[list[str]] = []
    for level in levels:
        for i in range(0, len(level), _BATCH_SIZE):
            question_groups.append(level[i : i + _BATCH_SIZE])

    batches: list[ClarificationBatch] = []
    total = len(question_groups)

    for batch_idx, group in enumerate(question_groups):
        questions: list[ClarificationQuestion] = []
        for field_name in group:
            meta, skill_name = filtered[field_name]
            questions.append(
                ClarificationQuestion(
                    id=f"{skill_name}__clarify_{field_name}",
                    source_skill=skill_name,
                    question=meta.hint,
                    type=meta.question_type,
                    options=meta.options,
                    default=meta.default,
                    required=meta.required,
                    depends_on=meta.depends_on,
                    placeholder=meta.placeholder,
                    min_value=meta.min_value,
                    max_value=meta.max_value,
                )
            )

        next_hint = ""
        if batch_idx + 1 < total:
            next_hint = f"还有 {total - batch_idx - 1} 批问题待确认"

        batches.append(
            ClarificationBatch(
                batch_id=str(uuid.uuid4()),
                batch_index=batch_idx,
                total_batches=total,
                title=f"{title_prefix}（{batch_idx + 1}/{total}）",
                description="请确认以下偏好，帮助我们更精准地为您创作",
                questions=questions,
                next_batch_hint=next_hint,
            )
        )

    return batches


def compile_clarification_result(
    all_answers: dict[str, Any],
    fields: dict[str, tuple[ClarifyFieldMeta, str]],
    model_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """编译最终 clarification_result。

    对每个字段走优先级链（§6.2）：
    clarification_answer > model_settings > ClarifyFieldMeta.default > 系统默认

    §6.3 Skip 级联：如果字段 A 依赖字段 B，且 B 被 skip（走降级链），
    A 的 depends_on 条件用 B 的降级值评估——不满足则 A 也走降级链。

    Args:
        all_answers: 所有批次的累积回答 {field_name: value}
        fields: 原始字段元数据
        model_settings: 用户持久配置

    Returns:
        clarification_result dict
    """
    _ms = model_settings or {}
    result: dict[str, Any] = {}

    def _fallback_value(field_name: str, meta: ClarifyFieldMeta) -> Any:
        ms_value = _ms.get(field_name) or _ms.get(f"writing_{field_name}")
        if ms_value is not None:
            return ms_value
        if meta.default:
            return meta.default
        return None

    for field_name, (meta, _) in fields.items():
        value = all_answers.get(field_name)
        if value is not None and value != "":
            result[field_name] = value
            continue

        # §6.3 Skip 级联：检查 depends_on 条件是否仍满足
        if meta.depends_on:
            deps_satisfied = True
            for dep in meta.depends_on:
                dep_value = result.get(dep.field, all_answers.get(dep.field))
                if dep_value is None:
                    dep_meta_tuple = fields.get(dep.field)
                    if dep_meta_tuple:
                        dep_value = _fallback_value(dep.field, dep_meta_tuple[0])
                if str(dep_value or "") != dep.value:
                    deps_satisfied = False
                    break
            if not deps_satisfied:
                continue

        fallback = _fallback_value(field_name, meta)
        if fallback is not None:
            result[field_name] = fallback

    return result