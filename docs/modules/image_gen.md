# 模块规格：image_gen

## 元信息

| 字段 | 值 |
|------|---|
| 节点类型 | image_gen |
| AgentDef | `agents/registry.py` → `BUILTIN_AGENTS["image_gen"]` |
| 节点实现 | `agents/nodes/image_gen.py` |
| Prompt | 内联 (registry.py) |
| 依赖的 Skills | (无显式 Skill，直接调 adapter) |
| 依赖的适配器 | image_gen (WanxAdapter 主力 / PollinationsAdapter 备用) |
| 执行器 | single_shot |
| 下游节点 | image_review / image_plan (回退) |
| 路由函数 | `route_after_image_gen` |

## 输入（从 WorkflowState 取）

- node_outputs["image_plan"]: 图片规划方案
- model_settings.image_model: str — 生图模型
- model_settings.image_style: str — 图片风格
- image_assets: list[dict] — 用户本地图片
- asset_mode: bool — 无模板模式
- platform: str — 目标平台
- format_name: str — 输出比例 (1080x1440 / 1024x1024 / 720x1280)

## 输出（写入 WorkflowState）

- `node_outputs["image_gen"]`: dict
  - images: list[dict] — 生成的图片 (base64 / url / metadata)

## 生图适配器

| 适配器 | 模型 | 需要 Key | 特点 |
|--------|------|---------|------|
| WanxAdapter | wanx2.1-t2i-turbo (推荐) | DASHSCOPE_API_KEY | 阿里云百炼，国内直连，异步任务模式 |
| WanxAdapter | wanx2.1-t2i-plus | DASHSCOPE_API_KEY | 高质量版 |
| PollinationsAdapter | pollinations | 无 | 免费，国内可能需代理 |

尺寸映射：1080x1440 → 768*1152 (3:4竖图) / 1024x1024 → 1024*1024 (方图) / 720x1280 → 720*1280 (9:16竖图)

## Recovery 策略

- max_attempts: 3 (默认)
- strategies: [retry, simplify_prompt, switch_model]

## 可扩展点

- 新增生图模型 = 在 `adapters/image_gen.py` 加 Adapter 子类
- 不需要改 image_gen.py / graph.py