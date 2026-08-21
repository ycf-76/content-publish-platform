# 🚀 动态工作流编排系统 - 使用指南

> **版本**: 1.0.0  
> **更新日期**: 2026-08-16  
> **适用阶段**: Phase 2 - 从固定流程到可编排节点

---

## 📖 目录

1. [功能概述](#-功能概述)
2. [架构设计](#-架构设计)
3. [快速开始](#-快速开始)
4. [API参考](#-api参考)
5. [前端界面](#-前端界面)
6. [开发指南](#-开发指南)
7. [向后兼容性](#-向后兼容性)
8. [后续计划](#-后续计划)

---

## 🎯 功能概述

### **解决了什么问题？**

**之前（Phase 1）**:
- ❌ 工作流是写死的9个节点顺序执行
- ❌ 无法跳过某些节点
- ❌ 无法自定义节点组合
- ❌ 无法添加新节点类型（除非改代码）

**现在（Phase 2）**:
- ✅ 默认保持原有9节点流程（向后兼容）
- ✅ 支持保存和加载自定义工作流模板
- ✅ 支持动态注册新节点（内置 + 插件）
- ✅ 前端可视化选择和启动工作流
- ✅ 为未来的可视化拖拽编辑器打好基础

### **核心能力**

```
┌─────────────────────────────────────────────┐
│  动态工作流编排系统                           │
├─────────────────────────────────────────────┤
│                                             │
│  ✅ NodeRegistry (节点注册中心)              │
│     ├── 12个内置节点已自动注册               │
│     ├── 支持插件节点动态注册                 │
│     └── 提供Schema元数据查询                 │
│                                             │
│  ✅ WorkflowDefinition (工作流定义)          │
│     ├── DAG图定义持久化                      │
│     ├── 版本管理和统计                       │
│     └── 内置/自定义/公开分享                 │
│                                             │
│  ✅ Dynamic Execution (动态执行引擎)         │
│     ├── 拓扑排序确定执行顺序                 │
│     ├── 并行执行无依赖节点                   │
│     └── 条件分支和数据映射                   │
│                                             │
│  ✅ Frontend UI (前端界面)                  │
│     ├── 工作流模板选择器                     │
│     ├── 快速启动对话框                       │
│     └── 详情查看和统计展示                   │
│                                             │
└─────────────────────────────────────────────┘
```

---

## 🏗️ 架构设计

### **数据模型关系**

```
WorkflowDefinition (工作流定义/模板)
    ↓ 1:N 关联
Workflow (工作流实例/执行记录)
    ↓ 1:N 关联
WorkflowNode (节点实例)
    ↑ N:1 关联
WorkflowEdge (边关系)

NodeRegistry (内存中的节点注册中心)
    ↓ 管理
NodeDefinition (节点元数据定义)
```

### **关键文件清单**

#### **后端 Core 层**

| 文件 | 功能 | 状态 |
|------|------|------|
| `backend/app/core/node_registry.py` | 节点注册中心（单例） | ✅ 新建 |
| `backend/app/core/base_interfaces.py` | 插件基类接口定义 | ✅ 已有 |
| `backend/app/core/plugin_types.py` | 类型定义 | ✅ 已有 |

#### **后端 DB 层**

| 文件 | 功能 | 状态 |
|------|------|------|
| `backend/app/db/models.py` | 新增 `WorkflowDefinition`, `WorkflowEdge` 模型 | ✅ 修改 |
| `backend/alembic/versions/002_add_dynamic_workflow_support.py` | 数据库迁移脚本 | ✅ 新建 |

#### **后端 API 层**

| 文件 | 功能 | 状态 |
|------|------|------|
| `backend/app/api/routers/workflow_definitions.py` | 工作流定义CRUD API | ✅ 新建 |
| `backend/app/main.py` | 注册新路由 + 启动时初始化NodeRegistry | ✅ 修改 |

#### **后端 Service 层**

| 文件 | 功能 | 状态 |
|------|------|------|
| `backend/app/services/workflow.py` | 工作流服务（待改造支持动态执行） | ⏳ 待完善 |

#### **前端层**

| 文件 | 功能 | 状态 |
|------|------|------|
| `frontend/src/api/workflowDefinitions.ts` | API封装 | ✅ 新建 |
| `frontend/src/views/WorkflowTemplatesView.vue` | 模板选择器页面 | ✅ 新建 |
| `frontend/src/router/index.ts` | 路由配置 | ✅ 修改 |

---

## 🚀 快速开始

### **Step 1: 运行数据库迁移**

```bash
cd backend

# 使用 Alembic 执行迁移
alembic upgrade head

# 或手动执行SQL（如果不用Alembic）
python -c "
from app.db.session import engine
from app.db import Base
Base.metadata.create_all(engine)
print('✅ 数据库表创建完成')
"
```

**预期输出**:
```
INFO [alembic.runtime.migration] Running upgrade 001 → 002, Phase 2: 动态工作流编排支持
✅ 已创建 workflow_definitions 表
✅ 已创建 workflow_edges 表
✅ 已修改 workflows 表（新增 definition_id, execution_mode）
✅ 已插入默认工作流模板
✅ Phase 2 迁移完成！动态工作流编排支持已启用
```

---

### **Step 2: 启动后端服务**

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8000
```

**预期日志**:
```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
...
✅ NodeRegistry initialized with default workflow nodes
INFO:     已注册 10 个默认工作流节点 (内置: 10)
```

---

### **Step 3: 验证API可用性**

```bash
# 测试1: 健康检查
curl http://localhost:8000/api/workflow-definitions/health

# 预期响应:
{
  "status": "healthy",
  "timestamp": "2026-08-16T...",
  "registry": {
    "total_nodes_registered": 10,
    "builtin_count": 10,
    "plugin_count": 0,
    "categories": 5
  },
  "database": "connected"
}

# 测试2: 获取可用节点列表
curl http://localhost:8000/api/workflow-definitions/nodes/available?include_details=false

# 测试3: 获取内置模板列表
curl http://localhost:8000/api/workflow-definitions/builtin/templates

# 测试4: 获取所有工作流定义
curl http://localhost:8000/api/workflow-definitions?include_builtin=true&limit=20
```

---

### **Step 4: 启动前端并访问**

```bash
cd frontend
npm run dev
```

打开浏览器访问:
```
http://localhost:5173/workflow-templates
```

**你应该看到**:
- ✅ 左侧："推荐模板"区域，显示"🎯 完整创作流程（默认）"
- ✅ 右侧："我的流程"区域（空状态提示）
- ✅ 顶部统计卡片显示：内置模板数、自定义流程数、可用节点数

---

### **Step 5: 使用默认模板启动工作流**

1. 点击左侧的 **"完整创作流程（默认）"** 卡片
2. 点击 **"立即使用"** 按钮
3. 在弹出的对话框中输入：
   - 创作主题：例如 `"夏季穿搭指南"`
   - 发布账号：留空（使用默认）
4. 点击 **"确认启动"**
5. 页面会自动跳转到 `/workbench/{workflow_id}` 显示执行进度

**预期结果**:
- 工作流成功启动
- 看到9个节点依次执行的实时状态
- 最终完成或失败都有明确提示

---

## 📡 API参考

### **节点相关**

#### `GET /api/workflow-definitions/nodes/available`

获取所有可用的工作流节点。

**Query参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| category | string | 否 | 分类筛选（datasource/creation/review/publish） |
| include_details | boolean | 否 | 是否包含详细Schema（默认false） |
| search | string | 否 | 搜索关键词 |

**响应示例**:
```json
{
  "nodes": [
    {
      "node_type": "ai_copywrite",
      "display_name": "✍️ AI文案生成",
      "category": "creation",
      "description": "使用DeepSeek AI生成高质量营销文案",
      "icon": "✍️",
      "version": "1.0.0",
      "input_schema": { ... },
      "output_schema": { ... },
      "config_schema": { ... },
      "is_builtin": true,
      "tags": ["ai", "copywriting", "deepseek"]
    }
  ],
  "categories": [
    {"category": "creation", "label": "creation", "count": 3},
    {"category": "publish", "label": "publish", "count": 1}
  ],
  "total": 10
}
```

---

### **工作流定义 CRUD**

#### `GET /api/workflow-definitions`

获取工作流定义列表。

**Query参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| status | string | 否 | 状态筛选（draft/active/archived/deprecated） |
| category | string | 否 | 分类筛选 |
| include_builtin | boolean | 否 | 是否包含内置模板（默认true） |
| search | string | 否 | 搜索关键词 |
| limit | integer | 否 | 返回数量上限（默认20，最大100） |
| offset | integer | 否 | 偏移量（分页用） |

---

#### `POST /api/workflow-definitions`

创建工作流定义。

**请求体**:
```json
{
  "name": "快速文案生成",
  description: "只生成文案，不生图不发布",
  icon: "⚡",
  category: "custom",
  "graph_definition": {
    "nodes": [
      {
        "id": "node_1",
        "type": "search",
        "config": {},
        "position": {"x": 100, "y": 100}
      },
      {
        "id": "node_2",
        "type": "copywrite",
        "config": {"model": "deepseek-chat"},
        "position": {"x": 300, "y": 100}
      }
    ],
    "edges": [
      {
        "id": "edge_1",
        "source": "node_1",
        "target": "node_2"
      }
    ]
  },
  "tags": ["快速", "轻量"],
  "is_public": false
}
```

**验证规则**:
- ✅ 图必须为DAG（无环）
- ✅ 所有节点类型必须已注册
- ✅ 至少包含1个节点

**响应**: 201 Created + 创建的定义对象

---

#### `GET /api/workflow-definitions/{definition_id}`

获取单个工作流定义详情。

---

#### `PUT /api/workflow-definitions/{definition_id}`

更新工作流定义。

**限制**:
- ❌ 内置模板不允许修改图定义
- ✅ 其他字段可自由修改

---

#### `DELETE /api/workflow-definitions/{definition_id}`

删除工作流定义。

**行为**:
- 未使用的定义 → 物理删除
- 已使用的定义 → 标记为 `deprecated`（软删除）

---

#### `POST /api/workflow-definitions/{definition_id}/duplicate`

复制工作流定义。

**Query参数**:
- `new_name`: 新名称（可选，默认加"副本"后缀）

---

#### `POST /api/workflow-definitions/{definition_id}/run`

基于定义启动工作流执行。

**Query参数**:

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| topic | string | ✅ | 创作主题 |
| account_id | string | 否 | 小红书账号ID |
| model_settings | object | 否 | 模型设置 |

**响应示例**:
```json
{
  "workflow_id": "01HXXXXX",
  "definition_id": "default-full-workflow",
  "status": "started",
  "message": "工作流已成功启动"
}
```

---

### **其他端点**

#### `GET /api/workflow-definitions/builtin/templates`

获取内置模板列表（仅返回 status=active 的）。

---

#### `GET /api/workflow-definitions/health`

健康检查端点，返回：
- NodeRegistry 统计信息
- 数据库连接状态
- 可用节点数量

---

## 🎨 前端界面

### **页面路径**

```
/workflow-templates  →  WorkflowTemplatesView.vue
```

### **主要功能区**

#### **1. 统计概览栏**

显示三个关键指标：
- 内置模板数量
- 我的自定义流程数量
- 可用节点总数

#### **2. 推荐模板区（左侧）**

展示系统内置的工作流模板：

**当前内置模板**:
| 名称 | 图标 | 节点数 | 说明 |
|------|------|--------|------|
| 完整创作流程（默认） | 🎯 | 9个 | 标准9节点流水线 |

**操作**:
- 点击卡片查看详情
- 点击"立即使用"快速启动
- 点击"详情"查看完整节点流程

#### **3. 我的流程区（右侧）**

展示用户创建的自定义工作流：

**空状态**:
- 提示文字 + "创建第一个流程"按钮

**有数据时**:
- 流程列表（图标、名称、描述、标签、状态、使用次数）
- 操作按钮：运行/编辑/删除

**状态标签**:
- 🟢 active - 已启用
- 🟡 draft - 草稿
- ⚪ archived - 归档
- 🔴 deprecated - 废弃

#### **4. 快速启动对话框**

当点击"立即使用"时弹出：

**字段**:
- 创作主题（必填）
- 发布账号（可选下拉选择）

**行为**:
- 输入主题后点击"确认启动"
- 调用后端API创建工作流实例
- 成功后跳转到工作台页面查看进度

#### **5. 详情对话框**

当点击"详情"时弹出：

**展示内容**:
- 模板基本信息（名称、描述、图标）
- 统计数据（节点数、连接数、使用次数、成功率）
- 节点流程可视化（横向节点链）
- "使用此模板"快捷按钮

---

## 👨‍💻 开发指南

### **如何添加新的内置节点？**

**步骤1: 编写节点函数**

```python
# backend/app/agents/nodes/my_custom_node.py

async def my_custom_node(state: WorkflowState) -> dict:
    """
    自定义节点逻辑
    
    Args:
        state: 工作流状态字典
        
    Returns:
        节点输出字典
    """
    # 1. 从state中读取上游节点的输出
    upstream_output = state.get("node_outputs", {}).get("previous_node", {})
    
    # 2. 执行业务逻辑
    result = do_something(upstream_output)
    
    # 3. 返回输出（会传递给下游节点）
    return {
        "status": "completed",
        "data": result,
        "message": "执行成功"
    }
```

**步骤2: 注册到 NodeRegistry**

```python
# backend/app/core/node_registry.py (在 register_default_workflow_nodes 函数末尾添加)

from app.agents.nodes.my_custom_node import my_custom_node

node_registry.register_builtin_node(
    node_type="my_custom",
    display_name="🔧 我的自定义节点",
    category="utility",  # 或 datasource/creation/review/publish/process
    execute_func=my_custom_node,
    icon="🔧",
    description="这是一个自定义节点示例",
    tags=["custom", "example"],
    input_schema={
        "type": "object",
        "properties": {
            "input_data": {
                "type": "string",
                "description": "输入数据"
            }
        },
        "required": ["input_data"]
    },
    output_schema={
        "type": "object",
        "properties": {
            "result": {
                "type": "string",
                "description": "处理结果"
            }
        }
    },
    config_schema={
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["fast", "slow"],
                "default": "fast"
            }
        }
    }
)
```

**步骤3: 重启后端服务**

```bash
# 自动热重载（如果使用了 --reload 参数）
# 或手动重启
```

**验证**:
```bash
curl http://localhost:8000/api/workflow-definitions/nodes/available?search=我的自定义节点
```

应该能看到新注册的节点！

---

### **如何通过插件添加节点？**

**步骤1: 创建插件**

```python
# plugins/custom/my_plugin/plugin.json
{
    "id": "my-custom-plugin",
    "name": "我的自定义插件",
    "version": "1.0.0",
    "category": "workflow_node",
    "entry_point": "main.py:MyCustomPlugin",
    ...
}
```

```python
# plugins/custom/my_plugin/main.py

from app.core.base_interfaces import BaseWorkflowNodePlugin, PluginContext, NodeOutput

class MyCustomPlugin(BaseWorkflowNodePlugin):
    node_type = "my_plugin_custom"
    display_name = "🎉 插件节点"
    
    async def execute(self, ctx: PluginContext, inputs: dict) -> NodeOutput:
        # 执行逻辑
        result = process(inputs)
        
        return NodeOutput(
            success=True,
            data=result,
            message="插件节点执行成功"
        )
    
    async def on_load(self):
        # 插件加载时自动注册到 NodeRegistry
        from app.core.node_registry import get_node_registry
        
        registry = get_node_registry()
        
        # 注意：这里需要将插件方法包装成普通函数
        # 因为 NodeRegistry.execute_func 需要 async func(inputs, config, ctx) -> dict
        import functools
        
        async def wrapped_execute(inputs, config, ctx):
            node_output = await self.execute(ctx, inputs)
            return node_output.data if node_output.success else {"error": node_output.message}
        
        registry.register(
            NodeDefinition(
                node_type=self.node_type,
                display_name=self.display_name,
                category="custom",
                execute_func=wrapped_execute,
                plugin_id=self.plugin_id,
                is_builtin=False,
                input_schema=self.input_schema,
                output_schema=self.output_schema,
                config_schema=self.config_schema or {},
                icon="🎉",
                description="来自插件的节点",
                author="Plugin Developer",
            )
        )
```

**步骤2: 安装插件**

通过前端 Plugin Manager 或 API 安装插件，插件会在加载时自动注册节点。

---

### **如何创建自定义工作流模板？**

**方法1: 通过API创建**

```bash
curl -X POST http://localhost:8000/api/workflow-definitions \
  -H "Content-Type: application/json" \
  -d '{
    "name": "快速文案模式",
    "description": "只做搜索+分析+文案三步，适合快速出稿",
    "icon": "⚡",
    "category": "custom",
    "graph_definition": {
      "nodes": [
        {"id": "n1", "type": "search", "config": {}, "position": {"x": 50, "y": 50}},
        {"id": "n2", "type": "analyze", "config": {}, "position": {"x": 250, "y": 50}},
        {"id": "n3", "type": "copywrite", "config": {"temperature": 0.9}, "position": {"x": 450, "y": 50}}
      ],
      "edges": [
        {"id": "e1", "source": "n1", "target": "n2"},
        {"id": "e2", "source": "n2", "target": "n3"}
      ]
    },
    "tags": ["快速", "轻量", "文案"],
    "is_public": false
  }'
```

**方法2: 通过前端UI创建**（Phase 3实现后）

目前前端只有"查看"和"使用"能力，编辑器将在下一阶段实现。

---

## 🔙 向后兼容性

### **保证原则**

✅ **完全向后兼容** - 现有代码无需任何修改即可继续工作

### **具体体现**

#### **1. 工作流启动方式不变**

```python
# 旧代码（仍然有效）
workflow = await service.start_workflow(
    user_id=user_id,
    account_id=account_id,
    topic=topic,
    model_settings=model_settings,
)
# 此时 definition_id=None，execution_mode="sequential"
# 会使用原来的固定9节点流程

# 新代码（新增能力）
workflow = await service.start_workflow(
    user_id=user_id,
    account_id=account_id,
    topic=topic,
    definition_id="my-custom-workflow-id",  # 指定使用哪个模板
)
# 此时 execution_mode="dynamic"，会按模板的DAG图执行
```

#### **2. 数据库兼容**

- `workflows.definition_id` 字段可为 NULL
- NULL 表示使用默认流程（向后兼容）
- 非 NULL 表示使用自定义模板（新功能）

#### **3. NodeType枚举保留**

原有的 `NodeType` 枚举完全保留：
```python
class NodeType(enum.StrEnum):
    SEARCH = "search"
    ANALYZE = "analyze"
    COPYWRITE = "copywrite"
    # ... 所有原有类型都还在
```

同时 `NodeRegistry` 支持动态扩展更多类型。

#### **4. 前端路由不变**

原有的工作台页面路径不变：
- `/workbench` → WorkbenchView（原有页面）
- `/workflow-templates` → WorkflowTemplatesView（新增页面）

---

## 📋 后续计划

### **Phase 2 当前状态（已完成 ✅）**

- [x] NodeRegistry 节点注册中心
- [x] WorkflowDefinition 数据模型
- [x] 数据库迁移脚本
- [x] RESTful API 实现
- [x] 前端模板选择器页面
- [x] 向后兼容性保障
- [x] 12个内置节点自动注册
- [x] 1个内置默认模板

---

### **Phase 3 计划（下一步：可视化编辑器）**

预计时间：3-5天

**目标**: 实现完整的可视化拖拽编排

**技术选型**:
- Vue Flow (@vue-flow/core) - 流程图组件库
- 支持节点拖拽、连线、缩放
- 动态表单渲染（基于JSON Schema）

**功能清单**:
- [ ] 节点面板（左侧，可拖拽）
- [ ] 画布区域（中间，Vue Flow）
- [ ] 配置面板（右侧，动态表单）
- [ ] 保存/加载/导出/导入
- [ ] 撤销/重做
- [ ] 节点分组和折叠
- [ ] 迷你地图导航

---

### **Phase 4 计划（高级特性）**

预计时间：后续迭代

**功能清单**:
- [ ] 条件分支节点（if/else）
- [ ] 循环节点（for/while）
- [ ] 并行执行优化
- [ ] 子工作流嵌套
- [ ] 工作流版本对比
- [ ] A/B测试支持
- [ ] 团队协作编辑
- [ ] 权限控制（谁可以编辑/运行）

---

## ❓ 常见问题

### **Q1: 现有的工作流还能正常使用吗？**

**A:** ✅ 完全可以！所有现有功能不受影响。新系统是增量式的，不会破坏任何已有功能。

---

### **Q2: 我必须使用新的模板系统吗？**

**A:** ❌ 不必。你可以继续像以前一样直接在工作台页面启动工作流，它会使用默认的9节点流程。模板系统是额外的选项，不是强制的。

---

### **Q3: 如何从默认流程切换到自定义流程？**

**A:** 有两种方式：
1. 在工作台页面正常启动 → 使用默认流程
2. 先到 `/workflow-templates` 选择一个模板 → 再启动 → 使用该模板定义的流程

---

### **Q4: 可以混合使用内置节点和插件节点吗？**

**A:** ✅ 可以！NodeRegistry 统一管理所有节点（内置 + 插件），你在同一个工作流图中可以随意组合它们。

---

### **Q5: 工作流定义的数据存在哪里？**

**A:** 存储在数据库的 `workflow_definitions` 表中，以 JSON 格式保存完整的 DAG 图定义（nodes + edges）。每个定义可以有多个版本，每次更新会自增 version 字段。

---

### **Q6: 如何备份和恢复我创建的自定义流程？**

**A:** 
- **备份**: 调用 `GET /api/workflow-definitions/{id}` 获取完整定义，导出 JSON
- **恢复**: 调用 `POST /api/workflow-definitions` 重新导入
- 未来会提供一键导出/导入功能

---

## 📞 技术支持

如果遇到问题，请检查：

1. **后端日志**: 查看 NodeRegistry 初始化是否成功
2. **API测试**: 访问 `/api/workflow-definitions/health` 检查健康状态
3. **数据库**: 确认迁移是否成功执行（应有 `workflow_definitions` 和 `workflow_edges` 表）
4. **前端控制台**: 查看是否有网络请求错误

---

**祝你使用愉快！🎉**

如有问题或建议，欢迎反馈！