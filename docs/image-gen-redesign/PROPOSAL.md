# 图片生成节点重构方案 — 从 AI 自动生图到用户掌控编排

> 本方案基于用户 4 项关键决策：
> 1. 节点架构：image_gen 拆分为 image_plan + image_workshop 两节点
> 2. 第一期模板：流程图、要点列表、时间线（3 种）
> 3. 背景图制作器：嵌入审核节点
> 4. 落地节奏：先出完整方案文档，review 后再分阶段实现

---

## 一、产品定位转变

### 1.1 当前痛点

| 痛点 | 当前实现 | 问题 |
|------|----------|------|
| AI 生图能力边界 | MarkdownCardSkill（HTML→PNG）+ 通义万相 | 无法精确表达流程图/对比图/时间线等结构化内容 |
| 用户无法掌控 | 图片完全由 AI 生成，用户只能通过/打回 | 真实博主多用实拍/截图/手绘，AI 覆盖不了 |
| 尺寸固定 | 写死 3:4（1080x1440） | 不同内容适合不同比例 |
| 排版 AI 味道 | 4 种固定风格 + 封面+内容两段式 | 一眼 AI，不够自然 |

### 1.2 新定位

**从"AI 自动生图为主"转向"用户掌控 + 多来源编排"**

- 图片来源三选一：用户上传（优先） / 平台背景图制作器 / AI 生图（兜底）
- 结构化内容用预设模板渲染（流程图/要点列表/时间线），LLM 填充数据而非"描述图片"
- 审核节点升级为图片编排工作台，用户逐张选择来源 + 编辑

---

## 二、工作流架构调整

### 2.1 节点拆分

**当前**：
```
copywrite → image_gen（AI 生图）→ image_review（通过/打回）→ audit
```

**新架构**：
```
copywrite → image_plan（LLM 规划图片类型+结构化数据）
         → image_workshop（用户编排工作台，interrupt）
              ├─ A. 用户上传本地图片
              ├─ B. 平台背景图制作器（嵌入）
              ├─ C. AI 生图（兜底/补充）
              └─ D. 结构化图表模板渲染（流程图/要点列表/时间线）
              + 裁剪/文字叠加/顺序调整
         → audit
```

### 2.2 image_plan 节点职责

**输入**：copywrite 节点的 title / content / tags

**LLM 任务**：分析文案内容，规划需要几张图、每张图什么类型、什么内容

**输出**（image_plan 结构）：
```json
{
  "image_count": 3,
  "plan": [
    {
      "index": 0,
      "role": "cover",
      "image_type": "background",
      "suggestion": "封面图：用背景图制作器做一张带大标题的封面"
    },
    {
      "index": 1,
      "role": "content",
      "image_type": "flow",
      "template_data": {
        "title": "5步搞定XXX",
        "steps": [
          {"title": "准备材料", "desc": "需要A、B、C"},
          {"title": "混合搅拌", "desc": "顺时针搅拌30秒"}
        ]
      },
      "suggestion": "流程图：用模板渲染，展示操作步骤"
    },
    {
      "index": 2,
      "role": "content",
      "image_type": "list",
      "template_data": {
        "title": "注意事项",
        "items": [
          {"num": "01", "title": "温度控制", "desc": "保持180度"},
          {"num": "02", "title": "时间把握", "desc": "不超过20分钟"}
        ]
      },
      "suggestion": "要点列表：用模板渲染，列出关键注意点"
    }
  ]
}
```

**关键**：image_plan 不生成图片，只输出规划。结构化数据由 LLM 填充（流程图的 steps、列表的 items、时间线的 events）。

### 2.3 image_workshop 节点职责

这是新的审核节点，替代原 image_review。

**展示**：image_plan 的规划（每张图的建议类型 + 内容）

**用户操作**（对每张图）：
1. 选择来源：
   - 用模板渲染（看到 image_plan 的 template_data 预览）
   - 上传本地图片
   - 制作背景图（打开嵌入的背景图制作器）
   - AI 生图（调通义万相/卡片渲染）
2. 编辑（可选）：
   - 裁剪（按 1:1 / 3:4 / 4:3 比例）
   - 叠加文字
   - 调整顺序（拖拽排序）
3. 确认 → 输出最终 images_base64 + image_details

**输出**：
```json
{
  "images_base64": ["base64_0", "base64_1", "base64_2"],
  "image_details": [
    {"source": "template", "type": "flow", "size": "3:4"},
    {"source": "upload", "type": "photo", "size": "3:4"},
    {"source": "background_maker", "type": "background", "size": "3:4"}
  ],
  "image_count": 3,
  "style": "用户编排"
}
```

### 2.4 路由调整

[graph.py](file:///d:/My_Project/多智能体小红书发布平台/backend/app/agents/graph.py) 路由变更：

```python
# 旧路由
graph.add_edge("quality_check_copywrite", "image_gen")  # copywrite → image_gen
graph.add_conditional_edges("image_gen", route_after_image_gen, ...)
graph.add_conditional_edges("image_review", route_after_image_review, {"audit": "audit", "image_gen": "image_gen"})

# 新路由
graph.add_edge("quality_check_copywrite", "image_plan")  # copywrite → image_plan
graph.add_edge("image_plan", "image_workshop")           # image_plan → image_workshop
# image_workshop 用 interrupt_before 暂停，等用户编排
graph.add_conditional_edges(
    "image_workshop",
    route_after_image_workshop,
    {"audit": "audit", "image_plan": "image_plan"},  # pass → audit, reject → 回 image_plan 重新规划
)
```

**回退路径**：image_workshop 打回 → image_plan 重新规划（不是回 image_workshop 自己）

---

## 三、结构化图表模板设计（第一期 · 核心）

### 3.1 模板渲染架构

复用现有 [card_renderer.py](file:///d:/My_Project/多智能体小红书发布平台/backend/app/services/card_renderer.py) 的 Playwright HTML→PNG 能力，但：
- 不再只有"封面+内容"两段式
- 新增 3 种结构化模板：流程图、要点列表、时间线
- 每种模板有独立的 HTML 结构和 CSS

### 3.2 流程图模板（flow）

**适用**：操作教程、步骤指南、流程说明

**数据结构**：
```json
{
  "type": "flow",
  "title": "5步搞定完美煎蛋",
  "style": "fresh_natural",
  "steps": [
    {"title": "热锅", "desc": "中火预热30秒"},
    {"title": "下油", "desc": "倒入少许橄榄油"},
    {"title": "打蛋", "desc": "小火缓慢打入"},
    {"title": "煎制", "desc": "2-3分钟至蛋白凝固"},
    {"title": "出锅", "desc": "撒盐和黑胡椒"}
  ]
}
```

**HTML 结构**（关键部分）：
```html
<div class="flow-card">
  <h1 class="flow-title">5步搞定完美煎蛋</h1>
  <div class="flow-steps">
    <div class="flow-step">
      <div class="step-num">1</div>
      <div class="step-content">
        <div class="step-title">热锅</div>
        <div class="step-desc">中火预热30秒</div>
      </div>
    </div>
    <div class="step-arrow">↓</div>
    <div class="flow-step">...</div>
  </div>
</div>
```

**视觉特点**：
- 竖向排列的步骤卡片，步骤间用箭头连接
- 每步带序号圆圈 + 标题 + 说明
- 配色沿用现有 4 种风格（fresh_natural 等）

### 3.3 要点列表模板（list）

**适用**：干货总结、注意事项、清单

**数据结构**：
```json
{
  "type": "list",
  "title": "新手煎蛋的5个避坑要点",
  "style": "fresh_natural",
  "items": [
    {"num": "01", "title": "温度控制", "desc": "火候太大容易焦"},
    {"num": "02", "title": "油量把握", "desc": "少许即可，太多会溅"},
    {"num": "03", "title": "时间把握", "desc": "不超过3分钟"}
  ]
}
```

**HTML 结构**：
```html
<div class="list-card">
  <h1 class="list-title">新手煎蛋的5个避坑要点</h1>
  <div class="list-items">
    <div class="list-item">
      <div class="item-num">01</div>
      <div class="item-content">
        <div class="item-title">温度控制</div>
        <div class="item-desc">火候太大容易焦</div>
      </div>
    </div>
  </div>
</div>
```

**视觉特点**：
- 大号序号 + 标题 + 说明的横向布局
- 序号用强调色，标题加粗，说明灰色

### 3.4 时间线模板（timeline）

**适用**：成长历程、事件演进、发展过程

**数据结构**：
```json
{
  "type": "timeline",
  "title": "我的烘焙成长之路",
  "style": "fresh_natural",
  "events": [
    {"time": "2023.01", "title": "入门", "desc": "买了第一个烤箱"},
    {"time": "2023.06", "title": "进阶", "desc": "学会做戚风蛋糕"},
    {"time": "2024.01", "title": "精通", "desc": "开了一家小工作室"}
  ]
}
```

**HTML 结构**：
```html
<div class="timeline-card">
  <h1 class="timeline-title">我的烘焙成长之路</h1>
  <div class="timeline-track">
    <div class="timeline-event">
      <div class="event-time">2023.01</div>
      <div class="event-dot"></div>
      <div class="event-content">
        <div class="event-title">入门</div>
        <div class="event-desc">买了第一个烤箱</div>
      </div>
    </div>
  </div>
</div>
```

**视觉特点**：
- 竖向时间轴，左侧时间 + 圆点 + 右侧内容
- 圆点用强调色，连线为虚线或实线

### 3.5 模板渲染接口

后端新增 [card_renderer.py](file:///d:/My_Project/多智能体小红书发布平台/backend/app/services/card_renderer.py) 函数：

```python
async def render_template_to_base64(
    template_type: str,  # "flow" | "list" | "timeline"
    data: dict,          # 模板数据
    style: str = "fresh_natural",
    size: str = "3:4",   # "1:1" | "3:4" | "4:3"
) -> str:
    """渲染结构化模板为 base64 PNG。
    
    根据 template_type 选择对应 HTML 模板，填充 data，渲染为 PNG。
    """
    html = _build_template_html(template_type, data, style, size)
    width, height = _get_size_dimensions(size)
    return await render_html_to_base64(html, width, height)


def _get_size_dimensions(size: str) -> tuple[int, int]:
    """尺寸映射。"""
    sizes = {
        "1:1": (1080, 1080),
        "3:4": (1080, 1440),
        "4:3": (1440, 1080),
    }
    return sizes.get(size, (1080, 1440))
```

### 3.6 去 AI 味道的排版优化

**当前问题**：4 种风格模板（清新自然/日系胶片/暖阳滤镜/复古胶片）配色太"工整"，一眼 AI。

**优化方向**：
1. **增加排版变体**：同一种风格下，封面布局有 3-4 种变体（左对齐/居中/底部署名/侧边标签）
2. **手写字体支持**：部分模板用手写风格字体（可通过 Google Fonts 引入手写体）
3. **便签风/截图拼接风**：新增"便签风"风格（米黄色背景 + 手写字 + 胶带效果）
4. **留白和不对称**：打破当前的对称居中布局，增加设计感

---

## 四、三来源图片编排

### 4.1 来源 A：用户上传

**前端**：
- 拖拽上传 + 点击选择
- 支持 JPG/PNG/WebP
- 上传后预览，可裁剪

**后端**：
- 新增接口 `POST /api/workflows/{id}/images/upload`
- 图片存储到本地 `uploads/workflows/{workflow_id}/` 目录
- 返回 base64 给前端预览

**接口设计**：
```python
@router.post("/{workflow_id}/images/upload")
async def upload_image(
    workflow_id: str,
    file: UploadFile,
    index: int = Form(...),  # 图片位置索引
) -> StandardResponse[dict]:
    """上传用户图片，返回 base64 预览。"""
    # 1. 校验文件类型/大小（< 10MB）
    # 2. 读取文件，转 base64
    # 3. 可选：存储到本地
    # 4. 返回 base64 + 文件信息
    return StandardResponse(data={
        "index": index,
        "base64": base64_str,
        "size_bytes": len(content),
        "mime": file.content_type,
    })
```

### 4.2 来源 B：平台背景图制作器（嵌入审核节点）

**功能**：用户在工作台内制作简单背景图

**编辑器能力**：
- 选择背景：纯色 / 渐变 / 纹理（预设 6-8 种）
- 添加文字：标题（大字）+ 副标题（小字）
- 选择尺寸：1:1 / 3:4 / 4:3
- 字体选择：3-4 种（含手写风）

**技术实现**：前端 Canvas 实时渲染，导出为 base64 PNG

**前端组件**：
```vue
<template>
  <div class="bg-maker">
    <!-- 左侧控制面板 -->
    <div class="bg-maker-controls">
      <div class="control-section">
        <label>背景</label>
        <div class="bg-options">
          <button v-for="bg in backgrounds" @click="selectBg(bg)">{{ bg.name }}</button>
        </div>
      </div>
      <div class="control-section">
        <label>标题</label>
        <input v-model="title" placeholder="输入标题">
      </div>
      <div class="control-section">
        <label>副标题</label>
        <input v-model="subtitle" placeholder="输入副标题">
      </div>
      <div class="control-section">
        <label>尺寸</label>
        <select v-model="size">
          <option value="1:1">1:1 方形</option>
          <option value="3:4">3:4 竖图</option>
          <option value="4:3">4:3 横图</option>
        </select>
      </div>
    </div>
    <!-- 右侧预览 -->
    <canvas ref="canvasRef" :width="canvasWidth" :height="canvasHeight"></canvas>
    <button @click="exportPng">导出并使用</button>
  </div>
</template>
```

### 4.3 来源 C：AI 生图（兜底）

保留现有 [image_gen_node](file:///d:/My_Project/多智能体小红书发布平台/backend/app/agents/graph.py#L670) 的通义万相 + MarkdownCardSkill 能力，作为：
- image_workshop 中的一个"AI 生成"选项
- 用户对某张图不满意时可点"用 AI 重新生成"

---

## 五、前端图片编辑器设计

### 5.1 编辑器架构

image_workshop 节点的前端是一个**图片编排工作台**，包含：

```
┌─────────────────────────────────────────────────┐
│  图片编排工作台                                    │
├─────────────────────────────────────────────────┤
│  ┌─图片1─┐  ┌─图片2─┐  ┌─图片3─┐  [+ 添加]      │
│  │ 预览  │  │ 预览  │  │ 预览  │                │
│  │       │  │       │  │       │                │
│  │ 模板  │  │ 上传  │  │ 背景图 │                │
│  └───────┘  └───────┘  └───────┘                │
│  [拖拽排序]                                      │
├─────────────────────────────────────────────────┤
│  当前编辑：图片1                                  │
│  ┌─────────────┐  ┌──────────────────────────┐  │
│  │             │  │ 来源选择：                │  │
│  │   预览区    │  │ [模板] [上传] [背景图] [AI]│  │
│  │             │  │                          │  │
│  │             │  │ 编辑工具：                │  │
│  │             │  │ [裁剪] [文字] [尺寸]      │  │
│  └─────────────┘  └──────────────────────────┘  │
├─────────────────────────────────────────────────┤
│           [打回重新规划]  [确认完成]              │
└─────────────────────────────────────────────────┘
```

### 5.2 技术选型

| 功能 | 库 | 说明 |
|------|-----|------|
| 图片上传 | 原生 input + 拖拽 API | 无需额外库 |
| 裁剪 | cropperjs | 轻量，支持按比例裁剪 |
| 顺序调整 | vuedraggable | 拖拽排序 |
| 文字叠加 | canvas API | 在 canvas 上绘制文字 |
| 背景图制作 | canvas API | 实时渲染 + 导出 PNG |

### 5.3 编辑器状态管理

```typescript
// stores/workflow.ts 新增
interface ImageWorkshopState {
  plan: ImagePlanItem[]           // image_plan 的规划
  images: ImageWorkshopItem[]     // 用户编排的图片
  currentEditIndex: number        // 当前编辑的图片索引
  editorMode: 'template' | 'upload' | 'background' | 'ai'
}

interface ImageWorkshopItem {
  index: number
  source: 'template' | 'upload' | 'background' | 'ai'
  base64: string
  size: '1:1' | '3:4' | '4:3'
  // 编辑数据（用于再次编辑）
  editData?: {
    templateType?: string
    templateData?: any
    cropBox?: CropBox
    textOverlays?: TextOverlay[]
  }
}
```

---

## 六、后端接口设计

### 6.1 新增接口

```python
# 1. 渲染结构化模板
@router.post("/{workflow_id}/images/render-template")
async def render_template(
    workflow_id: str,
    request: RenderTemplateRequest,  # {template_type, data, style, size}
) -> StandardResponse[dict]:
    """渲染结构化图表模板为 base64 PNG。"""
    from app.services.card_renderer import render_template_to_base64
    b64 = await render_template_to_base64(
        request.template_type, request.data, request.style, request.size
    )
    return StandardResponse(data={"base64": b64, "size": request.size})

# 2. 上传图片
@router.post("/{workflow_id}/images/upload")
async def upload_image(...) -> StandardResponse[dict]:
    """上传用户图片。"""
    # 读取文件 → base64 → 返回

# 3. 确认图片编排（image_workshop 通过）
@router.post("/{workflow_id}/review")
async def submit_review(...):
    # 复用现有 review 接口，pass 时带上 images_base64
    # request 新增字段：images_base64, image_details
```

### 6.2 image_plan 节点实现

```python
async def image_plan_node(state: WorkflowState) -> dict:
    """图片规划节点：LLM 分析文案，输出图片规划。
    
    不生成图片，只输出 image_plan（每张图的类型+模板数据）。
    """
    workflow_id = state["workflow_id"]
    node_id = "image_plan"
    
    await emit_node_event(workflow_id, node_id, "node_started")
    
    # 读取 copywrite 输出
    copywrite_output = state.get("node_outputs", {}).get("copywrite", {})
    title = copywrite_output.get("title", "")
    content = copywrite_output.get("content", "")
    tags = copywrite_output.get("tags", [])
    
    # LLM 规划图片
    plan = await _llm_plan_images(title, content, tags)
    
    output = {
        "image_plan": plan,
        "image_count": len(plan["plan"]),
    }
    
    await emit_node_event(workflow_id, node_id, "node_completed", output)
    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.COMPLETED.value},
        "node_outputs": {node_id: output},
    }


async def _llm_plan_images(title, content, tags) -> dict:
    """调 LLM 规划图片。
    
    Prompt 设计：
    - 分析文案内容，判断需要几张图
    - 每张图判断类型：cover(background) / flow / list / timeline / photo
    - 对结构化类型，填充 template_data
    """
    # LLM prompt + 调用
    pass
```

### 6.3 image_workshop 节点实现

```python
async def image_workshop_node(state: WorkflowState) -> dict:
    """图片编排工作台节点：interrupt 等待用户编排。
    
    用户在审核界面：
    1. 看到 image_plan 的规划
    2. 对每张图选择来源（模板/上传/背景图/AI）
    3. 编辑（裁剪/文字/顺序）
    4. 确认 → submit_review 带上 images_base64
    """
    workflow_id = state["workflow_id"]
    node_id = "image_workshop"
    
    # 读取审核状态（pass 时 submit_review 通过 update_state 设为 passed）
    review_status = state.get("node_statuses", {}).get(node_id, "pending")
    is_passed = review_status == NodeStatus.PASSED.value
    
    await emit_node_event(workflow_id, node_id, "node_started")
    
    if is_passed:
        # 用户已确认，读取 submit_review 传入的 images_base64
        # submit_review 时通过 update_state 写入 node_outputs
        workshop_output = state.get("node_outputs", {}).get(node_id, {})
        output = {
            "images_base64": workshop_output.get("images_base64", []),
            "image_details": workshop_output.get("image_details", []),
            "image_count": workshop_output.get("image_count", 0),
            "style": "用户编排",
        }
        await emit_node_event(workflow_id, node_id, "node_completed", output)
        return {
            "current_node": node_id,
            "node_statuses": {node_id: NodeStatus.PASSED.value},
            "node_outputs": {node_id: output},
        }
    
    # 首次进入，推送 review_required（前端展示编排工作台）
    # image_plan 的规划通过 review_required 事件传给前端
    image_plan = state.get("node_outputs", {}).get("image_plan", {}).get("image_plan", {})
    
    await emit_workflow_event(workflow_id, "review_required", {
        "review_node": node_id,
        "review_type": "image_workshop",
        "image_plan": image_plan,
    })
    
    return {
        "current_node": node_id,
        "node_statuses": {node_id: NodeStatus.AWAITING_REVIEW.value},
    }
```

### 6.4 submit_review 改造

image_workshop 的 pass 需要带上用户编排的图片数据：

```python
# review.py 的 submit_review 接口
@router.post("/{workflow_id}/review")
async def submit_review(
    workflow_id: str,
    request: ReviewActionRequest,  # 新增 images_base64, image_details 字段
    db: AsyncSession = Depends(get_db),
) -> StandardResponse[dict]:
    """提交审核结果。
    
    image_workshop 的 pass 需要带上用户编排的图片数据。
    """
    service = get_workflow_service(db)
    result = await service.submit_review(
        workflow_id=workflow_id,
        action=request.action,
        user_id=user_id,
        feedback=request.feedback,
        # 新增：图片编排数据
        images_base64=request.images_base64,
        image_details=request.image_details,
    )
    ...
```

submit_review 方法内，对 image_workshop 的 pass：
```python
if action == "pass" and review_node == "image_workshop":
    # 把用户编排的图片数据写入 state
    graph.update_state(
        config,
        {
            "node_statuses": {review_node: NodeStatus.PASSED.value},
            "node_outputs": {review_node: {
                "images_base64": images_base64,
                "image_details": image_details,
                "image_count": len(images_base64),
            }},
        },
    )
```

---

## 七、数据模型变更

### 7.1 WorkflowState 新增字段

```python
class WorkflowState(TypedDict, total=False):
    # ... 现有字段 ...
    image_plan: dict  # 新增：image_plan 节点的规划输出
```

### 7.2 NodeType 枚举新增

```python
class NodeType(str, Enum):
    SEARCH = "search"
    ANALYZE = "analyze"
    COPYWRITE = "copywrite"
    IMAGE_PLAN = "image_plan"          # 新增
    IMAGE_WORKSHOP = "image_workshop"  # 新增（替代 IMAGE_REVIEW）
    # IMAGE_GEN = "image_gen"          # 废弃
    # IMAGE_REVIEW = "image_review"    # 废弃
    AUDIT = "audit"
    FINAL_REVIEW = "final_review"
    PUBLISH = "publish"
```

### 7.3 数据库迁移

- workflow_nodes 表的 node_type 枚举新增 image_plan / image_workshop
- 旧工作流的 image_gen / image_review 节点保留（兼容历史数据）

---

## 八、阶段规划

### 第一期：结构化图表模板 + image_plan 节点（2-3 天）

**目标**：LLM 能识别内容类型并用模板渲染结构化图表

**范围**：
1. 后端 [card_renderer.py](file:///d:/My_Project/多智能体小红书发布平台/backend/app/services/card_renderer.py) 新增 3 种模板渲染（流程图/要点列表/时间线）
2. 后端 [graph.py](file:///d:/My_Project/多智能体小红书发布平台/backend/app/agents/graph.py) 新增 image_plan 节点（LLM 规划图片类型+填充模板数据）
3. 后端新增 `POST /api/workflows/{id}/images/render-template` 接口
4. 前端 image_review 审核界面增加"用模板渲染"预览能力
5. 暂不拆分节点，image_plan 作为 image_gen 的前置步骤

**验收**：工作流跑完后，能看到 LLM 根据内容自动选择流程图/列表/时间线模板并渲染

### 第二期：image_workshop 节点 + 用户上传（3-4 天）

**目标**：用户能上传自己的图片替代 AI 生成

**范围**：
1. 后端拆分 image_gen → image_plan + image_workshop
2. 后端新增 `POST /api/workflows/{id}/images/upload` 接口
3. 前端 image_workshop 编排工作台（上传+预览+顺序调整）
4. 前端审核按钮改造（pass 时带上 images_base64）
5. submit_review 改造支持 image_workshop 的图片数据

**验收**：用户能在编排工作台上传自己的图片，确认后工作流继续

### 第三期：背景图制作器 + 裁剪 + 文字叠加（3-4 天）

**目标**：用户能在工作台内制作背景图 + 编辑图片

**范围**：
1. 前端背景图制作器组件（canvas 实时渲染）
2. 前端裁剪组件（cropperjs）
3. 前端文字叠加（canvas）
4. 集成到 image_workshop 工作台

**验收**：用户能制作背景图、裁剪上传的图片、叠加文字

### 第四期：多尺寸支持 + 去 AI 味道排版（2-3 天）

**目标**：支持多种图片尺寸 + 排版更自然

**范围**：
1. card_renderer 支持 1:1 / 3:4 / 4:3 多尺寸
2. 前端尺寸选择器
3. 新增排版变体（便签风/手写字/不对称布局）
4. 模板配色优化

**验收**：用户能选择不同尺寸，排版不再"一眼 AI"

---

## 九、风险与对策

### 9.1 LLM 规划质量不稳定

**风险**：LLM 可能选错模板类型，或填充的 template_data 质量差

**对策**：
- Prompt 设计清晰的类型判断规则（有步骤→flow，有清单→list，有时间→timeline）
- image_workshop 允许用户手动改模板类型（覆盖 LLM 规划）
- 模板数据支持用户手动编辑（不只是看 LLM 填充结果）

### 9.2 前端工作台复杂度高

**风险**：图片编排工作台功能多，前端开发量大

**对策**：
- 分期落地，第一期只做模板预览，第二期才做上传+工作台
- 工作台用 Tab 切换来源（模板/上传/背景图/AI），降低单页复杂度

### 9.3 图片数据传输大小

**风险**：多张 base64 图片通过 HTTP + SSE 传输，数据量大

**对策**：
- 上传接口用 multipart/form-data，不走 JSON
- image_workshop 确认时，图片数据通过 POST body 传输，不走 SSE
- SSE 只推送事件状态，不传图片数据

### 9.4 与现有审核机制兼容

**风险**：image_workshop 替代 image_review，需改动 submit_review 逻辑

**对策**：
- submit_review 增加可选参数 images_base64 / image_details
- 对 image_review（旧）的请求保持兼容（不带图片数据）
- 对 image_workshop（新）的请求带上图片数据

---

## 十、总结

本方案的核心转变：

| 维度 | 当前 | 新方案 |
|------|------|--------|
| 图片来源 | AI 生图单一 | 上传/背景图制作/AI生图/模板渲染 四来源 |
| 用户掌控 | 只能通过/打回 | 逐张选择来源 + 编辑 |
| 结构化内容 | 用文字卡片描述 | 预设模板（流程图/列表/时间线）精确表达 |
| 图片尺寸 | 固定 3:4 | 1:1 / 3:4 / 4:3 可选 |
| 排版 | 4 种固定模板 | 增加结构化模板 + 排版变体 + 手写风 |
| 节点架构 | image_gen 单节点 | image_plan + image_workshop 双节点 |

**第一期优先做结构化图表模板**（用户最痛的点），验证 LLM 规划 + 模板渲染的可行性，再逐步扩展到用户上传、背景图制作、多尺寸支持。

---

## 附录：关键文件清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `backend/app/services/card_renderer.py` | 扩展 | 新增 3 种结构化模板渲染 + 多尺寸支持 |
| `backend/app/agents/graph.py` | 重构 | 新增 image_plan / image_workshop 节点，调整路由 |
| `backend/app/services/workflow.py` | 扩展 | submit_review 支持图片数据 |
| `backend/app/api/routers/workflow.py` | 扩展 | 新增图片上传/模板渲染接口 |
| `backend/app/api/routers/review.py` | 扩展 | submit_review 接口增加图片数据字段 |
| `backend/app/db/models.py` | 扩展 | NodeType 枚举新增 image_plan / image_workshop |
| `frontend/src/views/WorkbenchView.vue` | 重构 | image_workshop 编排工作台 |
| `frontend/src/stores/workflow.ts` | 扩展 | 新增 ImageWorkshopState |
| `frontend/src/components/` | 新增 | 背景图制作器/裁剪/文字叠加组件 |
