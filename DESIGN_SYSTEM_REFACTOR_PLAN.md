# 设计系统架构重构方案（修正版 v2）

> 问题：LLM 调用做图文时，格式/颜色总是固定的，65 个 Skills 只用到十几套。
> 根因：**设计系统知识（palettes.md / card-recipes.md / layout-laws.md）被锁在单个 Skill 的 references 里**，只有当 LLM 调用该 Skill 的 `execute()` 时才会加载。但 LLM 在决策"选哪个工具、用什么配色"时看不到这些知识——它只能靠自己"幻觉"，结果永远是默认蓝/紫。
> 目标：从"执行时才看到设计知识"变成"决策时就能看到设计知识"——LLM 在 system prompt 阶段就拥有完整的设计系统上下文。

---

## 架构对比（修正版）

```
当前链路：
  用户"帮我做图文"
    → ChatAgent → AgentHarness(creation_type=None) → 全量65个Skills进harness.skills
    → LoopExecutor._system_prompt()
      → SkillRouter.select_skills() → HOT类全入选（视觉Skill没被过滤！）
      → build_routing_table(selected_skills) → system prompt 有工具列表
      → _active_skills = selected_skills → prompt_guidance 只取选中Skills的
      → 返回 system prompt（无设计系统知识块）
    → LLM 读 system prompt → 看到工具列表，但没有配色/配方/布局指导
    → LLM 选 card_design → function calling
    → card_design.execute()
      → _load_references() → 此时才读 palettes.md / card-recipes.md
      → 但此时已经晚了——LLM 已经在上一轮自己决定了配色和风格
    → 输出：固定蓝/紫配色（LLM 无参考时的安全选择）

重构后链路：
  用户"帮我做图文"
    → ChatAgent → AgentHarness(creation_type="image_text") → CREATION_TYPE_SKILLS过滤后~35个Skills
    → LoopExecutor._system_prompt()
      → SkillRouter.select_skills() → HOT+WARM命中→ ~25个selected
      → build_compact_catalog(harness.skills) → 全量紧凑目录注入{skill_routing}
      → build_design_system_block("image_text") → 设计系统知识独立注入
        （palettes.md + card-recipes.md + layout-laws.md + anti-ai-slop.md）
      → prompt_guidance 从 harness.skills 全量取（不只是selected）
      → 返回 system prompt（含完整设计系统知识）
    → LLM 读 system prompt → 看到全部工具目录 + 配色方案 + 配方库 + 布局法则
    → LLM 自主选择配色（如 Indigo Porcelain）+ 工具（card_design）+ 风格参数
    → card_design.execute() → _load_references() 加载完整references
      → 此时 references 内容与 system prompt 中已注入的设计系统一致（或为补充细节版）
    → 输出：有设计依据的多样化配色和布局
```

---

## 根因修正（v1 方案的误诊）

### v1 误诊："视觉类 Skill 被 SkillRouter 过滤掉了"

**实际情况**：[skill_router.py:L213-L224](file:///D:/My_Project/多智能体小红书发布平台/backend/app/tools/skill_router.py#L213-L224)

```python
if pri == SkillPriority.HOT:
    selected.append(s)      # ← HOT 永远入选，不管 trigger_words
    continue
```

所有视觉类 Skill 的 frontmatter 都是 `priority: hot`：
- [card-design.md](file:///D:/My_Project/多智能体小红书发布平台/backend/app/agents/prompts/skills/card-design.md) → `priority: hot`
- [card-xiaohongshu.md](file:///D:/My_Project/多智能体小红书发布平台/backend/app/agents/prompts/skills/card-xiaohongshu.md) → `priority: hot`
- [infographic.md](file:///D:/My_Project/多智能体小红书发布平台/backend/app/agents/prompts/skills/infographic.md) → `priority: hot`
- [poster-hero.md](file:///D:/My_Project/多智能体小红书发布平台/backend/app/agents/prompts/skills/poster-hero.md) → `priority: hot`
- [comparison-card.md](file:///D:/My_Project/多智能体小红书发布平台/backend/app/agents/prompts/skills/comparison-card.md) → `priority: hot`
- [card-quote.md](file:///D:/My_Project/多智能体小红书发布平台/backend/app/agents/prompts/skills/card-quote.md) → `priority: hot`

**SkillRouter 从未过滤掉视觉类 Skill。**

### 真正的根因：设计系统知识的加载时机太晚

当前架构中，palettes.md / card-recipes.md / layout-laws.md 的加载路径：

```
Skill .md frontmatter references 字段
  ↓ PromptDrivenSkill.reference_paths 属性
  ↓ PromptDrivenSkill._load_references() 方法（[base.py:L285-L300](file:///D:/My_Project/多智能体小红书发布平台/backend/app/tools/base.py#L285-L300)）
  ↓ 只在 execute() 时调用
  ↓ 注入到 LLM 的单次 tool call 消息中
```

**问题**：LLM 在 system prompt 阶段做"选哪个工具、用什么配色"的决策时，这些知识还不存在。等 execute() 时加载进来，LLM 已经在上一轮自己决定了配色。

类比：**餐厅菜单上只写了菜名没有图片和描述，顾客点了之后厨师才拿出食谱——但顾客已经点完了。**

### 两层 Skill 过滤机制（方案必须同时处理）

| 层级 | 位置 | 机制 | 对视觉 Skill 的影响 |
|------|------|------|-------------------|
| **第 1 层** | [registry.py:L221-L334](file:///D:/My_Project/多智能体小红书发布平台/backend/app/agents/registry.py#L221-L334) `CREATION_TYPE_SKILLS` | 按 `creation_type` 在 Skill 实例化前过滤 | `creation_type="voiceover"` 时视觉 Skill 不被实例化 |
| **第 2 层** | [skill_router.py](file:///D:/My_Project/多智能体小红书发布平台/backend/app/tools/skill_router.py) `select_skills()` | 按 priority + trigger_words 运行时筛选 | 视觉 Skill 是 HOT，始终入选 |

**两层都正常工作时**（`creation_type="image_text"` 或 `None`），视觉 Skill 在 harness.skills 里且被 SkillRouter 选中。问题不在过滤，而在**设计系统知识的加载时机**。

**但第 1 层过滤有副作用**：当 `creation_type="voiceover"` 时，`CREATION_TYPE_SKILLS["voiceover"]` 的 produce 组只有 `["copywriting", "social_content", "style_transfer"]`——视觉 Skill 根本没被实例化，连 `harness.skills` 都进不去。后续 `build_compact_catalog()` 和 `_build_tools_schema()` 注入的全量目录里也不会有它们。如果用户在 voiceover 模式下突然说"帮我配个封面图"，LLM 看不到 `card_design` 也调不了。

---

## 改动清单（修正版 v3）

### 改动 0：`registry.py` 的 `_build_skills()` 保留 HOT 级 Skill

**文件**：`backend/app/agents/registry.py`

**改动位置**：`_build_skills()` 方法，约 L302-L334

**问题**：当 `creation_type` 不为 None 时，`CREATION_TYPE_SKILLS` 会过滤掉不属于该创作类型的 Skill。视觉类 Skill（`card_design`、`infographic`、`poster_hero` 等）只在 `image_text` 和 `ai_edit` 类型下被实例化，其他类型下完全不可见。

**改动逻辑**：在 `_build_skills()` 的 `creation_type` 过滤之后，追加一个"保留 HOT 级 Skill"的后置步骤——无论 `creation_type` 是什么，所有 `priority: hot` 的 Skill 都保留在 `harness.skills` 里。

```python
# _build_skills() 改动（在 creation_type 过滤之后追加）

def _build_skills(skill_names, creation_type=None):
    resolved = _resolve_creation_type_skills(creation_type)
    if resolved is not None:
        name_set = set(resolved)
        filtered = [s for s in _skills_cache if s.name in name_set]
    else:
        filtered = list(_skills_cache)

    # ===== 新增：保留 HOT 级 Skill（跨 creation_type） =====
    # 理由：HOT 级 Skill 是核心创作工具，用户随时可能跨类型使用。
    # 例如 voiceover 模式下用户说"帮我配个封面图"，需要 card_design 可用。
    # 只保留 category=create 且 priority=hot 的 Skill，避免引入不相关的 platform/audit 类。
    _hot_create_names: set[str] = set()
    for s in _skills_cache:
        pri = infer_skill_priority(s)
        cat = infer_skill_category(s)
        if pri == SkillPriority.HOT and cat == SkillCategory.CREATE:
            _hot_create_names.add(s.name)

    existing_names = {s.name for s in filtered}
    for s in _skills_cache:
        if s.name in _hot_create_names and s.name not in existing_names:
            filtered.append(s)

    return filtered
```

**效果**：`creation_type="voiceover"` 时，`harness.skills` 里除了 voiceover 专属 Skill，还有 `card_design`、`infographic`、`poster_hero`、`comparison_card`、`card_quote`、`card_xiaohongshu` 等 HOT 级创作工具。用户跨类型请求时 LLM 能看到并调用它们。

**Token 开销**：多实例化 ~6 个 Skill 对象，每个 Skill 的 .md 文件 ~1KB，总计 ~6KB 内存，忽略不计。

---

### 改动 1：新增 `design_system_injector.py`

**文件**：`backend/app/agents/prompts/references/design_system_injector.py`

**职责**：根据创作意图，将设计系统知识**提前到 system prompt 阶段**注入，让 LLM 在决策时就有完整的配色/配方/布局指导。

**关键修正**：
- `max_chars` 不再是硬编码 6000，而是根据意图类型动态计算
- 与现有 `CREATION_TYPE_SKILLS` 映射对齐（不重复造轮子）
- 明确去重策略：system prompt 注入摘要版，Skill.execute() 注入完整版

```python
"""设计系统注入器：将设计系统知识提前到 system prompt 阶段注入。

根因修复：
  当前 palettes.md / card-recipes.md / layout-laws.md 锁在 Skill.references 里，
  只有 execute() 时才加载。LLM 在决策阶段（选工具+选配色）看不到这些知识，
  导致"幻觉"出固定蓝/紫配色。

  本模块在 LoopExecutor._system_prompt() 阶段根据创作意图注入设计系统知识，
  让 LLM 决策时就有完整的设计上下文。

去重策略：
  - system prompt 注入：每个 reference 文件的【核心规则摘要】（~30%内容）
  - Skill.execute() 注入：reference 文件的【完整原文】（100%内容）
  - 两者不冲突：system prompt 是"全局导航"，execute() 是"详细手册"
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REFERENCES_DIR = Path(__file__).resolve().parent

_DESIGN_SYSTEM_FILES: dict[str, list[str]] = {
    "visual": [
        "palettes.md",
        "card-recipes.md",
        "layout-laws.md",
        "anti-ai-slop.md",
    ],
    "writing": [
        "writing-style-rules.md",
        "zh-ai-markers.md",
        "phrases-to-remove.md",
    ],
}

_INTENT_TO_KNOWLEDGE: dict[str, list[str]] = {
    "image_text": ["visual", "writing"],
    "card": ["visual", "writing"],
    "copywrite": ["writing"],
    "video": ["writing"],
    "data": ["visual"],
    "default": ["writing"],
}

_INTENT_SIGNALS: dict[str, list[str]] = {
    "image_text": [
        "图文", "做图", "卡片", "小红书", "封面", "海报",
        "信息图", "对比图", "知识卡", "金句卡", "竖版",
    ],
    "card": ["卡片", "知识卡", "金句卡", "card", "渲染卡片"],
    "copywrite": ["文案", "写", "标题", "正文", "标签", "种草"],
    "video": ["视频", "脚本", "口播", "剪辑"],
    "data": ["数据", "图表", "可视化", "报告", "信息图"],
}

_CREATION_TYPE_TO_INTENT: dict[str, str] = {
    "image_text": "image_text",
    "voiceover": "copywrite",
    "short_video": "video",
    "ai_edit": "image_text",
    "long_article": "copywrite",
    "live_clip": "video",
}


def infer_creative_intent(
    user_message: str,
    creation_type: str | None = None,
) -> str:
    """推断创作意图。

    复用项目已有的 creation_type 机制（见 registry.py CREATION_TYPE_SKILLS），
    不重新发明轮子。优先用前端显式传入的 creation_type，其次用信号词匹配。
    """
    if creation_type:
        return _CREATION_TYPE_TO_INTENT.get(creation_type, "default")

    msg = user_message.lower()
    best_intent = "default"
    best_score = 0
    for intent, signals in _INTENT_SIGNALS.items():
        score = sum(1 for s in signals if s in msg)
        if score > best_score:
            best_score = score
            best_intent = intent
    return best_intent


def _summarize_reference(content: str, max_chars: int) -> str:
    """将 reference 文件内容压缩为核心规则摘要。

    策略：
    - 保留 # 标题和 ## 二级标题（结构骨架）
    - 保留 > 引用块（关键原则）
    - 保留表格（如 palettes.md 的配色表）
    - 保留 🚫/✅ 标记的规则行
    - 截断长段落，保留前两句

    关键：append 前检查长度，保证每行都是完整的 Markdown，
    不会出现表格行被腰斩的情况。
    """
    lines = content.split("\n")
    kept: list[str] = []
    current_len = 0

    for line in lines:
        stripped = line.strip()

        # 先计算本行的贡献长度
        if stripped.startswith("#"):
            candidate = line
        elif stripped.startswith(">"):
            candidate = line
        elif stripped.startswith("|") and not stripped.startswith("|--"):
            candidate = line
        elif any(marker in stripped for marker in ("🚫", "✅", "⚠️", "🔴", "🟡", "🟢")):
            candidate = line
        elif stripped and not stripped.startswith("-") and not stripped.startswith("*"):
            candidate = stripped[:80] + ("…" if len(stripped) > 80 else "")
        elif stripped.startswith("-") or stripped.startswith("*"):
            candidate = stripped[:100]
        else:
            continue

        # append 前检查：如果加入本行会超限，则 break 不 append
        # 这保证 kept 里每行都是完整的，不会出现半截表格行
        if current_len + len(candidate) + 1 > max_chars:
            break

        kept.append(candidate)
        current_len += len(candidate) + 1

    result = "\n".join(kept)
    if current_len >= max_chars:
        result += "\n\n⚠️ 设计系统摘要已截断"
    return result


def build_design_system_block(
    user_message: str = "",
    creation_type: str | None = None,
    mode: str = "summary",
    max_chars: int = 0,
) -> str:
    """根据创作意图，构建设计系统知识块。

    Args:
        user_message: 用户原始消息
        creation_type: 前端传入的创作类型（复用 registry.py 已有机制）
        mode: "summary"=摘要版（用于 system prompt），"full"=完整版（备用）
        max_chars: 最大字符数，0 表示自动计算

    Returns:
        设计系统知识 Markdown 块
    """
    intent = infer_creative_intent(user_message, creation_type)
    knowledge_types = _INTENT_TO_KNOWLEDGE.get(intent, ["writing"])

    parts: list[str] = []
    parts.append("## 设计系统")
    parts.append(
        "> 以下知识适用于所有相关工具，不限于特定 Skill。\n"
        "> 选配色时必须从此处选取，不要自定义新配色。\n"
        "> 完整详情在各 Skill 执行时自动补充。\n"
    )

    # 自动计算 max_chars：基于实际文件大小
    if max_chars == 0:
        file_sizes: dict[str, int] = {}
        for ktype in knowledge_types:
            for fname in _DESIGN_SYSTEM_FILES.get(ktype, []):
                fpath = _REFERENCES_DIR / fname
                if fpath.exists():
                    file_sizes[fname] = fpath.stat().st_size
        total_raw = sum(file_sizes.values())
        # summary 模式下目标压缩到原大小的 ~40%
        max_chars = max(int(total_raw * 0.45), 8000)

    for ktype in knowledge_types:
        files = _DESIGN_SYSTEM_FILES.get(ktype, [])
        for fname in files:
            fpath = _REFERENCES_DIR / fname
            if fpath.exists():
                content = fpath.read_text(encoding="utf-8").strip()
                if content:
                    if mode == "summary":
                        content = _summarize_reference(content, max_chars // len(files))
                    parts.append(content)
                    parts.append("")

    result = "\n".join(parts)
    if len(result) > max_chars:
        result = result[:max_chars] + "\n\n⚠️ 设计系统内容已截断"
    return result
```

---

### 改动 2：`skill_router.py` 新增 `build_compact_catalog()`

**文件**：`backend/app/tools/skill_router.py`

**改动位置**：`SkillRouter` 类新增方法，不改现有方法（向后兼容）

```python
# 在 SkillRouter 类中新增方法

COMPACT_DESC_MAX = 50
COMPACT_CATALOG_MAX_CHARS = 5000

def build_compact_catalog(self, all_skills: list[Any]) -> str:
    """全量紧凑目录：每个 Skill 一行摘要，按 category 分组。

    用途：注入 system prompt 的 {skill_routing} 占位符，
    让 LLM 看到全部可用工具的一行概览，而不仅是 SkillRouter 选中的 subset。

    与 build_routing_table() 的区别：
    - build_routing_table(): 给 selected_skills 生成详细路由表（旧逻辑）
    - build_compact_catalog(): 给 all_skills 生成紧凑一行摘要（新逻辑）
    """
    if not all_skills:
        return "- (当前无可用工具)"

    grouped: dict[SkillCategory, list[Any]] = {}
    for s in all_skills:
        cat = infer_category(s)
        grouped.setdefault(cat, []).append(s)

    lines: list[str] = []
    for cat in SkillCategory:
        group = grouped.get(cat, [])
        if not group:
            continue
        meta = CATEGORY_META[cat]
        lines.append(f"### {meta.icon} {meta.label}（{len(group)}个）")
        for s in group:
            name = getattr(s, "name", "?")
            display = getattr(s, "display_name", "") or name
            desc = getattr(s, "description", "") or ""
            short = desc[:self.COMPACT_DESC_MAX] + "…" if len(desc) > self.COMPACT_DESC_MAX else desc
            lines.append(f"- {display}(`{name}`): {short}")
        lines.append("")

    result = "\n".join(lines)
    if len(result) > self.COMPACT_CATALOG_MAX_CHARS:
        result = result[:self.COMPACT_CATALOG_MAX_CHARS] + "\n\n⚠️ 工具目录已截断"
    return result
```

---

### 改动 3：`loop.py` 的 `_system_prompt()` 重构

**文件**：`backend/app/engine/harness/executor/loop.py`

**改动位置**：`_system_prompt()` 方法，约 L940-L1019

**改动逻辑**：

```python
def _system_prompt(self, harness, input=None, context=None):
    # ... _skill_desc 等辅助函数不变 ...

    skill_lines = "\n".join(_skill_desc(s) for s in harness.skills) or "- (no tools available)"
    role_block = ""
    if harness.prompt_template:
        tmpl = harness.prompt_template
        if input and context:
            try:
                tmpl = tmpl.format(**{**input, **context.model_dump()})
            except (KeyError, IndexError) as _fmt_err:
                logger.debug(f"[{context.node_id}] prompt template format partial miss: {_fmt_err}")

        raw_topic_early = (input or {}).get("topic", "")
        user_msg_early = self._latest_user_request(raw_topic_early) or raw_topic_early

        # ===== 改动点 A：全量紧凑目录注入 {skill_routing} =====
        # 旧逻辑（删除）：
        #   self._routing_result = self._skill_router.select_skills(harness.skills, user_msg_early)
        #   self._selected_skills = self._routing_result.selected_skills
        #   _skill_routing = self._skill_router.build_routing_table(self._selected_skills)
        #
        # 新逻辑：
        #   1. compact_catalog = 全量 Skills 一行摘要（让 LLM 看到所有工具）
        #   2. select_skills 仍然运行（用于 tools schema 排序提示，不再做过滤门）
        #   3. routing_hint = trigger 匹配到的工具提示（排前面引导注意力）

        _compact_catalog = self._skill_router.build_compact_catalog(harness.skills)

        # select_skills 仍然运行，但角色降级为"排序提示器"
        self._routing_result = self._skill_router.select_skills(harness.skills, user_msg_early)
        self._selected_skills = self._routing_result.selected_skills

        _routing_hint = ""
        if self._routing_result.trigger_matched_skills:
            _matched_names = self._routing_result.trigger_matched_skills
            _routing_hint = (
                f"\n> 当前请求可能涉及：{', '.join(f'`{n}`' for n in _matched_names)}"
                f"（已在上方目录中标注，可优先考虑）"
            )
            logger.info(
                f"[loop] skill_router: trigger_matched={_matched_names}, "
                f"selected={self._routing_result.total_selected}/{self._routing_result.total_available}"
            )

        _category_hint = self._routing_result.category_hint
        _skill_routing = _compact_catalog + _routing_hint
        if _category_hint:
            _skill_routing = f"{_category_hint}\n\n{_skill_routing}"

        if "{skill_routing}" in tmpl:
            tmpl = tmpl.replace("{skill_routing}", _skill_routing)
        else:
            logger.warning(
                f"[{context.node_id}] AGENTS.md missing {{skill_routing}} placeholder, "
                f"dynamic tool routing not injected"
            )
        role_block = tmpl + "\n\n"

    raw_topic = (input or {}).get("topic", "")
    user_msg = self._latest_user_request(raw_topic) or raw_topic

    # ===== 改动点 B：prompt_guidance 从全量 skills 取 =====
    # 旧逻辑：_active_skills = self._selected_skills or harness.skills
    # 新逻辑：始终从 harness.skills 全量取 guidance
    # 理由：guidance 是简短提示（1-2 句话），全量注入不会撑爆 prompt，
    #       且能让 LLM 在决策时就知道每个工具的使用要点
    _skill_guidance_block = ""
    for s in harness.skills:
        guidance = getattr(s, "prompt_guidance", "") or ""
        if guidance:
            _skill_guidance_block += guidance + "\n\n"

    _behavior_template = self._load_behavior_template()
    behavior_block = (
        _behavior_template
        .replace("{skill_lines}", skill_lines)
        .replace("{skill_guidance_block}", _skill_guidance_block)
    )

    # ===== 改动点 C：设计系统独立注入（核心修复）=====
    from app.agents.prompts.references.design_system_injector import build_design_system_block
    _creation_type = None
    if input and isinstance(input, dict):
        _creation_type = input.get("creation_type")
    _design_block = build_design_system_block(
        user_message=user_msg,
        creation_type=_creation_type,
        mode="summary",
    )

    return (
        f"{role_block}"
        f"{behavior_block}"
        f"{_design_block}\n\n"
        f"[USER REQUEST — DO NOT LOSE THIS]: {user_msg}\n"
    )
```

---

### 改动 4：`loop.py` 的 `_build_tools_schema()` 全量排序注入

**文件**：`backend/app/engine/harness/executor/loop.py`

**改动位置**：`_build_tools_schema()` 方法，约 L1004-L1058

**改动逻辑**：

```python
def _build_tools_schema(self, harness: AgentHarness) -> list[dict[str, Any]]:
    """全量 tools schema，按优先级排序。

    旧逻辑：skills = self._selected_skills or harness.skills（只用选中的）
    新逻辑：skills = harness.skills（全量），但按 triggered → hot → rest 排序

    关键修正：使用字符串 name 比较（与现有代码一致），不用对象 __eq__ 比较
    """
    all_skills = harness.skills

    # 构建基础 tools schema（全量）
    tools = []
    for s in all_skills:
        schema_cls = getattr(s, "input_schema", None)
        parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        if schema_cls is not None and schema_cls is not BaseModel:
            try:
                schema = schema_cls.model_json_schema()
                parameters = {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                }
            except Exception:
                pass
        tools.append({
            "type": "function",
            "function": {
                "name": getattr(s, "name", ""),
                "description": getattr(s, "description", ""),
                "parameters": parameters,
            },
        })

    # 三段排序：triggered → hot → rest（使用字符串 name 比较，避免对象 __eq__ 问题）
    _triggered_names: set[str] = set()
    if self._routing_result:
        _triggered_names = set(self._routing_result.trigger_matched_skills)

    _hot_names: set[str] = set()
    from app.tools.skill_router import infer_priority, SkillPriority
    for s in all_skills:
        if infer_priority(s) == SkillPriority.HOT:
            _hot_names.add(getattr(s, "name", ""))

    # 使用 t["function"]["name"] 字符串比较（与现有代码 L1039 一致）
    _triggered = [t for t in tools if t["function"]["name"] in _triggered_names]
    _hot = [t for t in tools if t["function"]["name"] in _hot_names]
    _other = [t for t in tools if t not in _triggered and t not in _hot]

    tools = list(dict.fromkeys(_triggered + _hot + _other))

    if len(tools) > self._MAX_TOOLS_FOR_LLM:
        tools = tools[:self._MAX_TOOLS_FOR_LLM]
        logger.info(
            f"[loop] tools_count={len(all_skills)} exceeds max={self._MAX_TOOLS_FOR_LLM}, "
            f"truncated to {len(tools)} (triggered+hot prioritized)"
        )
    return tools
```

**必须配套改动**：`_MAX_TOOLS_FOR_LLM` 从 50 改为 65。

```python
# loop.py 类常量改动
_MAX_TOOLS_FOR_LLM = 65  # 旧值 50
```

**理由**：`build_compact_catalog()` 让 LLM 在目录里看到了全部 65 个 Skill，如果 tools schema 只有 50 个，LLM 想调某个 Skill 但调不了——比现在更糟糕（现在至少不会给 LLM 看到调不了的工具）。目录和 tools schema 必须一致。

**注意**：排序逻辑与现有代码 [loop.py:L1039-L1049](file:///D:/My_Project/多智能体小红书发布平台/backend/app/engine/harness/executor/loop.py#L1039-L1049) 的截断排序完全一致，只是输入从 `selected_skills` 改成了 `harness.skills`（全量）。这保证了行为一致性。

---

### 改动 5：`card-design.md` 的 `clarify_schema` 扩充

**文件**：`backend/app/agents/prompts/skills/card-design.md`

**改动位置**：frontmatter 的 `clarify_schema.visual_style`

**改动内容**：从 3 个选项扩充到覆盖 palettes.md 全部配色体系

```yaml
clarify_schema:
  visual_style:
    hint: "卡片视觉风格？"
    when: ambiguous
    default: "indigo_porcelain"
    auto_default: true
    options:
      # === 杂志系（Ink Classic 家族）===
      - label: "靛蓝瓷墨（知识/科技/商业）"
        value: "indigo_porcelain"
      - label: "森林墨绿（自然/健康/户外）"
        value: "forest_ink"
      - label: "牛皮纸暖（回忆/手工/人文）"
        value: "kraft_paper"
      - label: "沙丘雅金（设计/美学/艺术）"
        value: "dune"
      - label: "午夜黑金（游戏/影视/暗色）"
        value: "midnight_ink"
      - label: "Ink Classic（通用中性/商务）"
        value: "ink_classic"
      # === 瑞士系（极简白底 + 点缀色）===
      - label: "极简白底+克莱因蓝（干货/产品/AI）"
        value: "minimal_white_ikb"
      - label: "极简白底+柠檬黄（年轻/消费/活力）"
        value: "minimal_white_lemon"
      - label: "极简白底+安全橙（工业/决策/效率）"
        value: "minimal_white_orange"
  layout:
    hint: "布局偏好？"
    when: ambiguous
    default: "top_img_bottom_text"
    auto_default: true
    options:
      - label: "左文右图"
        value: "left_text_right_img"
      - label: "上图下文"
        value: "top_img_bottom_text"
      - label: "全图+浮层文字"
        value: "full_img_overlay"
      - label: "左右对比"
        value: "left_right_compare"
```

---

### 改动 6：视觉类 Skills 的 trigger_words 扩充

**涉及文件**（6 个 .md 文件，每个加 2-3 个通用触发词）

| 文件 | 当前 trigger_words | 新增 |
|------|-------------------|------|
| `card-design.md` | `"设计卡片","做卡片","小红书卡片","信息卡","卡片设计","生成卡片","卡片组","封面卡"` | +`"做图文"`,`"图文"` |
| `card-xiaohongshu.md` | `"小红书卡片","知识卡","滑动卡片","渲染卡片","竖版卡片","3:4卡片","做卡片"` | +`"做图文"`,`"图文"` |
| `infographic.md` | `"信息图","流程图","数据可视化","动画图表","GIF图表","条形竞赛","做信息图","可视化"` | +`"做图文"`,`"图文"` |
| `poster-hero.md` | （需确认当前值） | +`"做图文"`,`"图文"`,`"海报"` |
| `comparison-card.md` | （需确认当前值） | +`"做图文"`,`"图文"`,`"对比图"` |
| `card-quote.md` | （需确认当前值） | +`"做图文"`,`"图文"`,`"金句卡"` |

**作用变化**：在重构后的架构中，trigger_words 不再决定 Skill 生死（HOT 类始终入选），而是决定 Skill 在 tools schema 中的**排序位置**（triggered 排最前面，LLM 更容易注意到）。

---

### 改动 7（非可选）：确保前端传 `creation_type`

**现状**：你的项目**已经实现了** `creation_type` 的端到端传递：

- [chat_agent router:L205](file:///D:/My_Project/多智能体小红书发布平台/backend/app/api/routers/chat_agent.py#L205)：API 接收 `creation_type`
- [chat_agent.py:L58](file:///D:/My_Project/多智能体小红书发布平台/backend/app/agents/chat_agent.py#L58)：ChatAgent 接收并传递
- [registry.py:L386](file:///D:/My_Project/多智能体小红书发布平台/backend/app/agents/registry.py#L386)：`build_harness(agent_id, creation_type=creation_type)` 使用
- [registry.py:L302-L334](file:///D:/My_Project/多智能体小红书发布平台/backend/app/agents/registry.py#L302-L334)：`_resolve_creation_type_skills()` 按 `CREATION_TYPE_SKILLS` 过滤

**需要检查的点**：前端 `ChatView.vue` 在用户选择"图文"模式时是否正确传了 `creation_type="image_text"`。如果前端传了 `None`（默认值），则 `registry.py` 会走全量加载路径（`resolved = None`），这不是 bug，但会多加载一些不需要的 Skills（如 wechat/feishu 等 platform 类）。

**建议**：在前端"图文"模式的 chat 请求中显式传 `creation_type: "image_text"`，这样 `registry.py` 第 1 层过滤就会精确加载 ~35 个相关 Skill（而不是全部 65 个），减少后续处理压力。

---

## Token 开销估算（修正版）

### 实际文件大小（已验证）

| 文件 | 大小（bytes） |
|------|-------------|
| palettes.md | 3,107 |
| card-recipes.md | 4,368 |
| layout-laws.md | 3,491 |
| anti-ai-slop.md | 3,482 |
| **visual 小计** | **14,448** |
| writing-style-rules.md | 2,755 |
| zh-ai-markers.md | 3,074 |
| phrases-to-remove.md | 2,587 |
| **writing 小计** | **8,416** |

### 各组件增量估算

| 组件 | 当前大小 | 重构后大小 | 增量 | 说明 |
|------|---------|-----------|------|------|
| `{skill_routing}` 占位符 | ~15 个 Skill 详细描述 ≈ 3000 字符 | 65 个紧凑目录 ≈ **7150 字符** | +4150 | 每个 Skill 一行 ~110 字（display_name + name + description 截断 + 格式符号） |
| 设计系统块 | **0**（不存在） | visual+writing 摘要 ≈ **10000 字符** | **+10000** | `_summarize_reference` 压缩到 ~45% |
| `prompt_guidance` 块 | ~15 个 Skill guidance ≈ 1500 字符 | 65 个 Skill guidance ≈ 6000 字符 | +4500 | 每个 guidance 1-2 句话 |
| tools schema | ~15 个 × 120 字 ≈ 1800 字符 | 65 个 × 120 字 ≈ 7800 字符 | +6000 | `_MAX_TOOLS_FOR_LLM` 改为 65 |
| **总计** | **~6300 字符** | **~30950 字符** | **+24650 字符** | |

**24650 字符 ≈ 8200 token（中文约 3 字符/token）**

以 DeepSeek-V3 价格（输入 ¥0.5/M token）：
- 每次 LLM 调用多花 ¥0.0041
- 一次图文创作平均 5 轮 LLM 调用 → 总共多花 **¥0.021**
- 以每天 100 次图文创作计 → 每天多花 **¥2.1**

**结论：完全可以接受。花 ¥2.1/天 换来 LLM 能看到全部工具和完整设计系统，产出质量显著提升。**

---

## 实施顺序（每步独立可测试）

### 第零步（前置条件）：修改 `registry.py` 保留 HOT 级 Skill + 修改 `_MAX_TOOLS_FOR_LLM`

**效果**：所有 creation_type 下 HOT 级创作工具都可用；tools schema 容量与目录一致。

**验证方法**：
1. 设置 `creation_type="voiceover"`，检查 `harness.skills` 里是否包含 `card_design`
2. 检查 `_MAX_TOOLS_FOR_LLM` 是否为 65

### 第一步（立即见效）：新增 `design_system_injector.py` + 修改 `loop.py` 注入设计系统

**效果**：LLM 在 system prompt 里就能看到配色方案和配方库，解决"颜色固定"的核心问题。

**验证方法**：
1. 启动后端，发一条"帮我做一期手冲咖啡的图文"
2. 查看 log 中 `_design_block` 的长度和内容
3. 确认 palettes.md 的配色表出现在 system prompt 中
4. 观察 LLM 生成的卡片是否使用了非默认配色（如 Indigo Porcelain 而不是克莱因蓝）

### 第二步（解决可见性）：修改 `skill_router.py` + `loop.py` 用全量目录替代过滤后的 routing table

**效果**：LLM 能看到全部 65 个 Skills 的目录，不再受 SkillRouter 过滤影响。

**验证方法**：
1. 同上测试场景
2. 确认 system prompt 中 `{skill_routing}` 包含了 `infographic`、`poster_hero`、`comparison_card` 等之前不可见的 Skill
3. 尝试说"做个海报"→ 确认 LLM 能找到 `poster_hero` 并调用

### 第三步（打通调用链路）：修改 `_build_tools_schema()` 全量排序注入

**效果**：LLM 的 function calling 列表包含全部工具（触发命中的排前面）。

**验证方法**：
1. 同上测试场景
2. 检查发给 LLM 的 tools 数组长度（应该接近 50 上限）
3. 确认 `card_design`、`infographic` 等都在 tools 列表中

### 第四步（体验优化）：扩充 clarify_schema + trigger_words + 前端 creation_type

**效果**：用户澄清时有更多风格可选，trigger 匹配更准确。

**验证方法**：
1. 测试 card_design 的 clarify 流程，确认能看到 12 种配色选项
2. 测试"做图文"能触发视觉类 Skill 的 trigger 排序提升
3. 检查前端请求中 `creation_type` 的值

---

## 回滚方案

每个改动都是增量式的，回滚简单：

| 改动 | 回滚操作 |
|------|---------|
| 改动 0 | `registry.py` 删除 `_build_skills()` 中的 HOT 级 Skill 保留逻辑 |
| 改动 1 | 删除 `design_system_injector.py`；`loop.py` 里去掉 `_design_block` 注入代码块 |
| 改动 2 | `loop.py` 恢复 `build_routing_table(self._selected_skills)` 替代 `build_compact_catalog(harness.skills)` |
| 改动 3 | `loop.py` 恢复 `_active_skills = self._selected_skills or harness.skills` |
| 改动 4 | `loop.py` 恢复 `skills = self._selected_skills or harness.skills`；`_MAX_TOOLS_FOR_LLM` 改回 50 |
| 改动 5 | 还原 `card-design.md` 的 frontmatter |
| 改动 6 | 还原各 `.md` 文件的 `trigger_words` |
| 改动 7 | 前端去掉 `creation_type` 参数（回退到默认 None） |

---

## 风险点与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| **设计系统知识重复注入** | system prompt 摘要 + execute() 完整版可能矛盾 | 明确分工：system prompt 是"全局导航"（摘要），execute() 是"详细手册"（完整版）；两者内容来源相同，不会矛盾 |
| **system prompt 过长导致 LLM 注意力分散** | LLM 可能忽略某些工具或设计规则 | compact_catalog 每行只有 50 字描述，信息密度高；trigger_matched 排前面引导注意力；设计系统用摘要模式压缩到 45% |
| **tools schema 65 个可能超出部分 LLM 上限** | 部分 LLM 不支持 65 个 function calling | DeepSeek-V3 支持 128+ tools；如用其他模型需测试上限，必要时降回 50 并在 compact_catalog 里标注"部分工具仅在特定场景可用" |
| **不同 creation_type 下设计系统注入不必要的内容** | voiceover 模式不需要 visual 类知识 | `infer_creative_intent()` 按 creation_type 精确映射，voiceover 只注入 writing 类 |
| **_summarize_reference() 摘要质量不稳定** | 可能丢失关键规则 | 保留标题、引用块、表格、emoji 标记行（这些是最关键的规则载体）；普通段落才截断；append 前检查长度保证每行完整 |
| **HOT 级 Skill 跨 creation_type 保留可能引入噪音** | voiceover 模式下 LLM 看到 card_design 但用户不需要 | HOT+CREATE 限定范围（~6 个视觉工具），噪音可控；且 LLM 不会主动调用与用户意图无关的工具 |

---

## 验证场景矩阵

| 场景 | 用户输入 | expected creation_type | 预期注入的知识 | 预期 LLM 行为 |
|------|---------|---------------------|--------------|--------------|
| 图文创作 | "帮我做一期手冲咖啡的图文" | image_text | visual + writing（~10KB 摘要） | 看到 card_design + 全部配色，选 Indigo Porcelain 或 Forest Ink |
| 海报制作 | "做个双11促销海报" | image_text（信号词推断） | visual + writing | 看到 poster_hero + 配色，选合适风格 |
| 对比图 | "iPhone 16 vs Samsung S25 对比图" | image_text（信号词推断） | visual + writing | 看到 comparison_card + 配色 |
| 纯文案 | "写一篇小红书种草文案" | copywrite（若前端传）或 image_text（信号词） | writing（无 visual） | 只看到写作规则，不看到配色 |
| 闲聊 | "今天天气怎么样" | default | writing（最小集） | 不调用任何 Skill，直接回答 |
| 视频脚本 | "帮我写一个探店视频脚本" | video（若前端传） | writing | 看到 voice_builder + 写作规则 |

---

## 与现有架构的关系图

```
                    ┌─────────────────────────────────────┐
                    │           Frontend (ChatView.vue)     │
                    │  creation_type: "image_text" | None   │
                    └──────────────┬──────────────────────┘
                                   │
                                   ▼
                    ┌─────────────────────────────────────┐
                    │     API Router (chat_agent.py)        │
                    │  creation_type: str | None = None      │
                    └──────────────┬──────────────────────┘
                                   │
                                   ▼
              ┌────────────────────┴────────────────────┐
              │         AgentRegistry (registry.py)        │
              │                                          │
              │  第 1 层过滤：                            │
              │  _resolve_creation_type_skills(type)      │
              │  → CREATION_TYPE_SKILLS[type] 映射        │
              │  → 若 type=None → 全量加载（65个）          │
              │  → 若 type="image_text" → ~35个            │
              └────────────────────┬────────────────────┘
                                   │
                                   ▼ harness.skills
              ┌────────────────────┴────────────────────┐
              │       LoopExecutor (loop.py)               │
              │                                          │
              │  _system_prompt():                        │
              │  ① build_compact_catalog(all_skills)      │ ← 改动 2
              │  ② select_skills() → 排序提示             │ （不删除）
              │  ③ build_design_system_block()            │ ← 改动 1（核心）
              │  ④ prompt_guidance(all_skills)            │ ← 改动 3
              │                                          │
              │  _build_tools_schema():                   │
              │  ⑤ 全量 + triggered/hot/rest 排序          │ ← 改动 4
              └────────────────────┬────────────────────┘
                                   │
                                   ▼ system prompt
              ┌────────────────────┴────────────────────┐
              │              LLM (DeepSeek-V3)            │
              │                                          │
              │  收到：                                   │
              │  - 全量工具目录（65个一行摘要）            │
              │  - 设计系统知识（配色+配方+布局摘要）      │
              │  - tools schema（65个，排序后）            │
              │                                          │
              │  决策：                                   │
              │  - 选工具（如 card_design）               │
              │  - 选配色（如 indigo_porcelain）           │
              │  - 选风格参数                             │
              └────────────────────┬────────────────────┘
                                   │ function calling
                                   ▼
              ┌────────────────────┴────────────────────┐
              │  Skill.execute() (如 card_design)         │
              │                                          │
              │  _load_references():                     │
              │  - palettes.md（完整版）                  │ ← 补充细节
              │  - card-recipes.md（完整版）              │
              │  - layout-laws.md（完整版）               │
              │  - anti-ai-slop.md（完整版）              │
              │                                          │
              │  生成最终输出（HTML/SVG/图片URL）          │
              └─────────────────────────────────────────┘
```