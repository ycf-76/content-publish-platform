# 模块规格：copywrite

## 元信息

| 字段 | 值 |
|------|---|
| 节点类型 | copywrite |
| AgentDef | `agents/registry.py` → `BUILTIN_AGENTS["copywrite"]` |
| 节点实现 | `agents/nodes/copywrite.py` |
| Prompt | 内联 (registry.py) |
| 依赖的 Skills | copywrite_builder (4 个子类: LivelyGirl / Elegant / Professional / Casual) |
| 依赖的适配器 | deepseek (R1) |
| 执行器 | single_shot |
| 下游节点 | image_plan / analyze (回退) |
| 路由函数 | `route_after_copywrite` |

## 输入（从 WorkflowState 取）

- topic: str
- search_keyword: str
- creative_brief: str
- node_outputs["search"]: 搜索结果
- node_outputs["analyze"]: 分析洞察
- model_settings.writing_style: str — 风格选择 (路由到对应 Skill 子类)
- model_settings.skill_name: str — Skill 路由名
- reference: dict — 选题池参考素材
- user_profile: dict — 创作者画像

## 输出（写入 WorkflowState）

- `node_outputs["copywrite"]`: dict
  - title: str — 标题
  - content: str — 正文
  - tags: list[str] — 标签

## 硬规则

- (无显式 hard_rules，由 soft_semantic 覆盖)

## 软语义

- enabled: True
- 判断内容: 调性匹配 / 内容空洞 / 标题吸引力

## Recovery 策略

- max_attempts: 3
- strategies: [retry, simplify_prompt, switch_model:deepseek-v3]

## 可扩展点

- 新增文案风格 = 在 `tools/copywrite_builder.py` 加 Skill 子类 + @register
- 不需要改 copywrite.py / graph.py
- 前端在 model_settings.writing_style 中传风格名即可路由