# 图文创作升级方案（P0 已落地）

## 目标

1. 让对话式创作不再退化为「封面 + 正文 + 正文 + 金句」。
2. 让模型能够使用 list / dark_panel / compare / steps / numbered_cards 等组件。
3. 不再丢失卡片页面的组件级数据，为单页精修和重新生成保留上下文。
4. 为「作品分析 → 下一次创作」的沉浸式呈现打好数据基础。

## 已完成的 P0 改动

### 后端

- `backend/app/tools/image_gen_skill.py`
  - 新增 `content_type`、`insights`、`visual_suggestion` 输入。
  - `blueprint` 模式改为复用 `ContentPlanner`，输出 `card_draft`。
  - 保留 `legacy_blueprint` 模式兼容旧动态布局。
  - `candidate` 模式不再固定 4 张「封面 + 2 内容 + 金句」，改为按内容类型生成页面角色。
  - 新增 `_ROLE_PRESETS`，对比型 / 教程型 / 清单型 / 观点型 / 叙事型使用不同页面节奏。

- `backend/app/agents/nodes/image_plan_planner.py`
  - 新增 `enforce_page_diversity()`：
    - 首页必须是封面；
    - 收尾页不使用清单 / 步骤 / 对比类结构；
    - 相邻页不能相同类型；
    - 连续 `content` 页自动转换为 `list / dark_panel / steps / numbered_cards / quote`；
    - 整体不足 3 种页面结构时继续转换中间页。
  - 新增 `_convert_page()`，转换时保留原文案并生成对应字段。
  - 新增 `_fallback_order()`，只选择当前模板支持的页面类型。
  - `build_content_plan_prompt()` 增加视觉多样性硬性要求。

### 前端

- 新增 `frontend/src/composables/cardDraft.ts`
  - `normalizeCardDraft()`：保留页面全部字段，不再只保留 `type/title/imageUrl/htmlUrl`。
  - `pickCoverUrl()`、`pickImages()`：统一封面与图片列表推导。

- `frontend/src/stores/work.ts`
  - `cardDraft.pages` 改为 `Array<Partial<CardPage> & { type: string }>`。
  - 支持保存 `title`、`template`。

- `frontend/src/components/chat/ChatView.vue`
  - `shortcut_completed` 与 `agent_output` 分支改用 `normalizeCardDraft()`。

- `frontend/src/components/chat/composables/useChatSSE.ts`
  - `draft_patch` 与 `card_draft_ready` 分支改用 `normalizeCardDraft()`。

- `frontend/src/composables/useCardEditor.ts`
  - 恢复草稿时保留 `textOverlayBlocks` 与 `textOverlayTemplateId`。

- `frontend/src/components/workbench/ImagePlanCard.vue`
  - 页面类型标签改用 `FULL_PAGE_TYPE_LABELS`，覆盖全部 18 种页面类型。

- `frontend/src/styles/workbench/_trends.css`
  - 修复编码损坏的 `.wf-type-*` 选择器（原文件按 GBK 误解码成乱码，构建会告警且样式失效）。
  - 改为属性选择器匹配「粉丝型 / 内容型 / 双重型 / 普通」，避免再次出现编码问题。

## 验证

- `backend/.venv` 下 `test_image_plan_planner.py` 等图片/卡片相关测试通过。
- 页面多样性示例：
  - 输入 5 张连续 `content` 页，输出 `cover / content / list / content / quote`。
  - Esther 模板下输出 `cover / content / dark_panel / content / quote`。
- 前端 `vue-tsc --noEmit` 通过。

## P1-1 已完成：统一 CreativeArtifact

### 后端

- 新增 `backend/app/services/creative_artifact.py`
  - 数据结构：`source / analysis / brief / storyboard / assets / quality / review / history`。
  - `build_storyboard()`：把 `card_draft.pages` 提升为带语义角色的分镜，包含
    `role / role_label / rationale / source_evidence / visual_goal / component / image_role`。
  - 语义角色：hook、pain、explanation、evidence、contrast、process、action、credibility、summary。
  - `infer_role()` 根据页面类型与位置推断角色；首页固定 hook，尾页优先 summary / action。
  - `to_card_draft()` 反向输出，保证不破坏现有卡片编辑器与渲染链路。
  - JSON 文件持久化：`backend/app/data/creative_artifacts/*.json`。

- 新增 `backend/app/api/routers/creative_artifact.py`
  - `GET /api/creative-artifacts`：列表。
  - `POST /api/creative-artifacts/build`：从 card_draft / brief / analysis 构建。
  - `POST /api/creative-artifacts/storyboard`：只做分镜提升预览。
  - `GET /api/creative-artifacts/{id}`、`GET /{id}/card-draft`、`PUT /{id}`、`PATCH /{id}`。

- `backend/app/agents/nodes/image_plan.py`
  - 规划完成后生成并保存 `CreativeArtifact`。
  - `content_plan.creative_artifact` 输出 `artifact_id / page_roles / storyboard`。

### 前端

- 新增 `frontend/src/types/creativeArtifact.ts`：与后端一一对应的类型与 `emptyArtifact()`。
- 新增 `frontend/src/api/creativeArtifact.ts`：list / get / build / storyboard / save / patch / card-draft。
- 新增 `frontend/src/stores/creativeArtifact.ts`：统一创作对象状态管理。

### 验证

- 分镜提升示例：`cover → hook`、`content → explanation`、`list → evidence`、`quote → summary`。
- 持久化与反向 `to_card_draft()` 正常。
- 路由注册正常，`vue-tsc` 与 `vite build` 通过。

## P1-3 已完成：共享质量门禁

把 BLCaptain 风格校验的 R1-R9 与满铺图构图合同抽成所有出图路径统一调用的服务，
避免每条生成链路各写一套校验、标准漂移。

### 新增后端服务

- 新增 `backend/app/services/quality_gate.py`
  - 阈值来自 `full-bleed-image-composition-contracts.json`：
    - `MIN_QUIET_ZONE_RATIO = 0.3`（留白比下限）
    - `MAX_TITLE_CANVAS_RATIO = 0.4`（标题占画布比上限）
    - `MAX_OVERLAY_PEAK_ALPHA = 0.3`（蒙版峰值透明度上限）
  - 文本字数 / 行数上限 `FIELD_CAPS`（R2 Type Caps 的内容层代理）：
    title / subtitle / footer / content / highlight / tag / ctaText / masthead。
  - 数组长度区间 `ARRAY_CAPS`（R4 Band Density 的内容层代理）：
    listItems / compare*Items / steps / numberedItems / iconTextPairs / newspaperCols。
  - `QualityIssue`（rule / severity / scope / page_index / field / message / suggestion）、
    `PageQuality`、`QualityReport`（passed / blocking / warn / info / page_reports / draft_issues / summary）。
  - `check_page(index, page)`：R2 / R3 / R4 / R7 / R8 / R9 的内容层代理。
  - `check_draft(card_draft)`：逐页检查 + 跨页检查（首页 cover、尾页收尾、相邻骨架去重、
    多样性预算 ≥3 种、计数匹配）。
  - `run_quality_gate(...)`：门禁入口，异常时降级为通过（不阻断出图，人工 review 兜底）。
  - `gate_badge(report)`：压缩成前端 badge（pass / warn / fail）。

### 复用的出图路径（四处统一）

1. `backend/app/agents/nodes/image_plan_planner.py` — `ContentPlanner.plan()` 在
   `enforce_page_diversity()` 之后调用 `run_quality_gate()`，并把报告挂到 `card_draft["quality"]`。
2. `backend/app/tools/image_gen_skill.py` — `blueprint` 模式规划后调用 `run_quality_gate()`，
   输出 `quality` 字段（对话式创作即时可见质量 badge）。
3. `backend/app/agents/nodes/image_gen.py` — 卡片编辑器注入图片后，用最终页面类型复跑门禁，
   把报告挂到 `validation.quality`（相邻去重 / 多样性 / 计数）。
4. 前端补充校验入口：`POST /api/quality-gate/check`（卡片编辑器 html2canvas 导出前预检、最终 review 复核）。

### 验证

- 命中：空正文页、相邻 content 重复、满铺图缺 `objectPosition/subjectMap/safeTextZones/avoidZones`、
  满铺图 `quietZoneRatio<0.3` / `titleCanvasRatio>0.4` / `overlayPeakAlpha>0.3` 均被 blocking 捕获。
- 干净草稿（`cover/list/steps/quote`）通过门禁，无 blocking。
- `py_compile` 全部通过；`ContentPlanner.plan()`（fallback 路径）正确挂载 `quality`。

## 下一步（P1 剩余 → 已并入 P2）

1. 把 BLCaptain 的质量规则抽成共享服务（✅ 已完成，见上）。
2. 对话式创作在生成后调用 `/build`，并把 `artifact_id` 带入下一轮创作上下文（并入 P2）。

## 下一步（P2）

1. 作品分析后生成「创作承接卡」：保留模式、避坑模式、置信度、原作品缩略图。
2. 创作前选择方向：沿用结构 / 改造结构 / 全新表达。
3. 先展示分镜，再逐页生成。
4. 把 `FinalReviewCard.vue` 的手机预览提前到封面生成阶段。
5. 单页精修：换版式、换图片、改密度、重新生成当前页。

## P2 已落地（增量 1）：分析到创作沉浸式承接

对应原问题 2——分析联动后如何让用户投入下一次创作。

### 前端

- 新增 `frontend/src/components/chat/CreationHandoffCard.vue`
  - 复用顶部「分析已联动」条的数据（`workStore.analysisContext`）：
    原作品缩略图、已验证模式（best_patterns）、避坑模式（avoid_patterns）、置信度。
  - 三种创作方向按钮：沿用结构 / 改造结构 / 全新表达，各自带建议分镜结构预览。
  - 选方向后出现「建议分镜」条（手机框 mini 预览，cover/list/content/…），
    明确标注「预览结构，真实生成会过质量门禁细化」。
  - 点击「开始创作」emit `start`，携带 direction / proposedStructure / analysis。
- 改造 `frontend/src/components/chat/ChatView.vue`
  - 分析条新增「开启创作」按钮（`Sparkles`），打开承接卡。
  - 新增 `handoffOpen` ref 与 `onHandoffStart()`：把方向 + 建议结构 + 模式/避坑
    拼成创作指令写入 `inputText` 并调用 `sendMessage()`，分析上下文由 `buildAnalysisPrompt()` 自动带入。
  - 复用 `FULL_PAGE_TYPE_LABELS` 渲染分镜页标签。

### 验证

- 两个 SFC 通过 `@vue/compiler-sfc` parse + script + template 编译（template errors = 0）。
- 承接卡与触发链路自包含，不改动既有生成/渲染路径。

### 待续（P2 增量 2+）

- 真实「逐页生成」进度：生成时按 proposedStructure 逐页流式展示（需后端 SSE 支持分页进度）。
- 把 `FinalReviewCard.vue` 手机预览提前到封面生成阶段（早期预览）。
- 单页精修：换版式 / 换图 / 改密度 / 重生成当前页（复用 CreativeArtifact.storyboard 的 page 级 context）。

## P2 已落地（增量 2）：手机预览提前

把 `FinalReviewCard.vue`「发布预览」节点的手机外框语言抽成可复用组件，让手机预览从终审节点提前到创作起点（规划阶段即可看到手机比例的分镜）。

### 前端

- 新增 `frontend/src/components/chat/PhoneFrame.vue`
  - 两种变体：`full`（完整外框：状态栏 + 刘海 + home 指示条，325px，用于真实预览）与 `mini`（紧凑外框：仅圆角 + 小刘海，58×82，用于分镜条缩略预览）。
  - 默认 slot 承接内容，视觉与 FinalReviewCard 一致。
- 改造 `frontend/src/components/chat/CreationHandoffCard.vue`
  - 建议分镜条每页改用 `<PhoneFrame variant="mini">` 渲染——用户在选方向时就能看到「页面在手机里的比例与顺序」，而非纯文字标签。
  - 移除旧的 `.chc-page-frame` 平框样式。

### 验证

- PhoneFrame / CreationHandoffCard / ChatView 三个 SFC 通过 `@vue/compiler-sfc` parse + script + template 编译（template errors = 0），无 `chc-page-frame` 残留引用。

### 待续（P2 增量 3+）

- 真实「逐页流式生成」进度（需后端 SSE 分页进度）。
- 单页精修：换版式 / 换图 / 改密度 / 重生成当前页（复用 CreativeArtifact.storyboard）。

## P2 已落地（增量 3）：生成结果逐页揭示

让用户在聊天侧看到「先分镜、再逐页出现」的完整节奏——承接卡看完分镜后，
生成结果在右侧草稿面板逐页淡入，而不是整屏一次性出现。

### 前端

- 改造 `frontend/src/components/chat/WorkDetailPanel.vue`
  - 视觉组图渲染的每一页 `.wdp-card-draft-page` 加 `wdp-page-reveal`：
    `opacity/translateY` 入场动画，`animation-delay: calc(var(--page-index) * 90ms)` 逐页错峰。
  - 页面 div 绑定 `:style="{ '--page-index': pi }"` 驱动错峰。

### 验证

- WorkDetailPanel.vue 通过 `@vue/compiler-sfc` parse + script + template 编译（template errors = 0）。

### 待续（P2 最后一项）

- 单页精修：换版式 / 换图 / 改密度 / 重生成当前页（复用 CreativeArtifact.storyboard 的页级 context，落在卡片编辑器侧）。
- 可选增强：后端 SSE 真·分页进度（生成过程中逐页 emit，而非生成后错峰揭示）。

## P2 已落地（增量 4 / 末项）：单页精修（Chat 侧）

> 更正：末项原本误落在工作流图片编辑器（ImageWorkspace / PageList / useCardEditor），已回退；按需求改到 **Chat 侧**
> `WorkDetailPanel.vue` 的「视觉组图」——即 P2 增量 3 逐页揭示的那块卡片上。Chat 侧没有独立卡片编辑器，
> 生成的卡片页以 `work.cardDraft.pages` 形式存在工作流 store，精修直接读写该草稿并 `updateDraft` 持久化。

### 前端：WorkDetailPanel.vue（Chat 侧视觉组图）

- 每块 `.wdp-card-draft-page` 右上角 hover 显示 `✎` 精修按钮，点击在卡片下方展开 `wdp-refine-pop` 内联面板。
- 四个分区（均作用于 `work.cardDraft.pages[index]`，改完 `workStore.updateDraft(work.id, { cardDraft })`）：
  - **换版式**：`FULL_PAGE_TYPE_LABELS` 三列 chip 网格，当前版式高亮；`changePageTypeAt(index, type)`。
  - **换图**：图片链接输入框，回车/失焦提交 `imageUrl`（`commitImageAt`）。
  - **改密度**：`精简`（`trimAt`，截断标题≤16、正文≤48、list 收至 3 条）。
  - **重生成当前页**：`regenerateAt` 清空该页可编辑文案、保留 `type/imageUrl`，再 best-effort 调 `buildStoryboard` 取回该页 `role_label / rationale` 作为面板内联提示（后端不可用时降级为本地提示）。
- 新增脚本：`refineOpenIndex` / `refineHint` 状态 + `getDraftPages` / `persistPages` / `toggleRefine` / `closeRefine` / `changePageTypeAt` / `commitImageAt` / `trimAt` / `regenerateAt`；新增轻量样式（浅色主题，匹配面板）。
- 导入：`FULL_PAGE_TYPE_LABELS`（esther-templates）、`buildStoryboard`（creativeArtifact API）。

### 回退记录（避免误改工作流编辑器）

- `ImageWorkspace.vue`、`PageList.vue` 恢复原状（移除 refine 相关导入 / 状态 / handler / emit）。
- `useCardEditor.ts` 移除 `trimPage` / `setPageImage` / `regeneratePage` 三个仅编辑器侧使用的原子方法及其导出（Chat 侧改用轻量实现，不引入重型编辑器）。

### 验证

- WorkDetailPanel.vue、ImageWorkspace.vue、PageList.vue 三文件通过 `@vue/compiler-sfc` 编译（template errors = 0，EXIT=0）。
- 全前端 grep `trimPage|setPageImage|regeneratePage` 无残留引用。

### P2 全部完成

至此 P2 四项增量（分析→创作沉浸式承接、手机预览提前、生成结果逐页揭示、单页精修）全部落地。
配合 P0（对话式多样性）+ P1（统一 CreativeArtifact + 共享质量门禁），原「两个问题」对应的两条主线均闭环。
