# 图片审核节点"打回重来"卡死问题 — 诊断与修复方案

## 问题现象

在 image_review 节点点击"打回重来"后，前端卡死，不返回任何信息。

## 诊断过程

### 1. LangGraph update_state + resume 机制验证（通过）

写了最小测试用例验证 `graph.update_state(config, {"node_statuses": {node: "rejected"}})` + `astream(None, config)` 的行为：

```
STEP 1: run to interrupt → next = ('b',)
STEP 2: update_state WITHOUT as_node → next 保持 ('b',) 不变
STEP 3: resume → node_b 读到 rejected → route 返回 "a" → node_a 重跑 → 再次 interrupt
```

**结论**：LangGraph 的 update_state + resume 机制本身是正确的，不改变 next 指针，reject 回退路径能正常工作。

### 2. API 路由验证（通过）

前端调 `POST /api/workflows/{id}/reviews/{review_id}` → 后端 `process_review_legacy` → `service.submit_review(workflow_id, action, user_id)` → reject 分支。

路由链路正确，参数传递正确。

### 3. 代码审查发现 4 个 Bug

#### Bug 1（根因）：`_resume_graph_stream` 不推送 `node_started` / `node_completed` 事件

**文件**：`backend/app/services/workflow.py` 行 755-772

`_resume_graph_stream` 的 astream 循环只推送 `workflow_snapshot` 事件（包含 `node_statuses` 和 `node_outputs_keys`），**不推送** `node_started` / `node_completed` 事件。

而首次执行（`_execute_graph_safely`）会推送 `node_started` / `node_completed` 事件，前端依赖这些事件来：
- 显示节点运行状态（loading 动画）
- 更新节点输出（特别是 `images_base64` 图片数据）

reject 回退后，image_gen_node 重新执行（Playwright 渲染需要 5-30 秒）。在这期间：
- 前端收不到 `node_started` → image_gen 卡片不显示 loading
- 前端收不到 `node_completed` → image_gen 卡片不更新图片
- 前端收不到 `node_completed` → image_review 审核界面不显示新图片

**用户感知**：点击 reject 后，5-30 秒内 UI 完全无变化，像"卡死"。

#### Bug 2（加重因素）：前端 reject 后无 loading/进度反馈

**文件**：`frontend/src/views/WorkbenchView.vue` 行 1851-1859

```typescript
async function submitNodeReview(nodeKey: string, action: 'pass' | 'reject') {
  const node = workflowStore.nodes.find(...)
  if (!node || !workflowStore.currentWorkflow) return
  try {
    await workflowStore.submitReview(node.node_id || nodeKey, action)
    // 没有设置 loading 状态，没有显示"正在回退..."提示
  } catch (e) {
    console.error('提交审核失败:', e)
    // 没有给用户任何 UI 反馈
  }
}
```

用户点击 reject 按钮后：
- 按钮不 disable，可以重复点击
- 没有 loading 动画
- 没有"正在回退，重新生成图片..."提示
- API 失败只 console.error，用户看不到

#### Bug 3（潜在风险）：`asyncio.create_task` 没保存引用

**文件**：`backend/app/services/workflow.py` 行 654-656

```python
asyncio.create_task(
    self._resume_graph_safely(workflow_id, graph, config)
)
```

Python 官方文档明确警告：
> Important: Save a reference to the result of this function, to avoid a task disappearing mid-execution.

task 没有被保存引用，可能被 GC 回收，导致 resume 根本不执行。pass 分支（行 694）也有同样问题。

#### Bug 4（潜在风险）：`graph.update_state` 没 try-catch

**文件**：`backend/app/services/workflow.py` 行 640-643

```python
graph.update_state(
    config,
    {"node_statuses": {review_node: NodeStatus.REJECTED.value}},
)
```

`update_state` 在 try-catch 块之外。如果抛异常（虽然概率低），submit_review 方法会抛异常，FastAPI 返回 500，前端 catch 后只 console.error。

## 修复方案

### 修复 1：`_resume_graph_stream` 推送 node 事件（Bug 1）

在 astream 循环中，对每个 chunk 推送 `node_started`（节点开始）和 `node_completed`（节点完成，含完整输出）事件，和 `_execute_graph_safely` 保持一致。

**改动文件**：`backend/app/services/workflow.py`
**改动位置**：`_resume_graph_stream` 方法，行 755-772

### 修复 2：前端 reject 加 loading + 错误提示（Bug 2）

- reject 按钮点击后 disable + 显示 loading
- 显示"正在回退，重新生成..."提示
- API 失败时显示 toast/alert

**改动文件**：`frontend/src/views/WorkbenchView.vue`
**改动位置**：`submitNodeReview` 函数 + image_review / final_review 卡片模板

### 修复 3：保存 task 引用（Bug 3）

在 WorkflowService 类中加 `_background_tasks: set` 属性，保存 task 引用，task 完成后自动移除。

**改动文件**：`backend/app/services/workflow.py`

### 修复 4：update_state 加 try-catch（Bug 4）

`graph.update_state` 包进 try-catch，异常时返回错误响应。

**改动文件**：`backend/app/services/workflow.py`

## 为什么这样改

1. **Bug 1 是根因**：reject 回退后 image_gen 重跑期间，前端完全收不到事件，感知为"卡死"。推送 node 事件后，前端能看到 image_gen 正在重跑，等待变得可预期。
2. **Bug 2 是体验问题**：即使后端正确推送事件，前端也需要在点击 reject 后给用户即时反馈，避免"我点了但没反应"的感觉。
3. **Bug 3/4 是防御性修复**：虽然目前不一定触发，但属于代码缺陷，趁此次修复一并处理。
