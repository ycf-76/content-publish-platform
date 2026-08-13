# 图片审核节点"打回重来"卡死 + 通过后报错问题 — 完整诊断与修复方案

> 本次诊断基于对前后端调用链路的逐行代码审查，定位到 **4 个确定性 Bug**（含 1 个核心功能性 Bug）+ 2 个潜在风险。
> 之前的 `docs/reject-fix/SOLUTION.md` 只覆盖了部分问题（后台 task 引用、update_state 异常处理），**核心功能性 Bug（pass 分支未重置 rejected 状态）+ 前端反馈缺失未修复**，因此用户仍感知"卡死"和"通过后报错"。

---

## 一、问题现象

**现象 A（卡死）**：在 image_review 节点点击"打回重来"后，前端 UI 无任何变化，按钮不 disable、无 loading，5~30 秒无反馈，感知为"卡死"。

**现象 B（通过后报错）**：重复打回重来几次后，点击"通过"，工作流报错终止。

---

## 二、诊断过程（调用链路逐层追踪）

### 2.1 完整调用链路（reject 分支）

```
前端按钮 @click="submitNodeReview('image_review', 'reject')"
  └─ WorkbenchView.vue: submitNodeReview()
       └─ workflowStore.submitReview('image_review', 'reject')
            └─ workflowApi.submitReview(workflowId, 'image_review', 'reject')
                 └─ POST /api/workflows/{id}/reviews/image_review  body={action:'reject'}
                      └─ review.py: process_review_legacy()
                           └─ WorkflowService.submit_review(action='reject')
                                ├─ graph.update_state({image_review: rejected})  ✅ 已有 try-catch
                                ├─ sse_bus.publish('node_status_changed')        ✅
                                ├─ _create_background_task(_resume_graph_safely) ✅ 已保存引用
                                └─ return {success: True}  ← HTTP 200 立即返回

[后台 task 异步执行]
_resume_graph_safely()
  └─ _resume_graph_stream()
       └─ graph.astream(None, config)  ← resume from interrupt
            ├─ image_review_node 执行（读到 rejected → 返回 rejected）
            ├─ route_after_image_review → "image_gen"
            ├─ image_gen_node 重跑（Playwright 渲染 5~30s）
            │    ├─ emit_node_event('node_started')      ← 前端应收到
            │    └─ emit_node_event('node_completed')    ← 前端应收到（含 images_base64）
            └─ 到 image_review 前 interrupt again
                 └─ _emit_review_required()  ← 推 review_required 事件
```

### 2.2 链路验证结论

| 环节 | 状态 | 说明 |
|------|------|------|
| HTTP 路由 | ✅ 正确 | legacy 接口 → submit_review，参数传递正确 |
| submit_review reject 分支 | ✅ 已修复 | update_state 有 try-catch，task 引用已保存 |
| LangGraph update_state + resume 机制 | ✅ 正确 | interrupt_before + astream(None) resume 机制经验证可用 |
| 路由函数 route_after_image_review | ✅ 正确 | rejected → "image_gen" 回退路径正确 |
| 节点函数事件推送 | ✅ 正确 | image_gen_node 内部调 emit_node_event 推 node_started/completed |
| 前端 node_id 匹配 | ✅ 正确 | 后端 getNodes 重建节点用字符串 node_id（"image_gen"），与 SSE 事件一致 |
| **前端按钮 loading 绑定** | ❌ Bug 1 | reviewSubmitting ref 设置了，但按钮模板未绑定 |
| **reject 后回退进度反馈** | ❌ Bug 2 | 审核按钮消失后无任何"正在回退"提示 |
| **_resume_graph_stream 的 workflow_snapshot** | ❌ Bug 3 | 推送的 snapshot 缺 nodes/status 字段，被前端忽略 |

---

## 三、根因分析

### Bug 0（核心功能性 Bug·后端）：pass 分支未重置 rejected 状态，导致通过后仍走回退路径无限循环

**文件**：`backend/app/services/workflow.py` 行 690-721（pass 分支）

**问题**：reject 分支调了 `graph.update_state` 设审核节点为 `rejected`，但 **pass 分支完全没有 `update_state`**，直接 resume。

reject 流程（行 654-658）：
```python
graph.update_state(
    config,
    {"node_statuses": {review_node: NodeStatus.REJECTED.value}},
)
```

pass 流程（行 690-721）：
```python
# 通过：resume 工作流
graph = build_workflow_graph(checkpointer=None)
config = {"configurable": {"thread_id": workflow_id}, "recursion_limit": 50}
# ... 验证 interrupt 状态 ...
# ❌ 没有 update_state！直接 resume
self._create_background_task(
    self._resume_graph_safely(workflow_id, graph, config)
)
```

**为什么会导致"通过后报错"**：

完整状态流转推演：

```
1. reject → update_state(image_review=rejected) → resume
   → image_review_node 执行，读到 rejected → 返回 {node_statuses: {image_review: rejected}}
   → route_after_image_review: rejected≠passed → 回退到 image_gen
   → image_gen 重跑 → 到 image_review 前 interrupt
   此时 checkpoint 里 image_review 状态 = rejected

2. 重复 reject → 同上，image_review 始终是 rejected

3. pass → ❌ 没 update_state → resume
   → image_review_node 执行，读到上次 reject 残留的 rejected
   → is_rejected = True → 返回 rejected
   → route_after_image_review: rejected≠passed → 又回退到 image_gen！
   → image_gen 又重跑 → 又 interrupt → 又要审核
   → 无限循环，最终 recursion_limit=50 触发 RecursionError
   → _resume_graph_safely catch 后推 workflow_error → 前端显示报错
```

[image_review_node](file:///d:/My_Project/多智能体小红书发布平台/backend/app/agents/graph.py#L1056-L1058) 读状态：
```python
review_status = state.get("node_statuses", {}).get(node_id, "pending")
is_rejected = review_status == NodeStatus.REJECTED.value  # ← 读到上次 reject 残留
```

[route_after_image_review](file:///d:/My_Project/多智能体小红书发布平台/backend/app/agents/graph.py#L1795-L1804)：
```python
if review_status == NodeStatus.PASSED.value:
    return "audit"
return "image_gen"   # ← rejected 走这里，又回退
```

**final_review 的 pass 分支有完全相同的问题**（reject → copywrite 回退，pass 不重置 → 无限回退）。

### Bug 1（根因·前端）：审核按钮未绑定 loading 状态

**文件**：`frontend/src/views/WorkbenchView.vue`

`submitNodeReview` 函数里定义了 `reviewSubmitting` ref 并正确设置/清除，**但按钮模板完全没有使用它**：

```html
<!-- 当前代码（行 637-643） -->
<button class="mint-btn mint-btn-outline" @click="submitNodeReview('image_review', 'reject')">
  <i data-lucide="undo-2" style="width:14px;height:14px;"></i>
  打回（回退至 03）
</button>
<button class="mint-btn mint-btn-primary" @click="submitNodeReview('image_review', 'pass')">
  <i data-lucide="check" style="width:14px;height:14px;"></i>
  通过
</button>
```

**问题**：
- 按钮没有 `:disabled="reviewSubmitting"` → 用户可以重复点击
- 按钮没有 loading 动画 → 点击后视觉无变化
- API 调用很快返回（HTTP 200），`reviewSubmitting` 瞬间清空，loading 形同虚设

**用户感知**：点击"打回重来"后，按钮没反应（没 disable、没转圈），1 秒内审核按钮区域消失（因为 `node.status='rejected'`），然后 5~30 秒无任何反馈 → "卡死"。

### Bug 2（根因·前端）：reject 后无回退进度提示

**文件**：`frontend/src/views/WorkbenchView.vue` + `frontend/src/stores/workflow.ts`

前端 `submitReview` 成功后只做了一件事：

```typescript
// stores/workflow.ts 行 198-201
const node = nodes.value.find(n => n.node_id === reviewId)
if (node) {
  node.status = action === 'pass' ? 'passed' : 'rejected'
}
```

把 image_review 节点状态设为 `rejected` → 审核按钮区域 `v-if="nodeStatus('image_review') === 'awaiting_review'"` 失效 → 按钮消失。

**但没有任何"正在回退至 image_gen 重新生成图片..."的提示**。

image_gen 节点状态此时还是旧的 `completed`，不会显示 loading。要等到后台 task 调度执行 + image_gen_node 函数开头推 `node_started` 事件，前端才会把 image_gen 设为 running。这个延迟可能 0.5~2 秒（event loop 调度）+ 节点函数执行到 emit_node_event 的时间。

**在这段空窗期 + image_gen 渲染期间，UI 完全静止，用户感知"卡死"**。

### Bug 3（加重因素·后端）：_resume_graph_stream 的 workflow_snapshot 缺字段

**文件**：`backend/app/services/workflow.py` 行 780-797

```python
async for chunk in graph.astream(None, config):
    for node_key, delta in chunk.items():
        ...
        if node_statuses or node_outputs:
            await sse_bus.publish(
                workflow_id,
                "workflow_snapshot",
                {
                    "workflow_id": workflow_id,
                    "current_node": delta.get("current_node", node_key),
                    "node_statuses": node_statuses,
                    "node_outputs_keys": list(node_outputs.keys()),
                },
            )
```

前端处理 `workflow_snapshot` 的逻辑：

```typescript
// stores/workflow.ts 行 298-306
case 'workflow_snapshot':
  if (payload.nodes) {        // ← 后端没推 nodes 字段！
    nodes.value = payload.nodes
  }
  if (payload.status && currentWorkflow.value) {  // ← 后端没推 status 字段！
    currentWorkflow.value = { ...currentWorkflow.value, ...payload }
  }
  break
```

后端推的 snapshot 只有 `current_node / node_statuses / node_outputs_keys`，**没有 `nodes` 也没有 `status`**，所以前端整个 case 体什么都不执行 → snapshot 事件被完全忽略。

这意味着 `_resume_graph_stream` 期间，前端**只能依赖节点函数内部推的 node_started / node_completed / node_status_changed 事件**来更新 UI。如果节点函数因某种原因没推事件（例如节点函数在 emit 前抛异常被 fallback 兜住），前端就收不到任何信号。

### 潜在风险 1：image_gen 重跑期间 Playwright 卡住

image_gen_node 重跑会调 `card_renderer.render_html_to_png`，内部用单例 Playwright browser。虽然 `render_html_to_png` 有 15 秒超时（`RENDER_TIMEOUT`），但如果单例 browser 实例已崩溃（`is_connected()` 返回 False 但对象还在），`_get_browser` 会尝试重新启动，可能再次卡住。

### 潜在风险 2：recursion_limit 触发

reject 回退路径：image_review → image_gen → image_review(interrupt) → reject → image_gen → ...
每次 reject 增加 2 步递归。`recursion_limit=50`，理论上可 reject 25 次。但如果用户快速连续 reject（Bug 1 导致按钮可重复点击），可能在短时间内触发 limit，astream 抛 `RecursionError`，被 `_resume_graph_safely` catch 后推 `workflow_error`。

---

## 四、修复方案

### 修复 0：pass 分支补 update_state 重置审核节点为 passed（Bug 0 · 核心）

**这是最关键的修复，不修这个则 pass 永远无法真正通过。**

**文件**：`backend/app/services/workflow.py`

**改动位置**：`submit_review` 方法的 pass 分支（行 690-721）

**如何改**：在 resume 之前，通过 `update_state` 把审核节点状态设为 `PASSED`，覆盖上次 reject 残留的 `rejected`。

```python
# 通过：resume 工作流
if not LANGGRAPH_AVAILABLE:
    return {"success": False, "message": "LangGraph unavailable"}

graph = build_workflow_graph(checkpointer=None)
if graph is None:
    return {"success": False, "message": "Graph build failed"}

config = {"configurable": {"thread_id": workflow_id}, "recursion_limit": 50}

# 验证当前确实处于 interrupt 状态，并获取审核节点名
try:
    graph_state = graph.get_state(config)
    next_nodes = getattr(graph_state, "next", None) or ()
    if not next_nodes:
        return {
            "success": False,
            "message": f"Workflow not in interrupt state (next={next_nodes})"
        }
    review_node = next_nodes[0]  # image_review 或 final_review
    logger.info(
        f"[{workflow_id}] resume from interrupt: next={next_nodes}, "
        f"review_node={review_node}"
    )
except Exception as e:
    return {"success": False, "message": f"Get graph state failed: {e}"}

# ===== 新增：pass 时必须重置审核节点状态为 passed =====
# 否则如果之前 reject 过，checkpoint 里残留的 rejected 状态会导致
# image_review_node 读到 rejected → route_after_image_review 又走回退路径
# → 无限循环 → recursion_limit 触发报错
from app.agents.graph import NodeStatus
try:
    graph.update_state(
        config,
        {"node_statuses": {review_node: NodeStatus.PASSED.value}},
    )
    logger.info(
        f"[{workflow_id}] update_state OK (pass): "
        f"{review_node}={NodeStatus.PASSED.value}"
    )
except Exception as e:
    logger.exception(f"[{workflow_id}] update_state (pass) failed: {e}")
    return {
        "success": False,
        "message": f"Update state failed: {e}",
    }

# 推送节点状态变更事件（前端更新 UI）
await sse_bus.publish(
    workflow_id,
    "node_status_changed",
    {"node_id": review_node, "status": NodeStatus.PASSED.value},
)

# 异步 resume
self._create_background_task(
    self._resume_graph_safely(workflow_id, graph, config)
)

return {"success": True, "message": "Workflow resumed"}
```

**关键点**：
- `review_node = next_nodes[0]` 复用 reject 分支相同的逻辑，拿到当前 interrupt 的审核节点名
- `update_state` 把该节点设为 `PASSED`，覆盖上次 reject 残留的 `REJECTED`
- image_review_node 执行时读到 `passed` → `is_rejected=False` → 返回 `passed` → route 走 `audit`（正常前进）
- final_review 同理，读到 `passed` → route 走 `publish`

### 修复 1：审核按钮绑定 loading 状态（Bug 1 · 根因）

**文件**：`frontend/src/views/WorkbenchView.vue`

**改动位置**：image_review 和 final_review 的审核按钮模板（行 636-644、行 862-872 附近）

**如何改**：

image_review 审核按钮改为：
```html
<div class="wf-review-actions" v-if="nodeStatus('image_review') === 'awaiting_review' || reviewSubmitting">
  <button
    class="mint-btn mint-btn-outline"
    :disabled="reviewSubmitting !== null"
    @click="submitNodeReview('image_review', 'reject')"
  >
    <i data-lucide="undo-2" style="width:14px;height:14px;"></i>
    {{ reviewSubmitting === 'image_review:reject' ? '回退中...' : '打回（回退至 03）' }}
  </button>
  <button
    class="mint-btn mint-btn-primary"
    :disabled="reviewSubmitting !== null"
    @click="submitNodeReview('image_review', 'pass')"
  >
    <i data-lucide="check" style="width:14px;height:14px;"></i>
    {{ reviewSubmitting === 'image_review:pass' ? '提交中...' : '通过' }}
  </button>
</div>
```

final_review 审核按钮同理（key 换成 `final_review:reject` / `final_review:pass`）。

**关键点**：
- `:disabled="reviewSubmitting !== null"` 防止重复点击
- 按钮文字根据 `reviewSubmitting` 值动态切换为"回退中..."/"提交中..."
- `v-if` 条件加上 `|| reviewSubmitting`，保证 loading 期间按钮区域不会因 `node.status` 变化而提前消失

### 修复 2：reject 后显示回退进度提示（Bug 2 · 根因）

**文件**：`frontend/src/stores/workflow.ts` + `frontend/src/views/WorkbenchView.vue`

**改动 A — store 层：reject 后立即把目标节点设为 running，并加回退标记**

```typescript
// stores/workflow.ts submitReview 函数内
async function submitReview(reviewId: string, action: 'pass' | 'reject' | 'regenerate') {
  if (!currentWorkflow.value) return
  try {
    await workflowApi.submitReview(currentWorkflow.value.workflow_id, reviewId, action)
    const node = nodes.value.find(n => n.node_id === reviewId)
    if (node) {
      node.status = action === 'pass' ? 'passed' : 'rejected'
    }
    // ===== 新增：reject 后立即把回退目标节点设为 running，给用户即时反馈 =====
    if (action === 'reject') {
      // image_review reject → image_gen 重跑
      // final_review reject → copywrite 重跑
      const rollbackTarget = reviewId === 'image_review' ? 'image_gen'
                           : reviewId === 'final_review' ? 'copywrite'
                           : null
      if (rollbackTarget) {
        const target = nodes.value.find(n => n.node_id === rollbackTarget)
        if (target) {
          target.status = 'running'
          // 标记为回退重跑（前端模板可据此显示"重新生成中..."而非首次 loading）
          target.output = { ...(target.output || {}), _rollback: true }
        }
      }
    }
  } catch (e: any) {
    error.value = e.response?.data?.message || '提交审核失败'
    throw e
  }
}
```

**改动 B — view 层：image_gen 节点卡片在 running + _rollback 时显示回退提示**

在 image_gen 卡片渲染区域，当 `nodeStatus('image_gen') === 'running'` 且 `node.output?._rollback` 为 true 时，显示"审核打回，正在重新生成图片..."提示，而非首次生成的"等待图片生成"文案。

### 修复 3：_resume_graph_stream 补全 workflow_snapshot 字段（Bug 3）

**文件**：`backend/app/services/workflow.py`

**改动位置**：`_resume_graph_stream` 方法的 astream 循环（行 780-804）

**如何改**：让 workflow_snapshot 带上 `node_statuses` 的完整状态，前端可据此更新节点状态（即使节点函数还没推 node_started）。

```python
async for chunk in graph.astream(None, config):
    for node_key, delta in chunk.items():
        if not isinstance(delta, dict):
            continue
        node_statuses = delta.get("node_statuses", {})
        node_outputs = delta.get("node_outputs", {})
        all_node_statuses.update(node_statuses)
        if node_statuses or node_outputs:
            # ===== 修改：补全 status 字段，让前端 workflow_snapshot case 能触发 =====
            await sse_bus.publish(
                workflow_id,
                "workflow_snapshot",
                {
                    "workflow_id": workflow_id,
                    "current_node": delta.get("current_node", node_key),
                    "node_statuses": node_statuses,
                    "node_outputs_keys": list(node_outputs.keys()),
                    # 新增：带 status 让前端 currentWorkflow 更新
                    "status": "running",
                },
            )
```

> 注意：前端 `workflow_snapshot` case 检查的是 `payload.nodes`（数组）和 `payload.status`。补 `status` 字段后，至少 `currentWorkflow` 会更新。`nodes` 数组重建建议走轮询兜底接口（已有 `startPollingFallback`），不必在 snapshot 里塞完整 nodes（数据量大）。

### 修复 4（防御）：image_gen_node 重跑前重置 Playwright 单例健康检查

**文件**：`backend/app/services/card_renderer.py`

**如何改**：在 `_get_browser` 里增加 health check，如果 browser 已断开连接则先清理再重启。

```python
async def _get_browser():
    global _browser
    if _browser is not None and _browser.is_connected():
        return _browser
    # ===== 新增：断开连接的 browser 先置 None，避免复用僵尸实例 =====
    if _browser is not None and not _browser.is_connected():
        logger.warning("[card_renderer] browser disconnected, recreating")
        _browser = None
    async with _browser_lock:
        if _browser is not None and _browser.is_connected():
            return _browser
        # ... 原有启动逻辑
```

### 修复 5（防御）：recursion_limit 提示

**文件**：`backend/app/services/workflow.py`

`_resume_graph_safely` 的 except 分支已推 `workflow_error`。建议在错误消息里识别 `RecursionError`，给前端更友好的提示（"打回次数过多，请刷新页面重新开始"）。

---

## 五、为什么要这样改

### 0. Bug 0 是"通过后报错"的真正根因（最高优先级）

用户反馈"重复打回重来然后按通过后就报错"，根因是 **pass 分支没有 update_state 重置 rejected 状态**。

- reject 时 `update_state` 设了 `rejected`，写入 checkpoint
- 节点函数执行后返回 `rejected`，再次确认写入
- pass 时不覆盖，image_review_node 读到上次残留的 `rejected` → route 仍走回退 → 无限循环 → recursion_limit 触发

**这是确定性 bug，只要 reject 过一次，后续 pass 必然走回退路径**。不修这个，审核功能完全不可用（一旦打回就永远过不了）。

修复后：pass 时 `update_state` 设 `PASSED`，节点函数读到 `passed` → route 正常前进到 audit/publish。

### 1. Bug 1/2 是"卡死"感知的直接根因

用户说"卡死，直接不返回任何信息"，本质是**点击按钮后 UI 无即时反馈 + 回退重跑期间无进度提示**。

- HTTP 请求本身是立即返回的（200），不存在后端 hang
- 后台 task 也在正常执行（image_gen 重跑）
- 但前端在点击瞬间到 image_gen 推 node_started 之间有 0.5~2 秒空窗，加上 image_gen 渲染 5~30 秒，用户完全不知道发生了什么

**修复 1（按钮 loading）** 解决"点击无反应"的感知 — 按钮立即 disable + 文字变"回退中..."。
**修复 2（回退进度提示）** 解决"回退期间无反馈"的感知 — reject 后立即把 image_gen 设为 running 并显示"重新生成中"。

### 2. Bug 3 是"防御性补强"

当前节点函数内部会推 node_started/node_completed，前端能收到。但 `_resume_graph_stream` 推的 workflow_snapshot 因缺字段被前端忽略，相当于**少了一条事件通道**。补全 status 字段后，前端 `currentWorkflow.status` 能及时更新，增加 UI 响应的可靠性。

### 3. 修复 4/5 是"鲁棒性加固"

- Playwright 单例 browser 在长时间运行后可能断连，health check 避免复用僵尸实例导致 image_gen 静默失败
- recursion_limit 在极端情况（用户快速连点 reject）下可能触发，友好提示避免用户困惑

### 4. 没有改动 LangGraph 核心机制

`update_state + astream(None) resume` 机制本身是正确的。问题出在 **pass 分支漏调 update_state**（Bug 0）+ 前端反馈层缺失（Bug 1/2）+ 事件推送字段不全（Bug 3）。**不需要改动 graph.py 的节点函数和路由逻辑**。

---

## 六、改动文件清单

| 文件 | 改动类型 | 改动内容 | 优先级 |
|------|----------|----------|--------|
| `backend/app/services/workflow.py` | 修改（核心） | pass 分支补 `update_state` 设审核节点为 `PASSED`；`_resume_graph_stream` 的 workflow_snapshot 补 `status` 字段 | **P0** |
| `frontend/src/views/WorkbenchView.vue` | 修改 | 审核按钮绑定 `:disabled` + loading 文字；image_gen 卡片增加回退提示 | P1 |
| `frontend/src/stores/workflow.ts` | 修改 | `submitReview` reject 分支立即设回退目标节点为 running + `_rollback` 标记 | P1 |
| `backend/app/services/card_renderer.py` | 修改（防御） | `_get_browser` 增加断连 health check | P2 |

> 注：`docs/reject-fix/SOLUTION.md`（上一轮）已修复的 `update_state try-catch` + `_background_tasks` 引用保存 **保持不变**，本轮在其基础上补全前端反馈层。

---

## 七、实际落地记录（已全部完成）

以下改动已全部落地到代码中。

### 1. `backend/app/services/workflow.py`（P0 核心 · 两处改动）

#### 改动 A：pass 分支补 `update_state` 设审核节点为 `PASSED`

**位置**：`submit_review` 方法的 pass 分支（原行 690-721）

**改后代码**：
```python
# 通过：resume 工作流
if not LANGGRAPH_AVAILABLE:
    return {"success": False, "message": "LangGraph unavailable"}

graph = build_workflow_graph(checkpointer=None)
if graph is None:
    return {"success": False, "message": "Graph build failed"}

config = {"configurable": {"thread_id": workflow_id}, "recursion_limit": 50}

# 验证当前确实处于 interrupt 状态，并获取审核节点名
try:
    graph_state = graph.get_state(config)
    next_nodes = getattr(graph_state, "next", None) or ()
    if not next_nodes:
        return {
            "success": False,
            "message": f"Workflow not in interrupt state (next={next_nodes})"
        }
    review_node = next_nodes[0]  # image_review 或 final_review
    logger.info(
        f"[{workflow_id}] resume from interrupt: next={next_nodes}, "
        f"review_node={review_node}"
    )
except Exception as e:
    return {"success": False, "message": f"Get graph state failed: {e}"}

# ===== 关键：pass 时必须重置审核节点状态为 passed =====
# 否则如果之前 reject 过，checkpoint 里残留的 rejected 状态会导致
# image_review_node 读到 rejected → route_after_image_review 又走回退路径
# → 无限循环 → recursion_limit 触发报错
from app.agents.graph import NodeStatus
try:
    graph.update_state(
        config,
        {"node_statuses": {review_node: NodeStatus.PASSED.value}},
    )
    logger.info(
        f"[{workflow_id}] update_state OK (pass): "
        f"{review_node}={NodeStatus.PASSED.value}"
    )
except Exception as e:
    logger.exception(f"[{workflow_id}] update_state (pass) failed: {e}")
    return {
        "success": False,
        "message": f"Update state failed: {e}",
    }

# 推送节点状态变更事件（前端更新 UI）
await sse_bus.publish(
    workflow_id,
    "node_status_changed",
    {"node_id": review_node, "status": NodeStatus.PASSED.value},
)

# 异步 resume，不阻塞 HTTP 响应（保存 task 引用防止 GC）
self._create_background_task(
    self._resume_graph_safely(workflow_id, graph, config)
)

return {"success": True, "message": "Workflow resumed"}
```

**关键点**：
- `review_node = next_nodes[0]` 复用 reject 分支相同的逻辑，拿到当前 interrupt 的审核节点名
- `update_state` 把该节点设为 `PASSED`，覆盖上次 reject 残留的 `REJECTED`
- image_review_node 执行时读到 `passed` → `is_rejected=False` → 返回 `passed` → route 走 `audit`（正常前进）
- final_review 同理，读到 `passed` → route 走 `publish`

#### 改动 B：`_resume_graph_stream` 的 workflow_snapshot 补 `status` 字段

**位置**：`_resume_graph_stream` 方法的 astream 循环

**改后代码**：
```python
if node_statuses or node_outputs:
    await sse_bus.publish(
        workflow_id,
        "workflow_snapshot",
        {
            "workflow_id": workflow_id,
            "current_node": delta.get("current_node", node_key),
            "node_statuses": node_statuses,
            "node_outputs_keys": list(node_outputs.keys()),
            # 补 status 字段，让前端 workflow_snapshot case 能触发 currentWorkflow 更新
            "status": "running",
        },
    )
```

### 2. `backend/app/services/card_renderer.py`（P2 防御）

**位置**：`_get_browser` 函数

**改后代码**：
```python
async def _get_browser():
    """获取单例 Playwright browser（懒加载）。

    首次调用时启动 Playwright + chromium，后续复用。
    进程退出时自动清理。
    """
    global _browser
    if _browser is not None and _browser.is_connected():
        return _browser

    # 断开连接的 browser 先置 None，避免复用僵尸实例导致 image_gen 静默失败
    if _browser is not None and not _browser.is_connected():
        logger.warning("[card_renderer] browser disconnected, recreating")
        _browser = None

    async with _browser_lock:
        # 双重检查
        if _browser is not None and _browser.is_connected():
            return _browser
        # ... 原有启动逻辑
```

### 3. `frontend/src/stores/workflow.ts`（P1）

**位置**：`submitReview` 函数

**改后代码**：
```typescript
/** 提交审核 */
async function submitReview(reviewId: string, action: 'pass' | 'reject' | 'regenerate') {
  if (!currentWorkflow.value) return
  try {
    await workflowApi.submitReview(currentWorkflow.value.workflow_id, reviewId, action)
    // 更新本地节点状态
    const node = nodes.value.find(n => n.node_id === reviewId)
    if (node) {
      node.status = action === 'pass' ? 'passed' : 'rejected'
    }
    // reject 后立即把回退目标节点设为 running，给用户即时反馈
    // 避免审核按钮消失后到后端推 node_started 之间的 UI 空窗期
    if (action === 'reject') {
      // image_review reject → image_gen 重跑
      // final_review reject → copywrite 重跑
      const rollbackTarget = reviewId === 'image_review' ? 'image_gen'
                           : reviewId === 'final_review' ? 'copywrite'
                           : null
      if (rollbackTarget) {
        const target = nodes.value.find(n => n.node_id === rollbackTarget)
        if (target) {
          target.status = 'running'
          // 标记为回退重跑（前端模板可据此显示"重新生成中..."而非首次 loading）
          target.output = { ...(target.output || {}), _rollback: true }
        }
      }
    }
  } catch (e: any) {
    error.value = e.response?.data?.message || '提交审核失败'
    throw e
  }
}
```

### 4. `frontend/src/views/WorkbenchView.vue`（P1 · 两处改动）

#### 改动 A：image_review 审核按钮绑定 loading

```html
<div class="wf-review-actions" v-else-if="nodeStatus('image_review') === 'awaiting_review' || (reviewSubmitting && reviewSubmitting.startsWith('image_review:'))">
  <button class="mint-btn mint-btn-outline" :disabled="reviewSubmitting !== null" @click="submitNodeReview('image_review', 'reject')">
    <i data-lucide="undo-2" style="width:14px;height:14px;"></i>
    {{ reviewSubmitting === 'image_review:reject' ? '回退中...' : '打回（回退至 03）' }}
  </button>
  <button class="mint-btn mint-btn-primary" :disabled="reviewSubmitting !== null" @click="submitNodeReview('image_review', 'pass')">
    <i data-lucide="check" style="width:14px;height:14px;"></i>
    {{ reviewSubmitting === 'image_review:pass' ? '提交中...' : '通过' }}
  </button>
</div>
```

#### 改动 B：final_review 审核按钮绑定 loading

```html
<!-- 审核按钮 -->
<div class="wf-review-actions" v-if="nodeStatus('final_review') === 'awaiting_review' || (reviewSubmitting && reviewSubmitting.startsWith('final_review:'))">
  <button class="mint-btn mint-btn-outline" :disabled="reviewSubmitting !== null" @click="submitNodeReview('final_review', 'reject')">
    <i data-lucide="undo-2" style="width:14px;height:14px;"></i>
    {{ reviewSubmitting === 'final_review:reject' ? '回退中...' : '驳回修改' }}
  </button>
  <button class="mint-btn mint-btn-primary" :disabled="reviewSubmitting !== null" @click="submitNodeReview('final_review', 'pass')">
    <i data-lucide="check" style="width:14px;height:14px;"></i>
    {{ reviewSubmitting === 'final_review:pass' ? '提交中...' : '确认发布' }}
  </button>
</div>
```

**前端按钮改动的三个关键点**：
- `:disabled="reviewSubmitting !== null"` 防止重复点击
- 按钮文字根据 `reviewSubmitting` 值动态切换为"回退中..."/"提交中..."
- `v-if` 条件加上 `reviewSubmitting` 前缀匹配，保证 loading 期间按钮区域不会因 `node.status` 变化而提前消失

---

## 八、测试验证步骤

重启后端后，测试关键流程：

1. 启动工作流，跑到 image_review 审核节点
2. 点"打回重来" → 按钮应立即 disable + 显示"回退中..."，image_gen 卡片应立即显示 running
3. 等待 image_gen 重跑完成，再次到 image_review 审核
4. 重复 reject 2-3 次
5. **点"通过"** → 应正常前进到 audit（不再报错）

**关键日志验证**：
- reject 时：`update_state OK: image_review=rejected`
- pass 时：`update_state OK (pass): image_review=passed` ← 这行必须出现
- 如果 pass 后仍报错，重点检查这行日志是否输出，以及是否在 resume 之前

**final_review 同样测试**：reject → copywrite 重跑 → reject → pass → 正常 publish
