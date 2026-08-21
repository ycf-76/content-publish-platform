# 插件节点适配层设计文档

## 1. 问题

三个核心问题：

**问题 A：签名断裂（后端）**
LangGraph 调用节点函数时只传 `state: WorkflowState`。
内置节点签名 `async def node(state: WorkflowState) -> dict`，兼容。
插件节点签名 `async def execute(inputs, node_config, ctx) -> dict`，不兼容。
当前代码直接把插件函数塞进 LangGraph 节点映射，运行时 TypeError。

**问题 B：Token 预算失控（后端）**
内置节点通过 `get_deepseek_llm()` 统一获取 LLM 实例，`max_tokens` 默认 1500。
插件没有受控的 LLM 入口，可以直接 `import openai` 无限制调用，
单次调用可以消耗数万 token，成本不可控。

**问题 C：前端看不到插件（前端）**
- 设置面板安装了 `workflow_node` 类型插件，但工作流不知道
- 动态编排编辑器 fallback 硬编码 9 个内置节点，插件节点不显示
- 右侧面板 Skill 选择也硬编码了 4 个默认 Skill
- 用户无法区分内置节点和插件节点

## 2. 目标

1. 插件节点能正确替换内置节点在 LangGraph 图中运行
2. 插件调 LLM 必须走统一入口，受 max_tokens 预算约束
3. 动态编排图中插件节点也能正确获取上游数据
4. 前端能看到已安装的插件节点，能区分内置和插件

## 3. 修改范围

| 文件 | 改什么 |
|------|--------|
| `backend/app/agents/graph.py` | 新增适配器函数，修改 `_get_node_func_map()` |
| `backend/app/core/plugin_types.py` | 给 PluginContext 加 `llm` 字段 |
| `frontend/src/components/workflow/WorkflowEditor.vue` | 插件节点显示标识 |
| `frontend/src/components/workbench/RightPanel.vue` | 插件 Skill 显示标识 |

## 4. 后端修改

### 4.1 改 `plugin_types.py`：PluginContext 加 LLM 入口

当前（第 64-85 行）：
```python
@dataclass
class PluginContext:
    plugin_id: str
    plugin_dir: str
    config: Dict[str, Any]
    logger: Any
    user_id: Optional[str] = None
    api: Any = None
```

改为：
```python
@dataclass
class PluginContext:
    plugin_id: str
    plugin_dir: str
    config: Dict[str, Any]
    logger: Any
    user_id: Optional[str] = None
    api: Any = None
    llm: Any = None  # 受控 LLM 实例（BaseLLM），由适配层注入
```

插件通过 `ctx.llm.chat(messages)` 调 LLM，而不是自己 import openai。

注意：`plugin_manager.py:273` 构造 PluginContext 时不传 `llm`（初始化阶段不需要 LLM），
`llm` 默认为 `None`。适配器在执行阶段构造新 PluginContext 时才注入 `llm`。

### 4.2 改 `graph.py`：新增 `_make_plugin_adapter()`

位置：`_get_node_func_map()` 函数之前（约第 288 行）

签名：
```python
def _make_plugin_adapter(
    plugin_raw_func: Callable,
    node_type: str,
    plugin_id: str,
) -> Callable:
```

**关键：`node_type` 和 `plugin_id` 必须作为参数传入，不能从闭包捕获。**
因为 `_get_node_func_map()` 在循环中调用，闭包捕获会导致所有适配器
引用循环结束后的最后一个值。

返回值：`async def (state: WorkflowState) -> dict`

包装函数逻辑：

**A. 从 WorkflowState 提取三个参数**

| 插件参数 | 取值方式 | 说明 |
|---------|---------|------|
| `inputs` | `dict(state.get("node_outputs", {}))` | 全部上游输出，不硬编码映射表 |
| `config` | `state.get("model_settings", {})` | 用户配置 |
| `ctx` | 构造 PluginContext | 含受控 LLM 实例 |

**B. 上游数据获取：传全部 node_outputs**

不硬编码映射表，原因：
- 固定工作流：copywrite 从 inputs 取 `inputs["analyze"]`，和内置节点取 `state["node_outputs"]["analyze"]` 结构一致
- 动态编排图：上游是谁运行时才知道，硬编码表用不上
- 数据量可控：每个节点输出 1-5KB，9 个节点全给也就 10-50KB

**C. 注入受控 LLM 实例**

```python
from app.agents.harnesses.factory import get_deepseek_llm

temperature = state.get("model_settings", {}).get("temperature")
model = state.get("model_settings", {}).get("text_model")
llm = get_deepseek_llm(temperature=temperature, model=model)
```

`get_deepseek_llm()` 返回的 DeepSeekAdapter 默认 `max_tokens=1500`，
插件通过 `ctx.llm.chat(messages)` 调用时自动受此限制。

LLM 不可用时 `llm=None`，插件需要自行处理（降级或报错），
与内置节点行为一致（内置节点也是 `llm=None` 时走降级）。

**D. 包装返回值**

插件返回纯业务数据 → 自动包装成 LangGraph 的 partial state update：

```python
{
    "current_node": node_type,
    "node_statuses": {node_type: "completed"},
    "node_outputs": {node_type: result},
}
```

### 4.3 改 `graph.py`：修改 `_get_node_func_map()`

改动位置：第 325-335 行

改动前：
```python
if node_def.execute_func and node_def.plugin_id:
    is_override = node_type in _NODE_FUNC_MAP
    _NODE_FUNC_MAP[node_type] = node_def.execute_func
    plugin_nodes_count += 1
```

改动后：
```python
if node_def.execute_func and node_def.plugin_id:
    is_override = node_type in _NODE_FUNC_MAP
    adapter = _make_plugin_adapter(node_def.execute_func, node_type, node_def.plugin_id)
    _NODE_FUNC_MAP[node_type] = adapter
    plugin_nodes_count += 1
```

### 4.4 错误处理

适配器 catch 插件异常，返回与内置节点一致的 error 格式：

```python
{
    "current_node": node_type,
    "node_statuses": {node_type: "error"},
    "node_outputs": {node_type: {"_error": str(e)}},
    "node_errors": {node_type: {"error": str(e), "type": type(e).__name__}},
}
```

同时推送 SSE 事件（node_error），前端卡片能显示错误状态。

### 4.5 事件推送

适配器在插件执行前后推送 SSE 事件，与内置节点行为一致：

- 执行前：`node_started` + `node_status_changed(running)`
- 成功后：`node_status_changed(completed)` + `node_completed`
- 失败后：`node_status_changed(error)` + `node_error`

使用 `emit_node_event(workflow_id, node_type, event_type, payload)`，
从 `state["workflow_id"]` 取 workflow_id。

### 4.6 Token 预算约束机制

| 层级 | 机制 | 效果 |
|------|------|------|
| LLM 实例 | `get_deepseek_llm()` 默认 `max_tokens=1500` | 单次调用输出上限 1500 token |
| 适配器 | `ctx.llm` 注入受控实例 | 插件通过 ctx.llm 调 LLM 自动受限 |
| 并发控制 | `BaseLLM` 内置信号量（`LLM_CONCURRENCY_LIMIT`） | 防止插件并发调 LLM 过载 |
| 文档约束 | 插件开发规范写明"禁止直接 import openai" | 软约束，配合代码审查 |

插件如果绕过 `ctx.llm` 直接调 openai，当前无法硬拦截。
但 `max_tokens=1500` 已经覆盖了正常使用场景（内置节点单次调用也在这个量级）。
后续如需硬拦截，可在插件沙箱中禁用 openai 包。

## 5. 前端修改

### 5.1 改 `WorkflowEditor.vue`：插件节点显示标识

当前 `loadAvailableNodes()` 已经从后端 `list_available_nodes` API 获取节点列表，
后端 NodeRegistry 已包含插件节点。但前端没有区分显示。

改动：

**A. 节点卡片加"插件"角标**

后端 `NodeDefinition` 已有 `plugin_id` 字段。
API 返回的节点数据中 `plugin_id` 非空的就是插件节点。

在节点卡片模板中加角标：
```html
<span v-if="node.plugin_id" class="plugin-badge">插件</span>
```

**B. 加角标样式**

```css
.plugin-badge {
  position: absolute;
  top: 4px;
  right: 4px;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 4px;
  background: #8B5CF6;
  color: white;
  font-weight: 500;
}
```

**C. 删除 fallback 硬编码节点**

当后端 API 可用时，不再 fallback 到硬编码的 9 个节点。
只在 API 不可用时才用 fallback。

当前代码已经是这个逻辑（第 625-668 行），不需要改。

### 5.2 改 `RightPanel.vue`：插件 Skill 显示标识

当前 `loadSkills()` 已从后端 `listSkills` API 获取 Skill 列表，
后端 SkillRegistry 已包含第三方 Skill。但前端没有区分显示。

改动：在 Skill 选项旁加"插件"标签

```html
<span v-if="skill.is_third_party" class="skill-plugin-tag">插件</span>
```

需要后端 `listSkills` API 返回时加 `is_third_party` 字段（见 5.3）。

### 5.3 后端 `listSkills` API 加 `is_third_party` 字段

当前后端 SkillRegistry 的 `list_skills()` 方法返回 Skill 元数据。
需要加一个字段标识是否为第三方注册的 Skill。

改动位置：`backend/app/agents/skills/registry.py` 的 `list_skills()` 方法

在返回的 Skill 信息中加：
```python
"is_third_party": skill_cls.__module__.startswith("skills.")  # skills/ 目录下的都是第三方
```

## 6. 不改的部分

- 内置节点代码：不动
- NodeRegistry：不动
- PluginNodeBridge：不动（PluginContext 在适配器里构造，不在 bridge 里）
- PluginManager：不动（初始化时 PluginContext 不需要 llm）
- SkillRegistry 核心逻辑：不动

## 7. 插件开发者须知

插件 `execute()` 中调 LLM 的方式：

```python
class MyCopywritePlugin(BaseWorkflowNodePlugin):
    node_type = "copywrite"
    display_name = "我的文案插件"

    async def execute(self, inputs, node_config, ctx):
        # ✅ 正确：通过 ctx.llm 调用，受 max_tokens=1500 限制
        if ctx.llm is None:
            return {"title": "降级标题", "content": "LLM 不可用", "tags": []}

        result = await ctx.llm.chat(messages=[
            {"role": "user", "content": f"写一篇关于{inputs.get('analyze', {})}的文案"}
        ])
        return {"title": result["content"], "content": "...", "tags": []}

        # ❌ 错误：直接调 openai，绕过 token 预算控制
        # import openai
        # client = openai.AsyncOpenAI()
        # resp = await client.chat.completions.create(
        #     model="gpt-4", messages=[...], max_tokens=8000  # 失控！
        # )
```

注意：`setup()` 阶段的 `self._ctx.llm` 为 `None`（初始化时不需要 LLM），
只在 `execute()` 的 `ctx` 参数中才有 LLM 实例。

## 8. 验证方法

1. 安装一个 copywrite 类型的插件节点
2. 启动工作流，执行到 copywrite 节点
3. 确认：插件函数被正确调用，前端卡片显示插件输出，无 TypeError
4. 确认：插件通过 ctx.llm 调 LLM 时，max_tokens 受 1500 限制
5. 确认：内置节点（未安装插件时）行为不变
6. 在动态编排图中使用插件节点，确认上游数据正确传入
7. 确认：LLM 不可用时插件走降级逻辑，不崩溃
8. 打开动态编排编辑器，确认插件节点显示"插件"角标
9. 打开右侧面板，确认插件 Skill 显示"插件"标签