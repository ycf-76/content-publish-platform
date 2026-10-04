# 模块规格：publish

## 元信息

| 字段 | 值 |
|------|---|
| 节点类型 | publish |
| AgentDef | `agents/registry.py` → `BUILTIN_AGENTS["publish"]` |
| 节点实现 | `agents/nodes/publish.py` |
| Prompt | 内联 (registry.py) |
| 依赖的 Skills | [] (纯工具调用) |
| 依赖的适配器 | (无 LLM 依赖) |
| 执行器 | loop |
| 下游节点 | card_gen / END |
| 路由函数 | `route_after_publish` (按 model_settings.enable_card_gen) |

## 输入（从 WorkflowState 取）

- node_outputs["final_review"]: 终审通过的内容
- node_outputs["copywrite"]: 文案
- node_outputs["image_gen"]: 图片

## 输出（写入 WorkflowState）

- `node_outputs["publish"]`: dict
  - success: bool
  - post_url: str | None

## 说明

- 小红书直接发布已移除（风控风险）
- 当前 publish 节点主要做内容组装和状态标记
- 实际发布走后处理节点: card_gen → wechat_push / feishu_push

## Recovery 策略

- max_attempts: 2
- strategies: [retry]

## 后处理链

```
publish → card_gen (可选) → wechat_push (可选) → feishu_push (可选) → END
```

启用条件由 `model_settings.enable_card_gen / enable_wechat_push / enable_feishu_push` 控制。