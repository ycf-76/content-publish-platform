# 模块规格：search

## 元信息

| 字段 | 值 |
|------|---|
| 节点类型 | search |
| AgentDef | `agents/registry.py` → `BUILTIN_AGENTS["search"]` |
| 节点实现 | `agents/nodes/search.py` |
| Prompt | 内联 (registry.py) |
| 依赖的 Skills | trending_search |
| 依赖的适配器 | deepseek (V3) |
| 执行器 | loop |
| 下游节点 | analyze / END |
| 路由函数 | `route_after_search` |

## 输入（从 WorkflowState 取）

- topic: str
- search_keyword: str (未传时用 topic)
- model_settings: dict

## 输出（写入 WorkflowState）

- `node_outputs["search"]`: dict
  - results: list[dict] — 搜索结果 (title/summary/url/platform/likes/comments)
  - keyword_used: str — 实际使用的搜索词

## 硬规则

- search_result_non_empty: 结果数 >= 1 (否则触发 recovery)
- rate_limit_check: API 调用频率检查

## Recovery 策略

- max_attempts: 3
- strategies: [retry, broaden_keyword, switch_model:deepseek-v3]

## 可扩展点

- 新增数据源 = 在 `tools/sources/` 加 Source 子类 + 注册到 SourceManager
- 不需要改 search.py / graph.py