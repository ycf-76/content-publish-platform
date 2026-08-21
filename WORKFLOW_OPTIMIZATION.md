 # 工作流精炼优化方案

> 核心理念：把选择权还给创作者。工作流不是程序替用户跑完盖章，是用户在每个关键决策点 shape 方向。

---

## 一、问题诊断

### 当前工作流（改前）

```
search → analyze → quality_check_analyze → copywrite → quality_check_copywrite
→ image_plan → image_gen → image_review → audit → quality_check_audit
→ final_review → publish
```

12 个节点 + 4 个 interrupt 点（image_gen, image_review, final_review, publish）

### 五个核心问题

| # | 问题 | 说明 |
|---|------|------|
| 1 | 质检节点是摆设 | 3 个 quality_check 节点 MVP 阶段仅建议权，永远放行，等于空跑 3 次 LLM 调用 |
| 2 | 方向权在程序手里 | analyze 后用户看不到、选不了方向，程序替用户决定了"从什么角度写" |
| 3 | reject 是死循环 | final_review reject → copywrite → 同方向重写 → 大概率还是不满意；image_review reject → image_gen → 同文案重出图 → 大概率还是不对 |
| 4 | interrupt 放错了位置 | image_gen 前 interrupt：文案都没确认，图片基于什么生成？final_review 前 interrupt：东西都生完了，不满意只能 rollback |
| 5 | 用户只能盖章不能塑造 | 每个 interrupt 点用户只能 approve/reject，不能编辑内容、选择方向 |

### 创作者痛点（从用户视角走一遍工作流）

1. **方向不是我选的** — 分析结果出来，我看不到、选不了，程序替我决定了角度
2. **文案不是我定的** — 文案出来我才能看，但生成文案的方向已经错了，reject 回 copywrite 基于同一份 analyze 重写，同方向换个措辞还是不对
3. **改不了局部** — 文案好但图片不对，或图片好但文案要微调，做不到，改一个就得重跑后面一串
4. **reject 不改变方向只改变执行** — 这是最致命的：reject 后重跑用的是同样的输入，大概率产出同样的结果

---

## 二、目标工作流

```
search → analyze
  ↓
  🔴 创作点：用户选方向（看分析结果，选角度、选调性）
  ↓
copywrite（基于用户选的方向）
  ↓
  🔴 创作点：用户改文案（AI 给初稿，用户改字、改调、改结构）
  ↓
image_plan → image_gen（基于用户改完的文案）
  ↓
  🔴 创作点：用户调图片（图片基于已确认的文案，方向大概率对）
  ↓
audit → publish
  ↓
  🟢 安全门：用户确认发布
```

**3 个创作点 + 1 个安全门**，每个创作点用户不是 approve/reject，是**编辑和塑造**。

### interrupt_before 变更

| 改前 | 改后 | 理由 |
|------|------|------|
| image_gen | analyze | analyze 后让用户选方向，这是最值钱的决策 |
| image_review | copywrite | 文案是灵魂，文案确认后再出图 |
| final_review | image_gen | 图片基于已确认文案生成，用户调图 |
| publish | publish | 安全门保留 |

### 质检节点变更

| 节点 | 处理 | 理由 |
|------|------|------|
| quality_check_analyze | 删除 | 永远放行，空跑 |
| quality_check_copywrite | 删除 | 永远放行，空跑 |
| quality_check_audit | 删除 | 永远放行，空跑；audit 后直连 final_review |

### reject 回退目标变更

| 场景 | 改前 | 改后 | 理由 |
|------|------|------|------|
| image_review reject | → image_gen | → image_gen | 不变，图片不满意重做图片 |
| final_review reject | → copywrite | → copywrite | 不变，但文案方向是用户选的，reject 概率大幅降低 |

---

## 三、分期执行计划

### 第一期：去掉 quality_check_analyze + quality_check_copywrite ✅ 已完成

**改动文件：**

| 文件 | 改动 |
|------|------|
| `backend/app/agents/graph.py` | 删 2 个 add_node + 删 2 个 add_conditional_edges + 删 2 个 add_edge，改成 analyze → copywrite 直连 + copywrite → image_plan 直连；re-export 删 2 个质检函数 + 2 个路由函数 |
| `backend/app/agents/nodes/routing.py` | 删 route_after_analyze 和 route_after_copywrite |
| `backend/app/agents/nodes/__init__.py` | 删 2 个质检 import + 2 个路由 import + __all__ 清理 |
| `backend/app/agents/__init__.py` | 删 re-export |

**改后拓扑：**
```
search → analyze → copywrite → image_plan → image_gen → image_review → audit → quality_check_audit → final_review → publish
```

**验证结果：** import OK, graph build OK, nodes = [search, analyze, copywrite, image_plan, image_gen, image_review, audit, quality_check_audit, final_review, publish]

---

### 第二期：去掉 quality_check_audit + 调整 interrupt 点 ✅ 已完成

**核心改动：把 interrupt 从"审批点"改成"创作点"**

**实际改动文件：**

| 文件 | 改动 |
|------|------|
| `backend/app/agents/graph.py` | 删 quality_check_audit 的 add_node + add_edge + add_conditional_edges，改成 audit → final_review 直连；interrupt_before 从 ["image_gen", "image_review", "final_review", "publish"] 改成 ["copywrite", "image_plan", "image_review", "publish"]；re-export 删 audit_quality_check_node + route_after_audit |
| `backend/app/agents/nodes/routing.py` | 删 route_after_audit |
| `backend/app/agents/nodes/__init__.py` | 删 audit_quality_check_node import + route_after_audit import + __all__ 清理 |
| `backend/app/agents/__init__.py` | 删 re-export |
| `backend/app/services/workflow.py` | execute_graph 和 _resume_graph_stream 的 interrupt 检测逻辑重写：is_awaiting_review/is_awaiting_card_inject/is_awaiting_manual_resume 替换为 is_awaiting_direction_choice/is_awaiting_copywrite_review/is_awaiting_image_review；新增 direction_choice 和 copywrite_review 两种 review_required 事件类型 |
| `backend/app/api/routers/workflow.py` | get_workflow_nodes 兜底 node_order 更新（删 quality_check_audit，顺序调整）；interrupt 状态判断更新（copywrite/image_plan/image_review/publish 为 awaiting_review） |

**改后拓扑：**
```
search → analyze → copywrite → image_plan → image_gen → image_review → audit → final_review → publish
```

**interrupt_before = ["copywrite", "image_plan", "image_review", "publish"]**

**验证结果：** import OK, graph build OK, nodes = [search, analyze, copywrite, image_plan, image_gen, image_review, audit, final_review, publish]

**interrupt 语义：**

| interrupt 点 | 暂停时机 | 用户做什么 | resume 方式 |
|---|---|---|---|
| copywrite 前 | analyze 完成后 | 选方向/调性 | resume_workflow |
| image_plan 前 | copywrite 完成后 | 改文案 | resume_workflow |
| image_review 前 | image_gen 完成后 | 调图片 | resume_workflow |
| publish 前 | final_review 完成后 | 确认发布 | resume_workflow (auto_publish=True 时自动) |

---

### 第三期：前端交互改造 ✅ 已完成

**把 interrupt 点的前端交互从 approve/reject 改成编辑+继续**

| interrupt 点 | 改前前端交互 | 改后前端交互 |
|---|---|---|
| copywrite 前（analyze 完成后） | 无 | AnalyzeCard awaiting_review 状态：显示"分析完成，请选择创作方向后继续" + "开始创作"按钮，点击 resume |
| image_plan 前（copywrite 完成后） | 无 | CopywriteCard awaiting_review 状态：显示"文案已生成，请确认或修改后继续" + "生成图片"按钮，点击 resume |
| image_review 前（image_gen 完成后） | 审核卡片：通过/打回 | 图片确认卡片：标题改为"图片确认"，提示改为"请确认图片样式与质量"，按钮改为"确认通过"/"调优重做" |
| publish 前 | 确认发布按钮 | FinalReviewCard：终审按钮改为"确认，进入发布"/"调优重做"，状态标签改为"请确认"/"已调优" |

**实际改动文件：**

| 文件 | 改动 |
|------|------|
| `stores/workflow.ts` | review_required SSE 事件处理：区分 review_type（direction_choice/copywrite_review/image/publish/final），保存到 node.output.review_type；review_processed reject 回退映射：image_review → image_gen；submitReview reject 回退逻辑更新 |
| `components/workbench/AnalyzeCard.vue` | 新增 awaiting_review 状态展示："请选择方向" + "开始创作"按钮；emit enter-copywrite 事件；statusLabel/statusColor 映射更新 |
| `components/workbench/CopywriteCard.vue` | 新增 awaiting_review 状态展示："请确认文案" + "生成图片"按钮；emit continue-to-image 事件；statusLabel/statusColor 映射更新 |
| `components/workbench/ImageReviewCard.vue` | 全部"审核"文案改为"确认/调优"：标题"图片确认"、提示"请确认图片样式与质量"、按钮"确认通过"/"调优重做"、statusLabel"请确认图片"/"已调优"、reviewStatusLabel"确认通过"/"调优重做" |
| `components/workbench/FinalReviewCard.vue` | 终审文案改为创作点定位：按钮"确认，进入发布"/"调优重做"、statusLabel"请确认"/"已调优"、reviewStatusLabel"请确认"/"已调优"、idle 提示"等待图片确认后" |
| `views/WorkbenchView.vue` | AnalyzeCard 绑定 @enter-copywrite → onEnterCopywrite()；CopywriteCard 绑定 @continue-to-image → onContinueToImage()；两个函数均调用 workflowStore.resumeWorkflow() |

---

## 四、改后工作流完整拓扑

```
search → analyze
  ↓ interrupt_before=["copywrite"]
  🔴 用户选方向（看分析结果，选角度/调性，resume 时携带选择）
  ↓
copywrite
  ↓ interrupt_before=["image_plan"]
  🔴 用户改文案（编辑标题/正文/标签，resume 时携带修改）
  ↓
image_plan → image_gen
  ↓ interrupt_before=["image_review"]
  🔴 用户调图片（卡片编辑器，resume 时携带图片数据）
  ↓
image_review → audit → final_review
  ↓ interrupt_before=["publish"]
  🟢 用户确认发布
  ↓
publish → END
```

9 个业务节点，0 个质检节点，4 个创作点 interrupt。

---

## 五、风险与回退

| 风险 | 应对 |
|------|------|
| interrupt 语义变更导致前端审核流程断裂 | 第二期改后端时同步改前端 store 的 interrupt 类型判断 |
| resume 携带数据格式变更 | 新增 resume_with_data 接口，保持原 resume 接口向后兼容 |
| 去掉 quality_check_audit 后 audit 直连 final_review | quality_check_audit 永远放行，去掉不影响路由，audit 的 suggestion 通过 SSE 推送不变 |
| 已有 checkpoint 数据不兼容 | interrupt_before 变更后，旧 checkpoint 的 next 值会不同，需要清空 langgraph_checkpoints.sqlite 或加版本迁移 |

---

## 六、验证清单

- [x] 第一期：import 验证通过
- [x] 第一期：graph build 验证通过
- [x] 第一期：节点列表正确（无 quality_check_analyze / quality_check_copywrite）
- [x] 第二期：interrupt_before 变更后 graph build 验证
- [x] 第二期：execute_graph interrupt 检测逻辑重写
- [x] 第二期：_resume_graph_stream interrupt 检测逻辑重写
- [x] 第二期：routers/workflow.py 兜底 node_order 更新
- [x] 第二期：resume_workflow 各类型 resume 逻辑验证（代码审查通过）
- [x] 第三期：AnalyzeCard awaiting_review 交互 + enter-copywrite 事件
- [x] 第三期：CopywriteCard awaiting_review 交互 + continue-to-image 事件
- [x] 第三期：ImageReviewCard 文案从"审核"改为"确认/调优"
- [x] 第三期：FinalReviewCard 文案从"审核/打回"改为"确认/调优"
- [x] 第三期：WorkbenchView 事件绑定 + resumeWorkflow 调用
- [x] 第三期：workflow.ts review_required 事件处理 + review_type 区分
- [x] TypeScript 编译检查通过（vue-tsc --noEmit exit 0）
- [x] Python 编译检查通过（py_compile 全部 OK）
- [x] 端到端：前端 vite build 通过（exit 0）
- [x] 端到端：后端 import 链 + graph build 验证通过（9 业务节点，0 质检节点）
- [ ] 端到端：完整工作流运行验证（需启动后端 + 前端实际执行工作流）