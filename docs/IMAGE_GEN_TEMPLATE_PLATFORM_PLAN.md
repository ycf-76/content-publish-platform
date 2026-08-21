# 图片生成模板平台方案

## 目标

把图片生成节点从硬编码模板和巨型 Prompt，升级为可扩展的模板平台。用户可以使用内置模板、自定义模板、自定义格式方案，也可以导入本地图片走无模板照片模式。

核心原则：

- 节点卡片负责工作流状态和摘要，不承载完整编辑器。
- 内容规划、模板选择、格式方案、图片素材、渲染执行互相解耦。
- 新增模板或平台尺寸不改主流程代码。

## 当前问题

硬编码集中在：

- `backend/app/agents/nodes/image_plan.py`
- `backend/app/tools/blueprint_skill.py`
- `backend/app/services/card_renderer.py`
- `frontend/src/card-editor/templates.ts`
- `frontend/src/card-editor/esther-templates.ts`

表现是：

1. LLM Prompt 写死模板名、页面类型和字段定义。
2. 模板推荐依赖关键词数组。
3. 装饰层和样式预设在 Python、TypeScript 两侧重复。
4. 只支持小红书 3:4，平台和尺寸不可扩展。
5. 用户不能规划每页模板，也不能导入本地图片。
6. 图片编辑器被嵌入节点卡片，空间和交互都不够。

## 目标架构

```text
ContentPlanner     决定每一页说什么
TemplateMatcher    决定用哪套模板、平台和尺寸
TemplateRegistry   保存模板 Schema、Theme、Renderer
FormatPlan         保存用户自定义格式方案
AssetLibrary       保存用户上传图片和 AI 生成图
Renderer           把内容、模板、素材渲染成图片
```

关键链路：

```text
TemplateRegistry --schema--> ContentPlanner
```

ContentPlanner 的 Prompt 不硬编码 page type 字段定义，而是从
`TemplateManifest.fields` 和 `TemplateManifest.page_types` 动态生成。

## 核心数据模型

### TemplateManifest

```json
{
  "id": "esther_steps_v2",
  "name": "Esther 步骤卡",
  "category": ["教程", "知识"],
  "description": "适合步骤教程和干货内容",
  "platforms": {
    "xiaohongshu": {
      "format": "3:4",
      "width": 1080,
      "height": 1440
    }
  },
  "schema": {
    "fields": [
      {"key": "title", "type": "string", "label": "标题", "required": true},
      {"key": "steps", "type": "array", "label": "步骤"}
    ]
  },
  "theme": {
    "bg": "#FEFCF6",
    "text": "#1A1A2E",
    "accent": "#2B7FD8"
  },
  "default_decoration": {
    "type": "gradient_orbs",
    "color1": "#2B7FD8",
    "color2": "#F4D758",
    "opacity": 0.25
  },
  "renderer": "frontend_builtin",
  "source": "builtin"
}
```

### ContentPlan

LLM 只输出语义内容，不选模板。

```json
{
  "pages": [
    {
      "type": "steps",
      "data": {
        "title": "3 步学会 AI 写作",
        "steps": [
          {"title": "定主题", "desc": "明确用户想解决的问题"}
        ]
      }
    }
  ],
  "constraints": {
    "platform": "xiaohongshu",
    "format": "3:4",
    "content_type": "教程型"
  }
}
```

### FormatPlan

用户可自定义每页模板和图片来源。

```json
{
  "platform": "xiaohongshu",
  "format": "3:4",
  "page_count": 4,
  "pages": [
    {
      "index": 0,
      "source": "template",
      "template_id": "esther_cover_v1"
    },
    {
      "index": 1,
      "source": "template",
      "template_id": "esther_steps_v2"
    },
    {
      "index": 2,
      "source": "asset",
      "asset_id": "img_local_001",
      "fit": "cover"
    },
    {
      "index": 3,
      "source": "mixed",
      "asset_id": "img_bg_001",
      "overlay": {
        "template_id": "minimal_overlay"
      }
    }
  ]
}
```

页面来源：

- `template`：纯模板页。
- `asset`：纯图片页。
- `mixed`：本地图片作为背景，模板作为文字层。该模式在 Phase 4 落地。

## 分期执行

### Phase 1：TemplateRegistry 地基

目标：先建立模板注册表和查询 API，不破坏现有工作流。

范围：

- 定义 `TemplateManifest`、`PlatformFormat`、`TemplateSchema`。
- 创建 `TemplateRegistry` 单例。
- 注册 6 套现有内置模板：
  - `minimal_white`
  - `warm_card`
  - `dark_tech`
  - `esther_brand`
  - `esther_dark`
  - `esther_warm`
- 增加 `GET /api/templates`。
- 增加 `GET /api/templates/{template_id}`。
- 支持按 `platform`、`category` 过滤。
- `_recommend_template()` 通过 `TemplateRegistry` 的 category 查询模板，不再维护独立关键词映射。
- 前端在 ImagePlanCard 加载时调用 `/api/templates` 并缓存到 `templates` store，但不替换现有渲染逻辑。

验收：

- 后端测试通过。
- `/api/templates` 返回 6 套内置模板。
- 旧工作流继续使用现有 `card_draft` 和前端模板，不回归。
- `TemplateManifest` 包含 `default_decoration`，模板推荐统一走 Registry。

### Phase 2：重写 image_plan_node

目标：把内容规划与模板选择解耦。

范围：

- 删除 image_plan 中的巨型 Prompt。
- 增加 `ContentPlanner`。
- 增加 `TemplateMatcher`。
- `image_plan_node` 输出 `content_plan`、推荐 `template_id` 和 `format_plan`。
- `card_draft` 字段保留但标记为 deprecated，前端先做两版兼容。

验收：

- image_plan 中不再出现模板名、页面类型字段定义和关键词数组。
- LLM 输出失败时仍走确定性 fallback。
- Prompt 中的页面类型和字段定义从 `TemplateRegistry` 动态生成。

### Phase 3：用户自定义模板与格式方案

目标：用户可以使用、调整、保存自己的模板和格式方案。

范围：

- 模板包扫描和导入。
- 用户模板存储。
- 每页模板选择和顺序编辑。
- 保存和复用 FormatPlan。

验收：

- 用户新增模板后前端可以展示和编辑。
- 用户保存格式方案后可以在后续工作流复用。

Phase 3 同时收口 Phase 2 的三项遗留：

1. 消除 `is_esther` 分支：
   `build_fallback_card_draft()` 和 `_build_structured_draft()` 当前通过
   `suggested_template.startswith("esther_")` 判断是否填充
   `highlight`、`tag`、`decoNumber`、`emoji` 等字段。后续改为遍历
   `TemplateManifest.fields`，字段存在就填，不存在就不填。

2. 消除关键词硬编码：
   `TemplateMatcher.match_template()` 中的 `category_keywords` 迁移到
   `TemplateManifest` 的扩展字段，让新增模板自带关键词，不用改 matcher 代码。

3. 默认模板 ID 收口：
   将 `esther_brand` 字符串兜底改为从 `TemplateRegistry` 取第一个模板，
   或定义统一的 `DEFAULT_TEMPLATE_ID` 常量。

### Phase 4：本地图片素材库与无模板模式

目标：支持用户本地图片，不依赖模板。

范围：

- 图片上传、校验、去 EXIF、缩略图。
- AssetLibrary。
- 纯图片模式。
- 混合模式。

验收：

- 用户可以批量导入本地图片。
- 用户可以直接使用自己的照片发布，不生成 card_draft。
- 图片资产按用户隔离。

### Phase 5：多社媒尺寸和品牌 Kit

目标：同一内容适配不同平台尺寸。

范围：

- 平台 profile。
- 3:4、9:16、1:1 尺寸映射。
- 安全边距。
- 品牌色、字体、头像和署名注入。

验收：

- 同一内容可以切换小红书 3:4 和抖音 9:16。
- 模板自动应用安全边距和品牌配置。

### Phase 6：独立图片工作区 UI

目标：把完整编辑器从节点卡片中移出。

范围：

- `ImageWorkspace` 中央工作区。
- `ImageGenCard` 只保留状态摘要和入口。
- 节点 UI 类型：`inline`、`inspector`、`workspace`、`modal`。

验收：

- 图片节点卡片高度固定。
- 图片编辑器在中央工作区完成。
- 搜索、分析、文案节点仍保持轻量卡片。

## 执行顺序

```text
Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6
```

Phase 1 是当前最先执行的一期。
