# ReAct 图文卡片系统架构诊断与演进方案

> 范围：**对话式 ReAct（ChatAgent → AgentHarness → LoopExecutor → card skills）**。不是 LangGraph/DAG 工作流，也不是改用 React 前端。当前前端是 Vue（`frontend/package.json:13-58`）。本文先记录基于源码的架构诊断和实施方案；后续实施状态与验证结果见文末“实施进展”。真实供应商生图尚未调用。

## 结论先行

你提出的两个体验问题成立，但需要精确表达：**ReAct 并非在运行时“只有一个模板”**，它让模型直接写自由 HTML，理论上可以写不同版式；实际是 *没有受约束且可执行的多版式/多素材/生图组合协议*。示例 HTML、配方偏向同一骨架，主题大多体现为调色与字体；输出只有 `htmlContent`，后续没有可编辑的结构和可预测的图片位。修复不是“再给模型几个 CSS 模板”，而是把卡片做成 **结构化作品 + 版式能力库 + 图片资产解析 + 单源渲染器**，由 ReAct 选择并调用高级创作能力。

建议沿现有 `CARD_DSL_P1_SPEC.md` 的方向推进，但**先以 ReAct 对话为第一个消费者，先打通小型纵向闭环**，不要让已经断链的 DAG 编辑器或缺失的模板注册表成为前置条件。

## 1. 真实链路（仅 ReAct 主线）

```text
POST /api/v1/chat/agent
 → ChatAgent.process() → AgentRegistry.build_harness() → AgentHarness.run()
 → LoopExecutor：system prompt / 工具目录 → 模型选 card_xiaohongshu 等 Skill
 → PromptDrivenSkill.execute()：加载本技能及存在的 references，调用 LLM
 → 从 <!--card-html--> 提取完整 HTML → card_draft.pages[].htmlContent
 → LoopExecutor._persist_creative_state → chat session 的 _card_draft + draft_patch SSE
 → useChatSSE.normalizeCardDraft → ChatCardDraft / WorkDetailPanel 的 iframe(srcdoc)
```

证据：`backend/app/agents/chat_agent.py:1-5,49-118`；`backend/app/agents/registry.py:202-210,221-235,301-354`；`backend/app/engine/harness/executor/loop.py:1068-1176,1524-1604,2449`；`backend/app/tools/base.py:232-267,302-398`；`frontend/src/components/chat/composables/useChatSSE.ts:823-853`；`frontend/src/components/chat/ChatCardDraft.vue:9-39`。`backend/app/agents/graph.py` 的 image_plan/image_gen 是**另一条 DAG 路径**，不应被当成本问题的主故障链。

### 运行时观察（不要和文档规划混淆）

| 事实 | 代码证据 | 影响 |
|---|---|---|
| `card_xiaohongshu` 明确指示 LLM 写整页 HTML，示例直接固定 `.xhs-card` 的 1080×1440、flex 列、padding 等 | `backend/app/agents/prompts/skills/card-xiaohongshu.md:30-32,79-131` | 模型倾向复用示例几何；更换 palette 并不等于换骨架 |
| 运行输出只是 `{id,type,title,htmlContent}`，`type` 按首/中/尾位置赋值，并非内容语义 | `backend/app/tools/base.py:245-265` | 无 image slot、布局 ID、block ID，无法可靠替换单图、换局部排版或审计 |
| 已有“封面/账本/流程/对比/网格/数据”等**文字配方**，但它们只是 prompt，不是可执行组件库 | `backend/app/agents/prompts/references/card-recipes.md:8-54` | 不能保证模型每次调用相应布局、也无法程序化验证 |
| ReAct 的技能目录/引导提前可见，但技能级 references 到 execute 时才加载；缺失文件被静默跳过 | `backend/app/engine/harness/executor/loop.py:1094-1159`；`backend/app/tools/base.py:284-300` | 决策阶段不知道真正可用版式；`card-design.md:22-29` 引用的 `styles.md`、`typography.md` 缺失 |
| 设计知识有摘要注入，不过不是布局能力 API | `backend/app/agents/prompts/references/design_system_injector.py:27-48,141-191` | 增加规则文字不足以使版式/图片变成可调用对象 |
| `image_gen.py` 存在 `ImageGenAdapter`/`WanxAdapter` 和选择器，却未发现 ReAct 卡片路径调用选择器 | `backend/app/adapters/image_gen.py:73-105,451+`；`backend/app/tools/base.py:302-398` | “有生图代码”不等于“对话卡片能生图” |
| ReAct 的 `card_draft` 只对 `_CARD_PRODUCE_TOOLS` 白名单中工具进入 creative_state 和 SSE | `backend/app/engine/harness/executor/loop.py:1537-1570` | 新卡片工具若未改白名单，能执行却不会在聊天中出现；应改为产物契约识别 |
| 聊天卡片“编辑”只打开 work detail，那里仍以 HTML iframe 展示 | `frontend/src/components/chat/AssistantMessageCell.vue:249-253,349-353`；`ChatCardDraft.vue:23-30` | 现有 ReAct 结果不是可视化积木编辑器 |

**补充边界，不是把 DAG 错误拿来解释 ReAct**：现存 `frontend/src/card-editor/templates.ts:11-15,45-98,364-449` 有 18 个 page type、6 个颜色/字体主题，但 `TemplateVariant` 只有 `default`；更关键的是 `ImageWorkspace.vue:50,74-96,147-180` 画布/属性/导出容器被移除，`useCardEditor.ts:568-595` 却仍查找 `.card-canvas`。这些影响“想复用当前编辑器”的可行性，**不构成 ReAct HTML 生成的根因**；不建议把旧工作区作为新卡片系统的必经路径。

### 技能体系本身的两处结构隐患

- `LoopExecutor._system_prompt()` 在 `execute()` 的 `loop.py:361` 先运行；工具表在 `loop.py:1853` 才构建，而后者最多 65 个工具（`loop.py:1191,1228-1275`）。首轮目录可能列出实际未进入 function-calling 的工具（`loop.py:1125-1128`），所以“模型知道有能力”和“模型真的能调用”要统一；不是多堆技能解决。
- `card-xiaohongshu.md:140-156` 声称运行共享渲染/审计脚本，但仓库中不存在这些脚本；`card-design.md:22-29` 引用的部分 reference 也不存在。技能的步骤描述不等于可执行交付管线；需要启动时校验能力依赖并在缺失时显式告警，而非静默跳过。

## 2. 竞品可借鉴的“机制”，不是照搬模板数

- **Canva Magic Design**：以文字或自有媒体起稿，套品牌风格后仍能继续编辑；启示是“上传图片 → 成为可替换设计素材”，而非让 AI 把图片 URL 写进一张死 HTML。[官方说明](https://www.canva.com/magic-design/)。其 [Magic Layers](https://www.canva.com/magic-layers/) 强调修改一个元素无需重做整张图，恰好对应本项目 block/slot 可编辑性。
- **Adobe Express**：文本生成社媒贴、海报、卡片的**可编辑模板**，用户挑方向后继续修改；启示是把生成结果交付为可编辑对象，不是仅交 PNG 或 HTML。[官方说明](https://helpx.adobe.com/express/web/create-with-templates/text-to-template.html)。
- **Figma 卡片布局生成**：基于既有组件、token、间距规则生成多个**结构方向**，并行比较后细调；启示是“版式变体 × 组件约束 × 多候选”，不等于 6 个颜色主题。[官方说明](https://www.figma.com/solutions/ai-card-layout-generator/)。
- **Gamma**：从大纲生成内容，后续增加 smart layouts、rich content、生图、再编辑，官网还明确提到 social media 输出；启示是先定信息结构，再配置媒体与布局。[官方说明](https://gamma.app/)。

以上是公开产品能力的对照，不推断其内部技术实现。

## 3. 推荐的目标架构：ReAct 负责任务选择，卡片能力负责确定性组合

```text
用户请求/上传资产/当前作品
    ↓
ReAct：理解“做知识卡 / 图片主视觉 / 对比 / 探店”等意图，调用 compose_card_deck
    ↓
CardComposer 服务（工具内部确定性流程，不是 DAG）
  A 语义规划：Deck → 每页 block / 图像需求 / 内容角色
  B 候选编排：从布局注册表匹配，生成 2-3 套“几何方向”供选，不只变色
  C 资产解析：upload → asset → AI 生图（明确授权/预算）→ 占位/降级
  D 契约校验：block 数量/密度/图片槽位/品牌/安全边距
  E 单源渲染：Deck + Layout + Theme + resolved assets → HTML → 同源预览/PNG
    ↓
card_draft（携带结构化 Deck + 预览/PNG + revision）→ 现有 draft_patch SSE
    ↓
聊天预览 / 作品详情 → 换图、换布局、改单块 → 局部重渲 → 审核/发布
```

**关键不是抛弃 HTML/CSS**：HTML/CSS 仍是浏览器排版的执行层，不能再当**模型输出协议/持久化事实源**。LLM 只产受校验的结构化意图，不给模型任意脚本、CSS 或外链权限。首版不要构建自由拖拽式 Figma，优先做受控布局与块级编辑，以生成质量和可控性换掉无边界自由度。

### 最小契约（在 `CARD_DSL_P1_SPEC.md` 的 Deck/Page/Block 上修正）

```json
{
  "schema_version": 2,
  "deck_id": "d_123",
  "theme_id": "indigo_porcelain",
  "canvas": {"width": 1080, "height": 1440},
  "pages": [{
    "id": "page_01",
    "role": "body",
    "layout_id": "image_right_ledger",
    "variant": "normal",
    "blocks": [
      {"id": "b1", "type": "heading", "text": "旅途装备清单"},
      {"id": "b2", "type": "list", "items": [{"title": "雨衣", "desc": "比伞更省空间"}]},
      {"id": "b3", "type": "image", "slot_id": "hero", "media_id": "asset_42", "fit": "cover", "focal_point": [0.5, 0.4], "alt": "折叠雨衣"}
    ]
  }]
}
```

示意 JSON 只说明 **layout 与主题分离 / 图片 slot 可以引用资产 / block 有稳定 ID**，并非已实现接口或可直接通过现有规格的样例：列表条数、版式合法性须由注册表进一步校验。生产契约需给每张图 `source(upload|asset|ai) / prompt / job_id / media_id / license_or_consent / status / crop`，生成失败不可默默发布空图；新上传统一入资产库而不是让 LLM 引用本机路径或任意远程 URL。

**组合的三根轴**：① 页面“语义”＝封面/步骤/对比/实拍展示/收尾；② “结构”＝无图清单、左右图文、顶图、全图覆字、拼贴等几何；③ “视觉语言”＝主题 token、字型、边界与装饰。三者独立，按内容密度和图片可用性约束组合；同一 Deck 锁定主视觉语汇，跨页换布局与密度，避免“每页都像同一 PPT”，也避免每页随机拼出风格杂乱。

**生图策略**：先处理用户上传（最高优先、未经许可不替换）与资产匹配；用户要求“生图”或视觉确有必要时，通过媒体服务复用 `backend/app/adapters/image_gen.py` 的 provider 抽象，经异步任务取回**持久化资产 ID**；prompt 描述画面，不让生图模型绘制正文文字，中文标题由排版引擎绘制。基于图片位目标比例预留 crop/焦点；用字体、主题、构图提示统一一套卡的视觉。API 错误、额度、超时必须有可见的失败/重试/替换动作。外部模型调用成本须受配额和用户意图控制。

**单源渲染**：后端服务编译 Deck→一份固定版本的 HTML/CSS（生产模板，不由 LLM 写），Vue 用这份 HTML 做隔离预览；Playwright/Chromium 用**同一份 HTML、相同字体与尺寸**截图为 PNG。仅靠 Vue 自己写一份版式、Playwright 再写另一份并不能做到所见即所得；这里不要求重写前端为 React。导出完成再检查文本溢出、图片实际加载、对比度/密度，失败返回结构化诊断。旧 `htmlContent` 可继续在 sandbox iframe 展示，但不能冒充新 DSL 的可编辑作品。

### ReAct 具体落点与接口建议

| 落点 | 推荐变更（未来实施，当前未修改） |
|---|---|
| `backend/app/agents/registry.py:221-235` / 技能路由 | 将一个高层 `compose_card_deck` 工具加入 image_text 可调用集合；另提供 `replace_media_slot` / `reflow_page` 等少数编辑动作，**不要给模型暴露 24 个布局工具** |
| `backend/app/tools/base.py:302-398` | 现有自由 HTML 的 PromptDrivenSkill 保留兼容；新卡片工具用有 `input_schema` 的显式 Skill，避免通用 prompt 技能一边写任意 HTML 一边假装结构化 |
| `backend/app/cards/`（拟新增；参见现有规格） | `schema`、布局/主题注册表、选择器、validator、compiler；注册表统一给模型版式摘要和 UI 选择器，避免 refs 手写第二份目录 |
| `backend/app/services/`（拟新增） | `card_composer`、`media_resolver`、`card_render`。复用 `adapters/image_gen.py`，并承担资产持久化、异步任务和截图；不用 DAG 的 `image_gen_node` |
| `backend/app/engine/harness/executor/loop.py:1524-1604` | 用 `result.card_draft` + `schema_version` 识别卡片产物并持久化/SSE，而非枚举技能名；异步生图用进度事件/任务状态，最终一次 revision 提交 |
| `frontend/src/components/chat/ChatCardDraft.vue:9-49` / `cardDraft.ts:11-52` | 优先读取新 `deck` 和 `renderedPages`；按 `page_id` 处理预览、换图/版式、保留原 HTML 分支；新类型由服务端 Schema/OpenAPI 生成，杜绝 `any[]` 放大协议漂移 |

**接口初案（需实现与评审）**：`POST /api/v1/cards/compose`（请求内容、用户素材 ID、风格/是否生图、候选数量）→ `{job_id}` 或短任务直接返回 Deck；`GET /api/v1/cards/{id}`；`PATCH /api/v1/cards/{id}/pages/{page_id}`（按 block/slot 的版本化补丁，冲突返回 409）；`GET /api/v1/cards/{id}/preview`；`POST /api/v1/cards/{id}/render`；`GET /api/v1/cards/catalog`。ReAct 工具调用 service，而不是在 ReAct 循环内手搓这些 HTTP 请求。会话 SSE 继续走 `draft_patch`，并添加 job 进度状态。发布只消费已通过质量门禁且版本号一致的成品 PNG/图组，不把 `htmlContent` 当发布资产。

## 4. 执行顺序与验收（按可交付的纵向切片，而不是先堆满 24 模板）

| 阶段 | 只做的事 | 必须通过的验收 |
|---|---|---|
| 0. 基线/止血 | 给 ReAct 卡片技能引用与工具目录做启动校验；建立 10-12 个真实创作请求的快照基线；标出旧 HTML 兼容路径 | 可复现 ReAct→SSE→iframe 的旧链路；缺失 refs/脚本被报告，目录里不出现不可调用工具 |
| 1. 结构化闭环 | 做 4-6 个**几何不同**的版式：纯排版封面、账本、步骤、左右图文、顶图、全图覆字；两套主题；上传图片；让 `compose_card_deck` 产出 Deck 并打通 ReAct SSE→聊天预览→同源 PNG | 同一篇文案产多种页面结构；图片进入指定 slot；文案可编辑；预览与 PNG 关键元素不漂移；无 DAG 依赖 |
| 2. 真正接生图 | 独立媒体资产服务 + provider/生成任务 + 额度/失败状态；单个 slot 可生图/换用户图/裁切，保存 provenance；失败降级 | 请求“封面生成实景图”能看到异步进度和结果；换图无需重写整张卡；失败不会伪装成功 |
| 3. 丰富组合与多方向 | 扩展到经过验收的 12-24 布局、密度变体、主题、拼贴；同内容产 2-3 个**结构明显不同**的方向，用户选方向后局部迭代 | 跨页骨架多样性由结构差异衡量；不是仅色值不同；回归样本无明显文字截断和图像失焦 |
| 4. 统一编辑与清退 | 将新编辑器接入工作详情，旧 `htmlContent` 保持只读预览；逐步清理旧空工作区与无效脚本；再评估是否推广给其他工作流 | 新旧作品均可打开；新作品能改块/换布局/换图；旧 HTML 不被错误地反解析为 DSL |

回归测试建议：纯文字知识卡、对比评测、探店多图、上传产品主图、明确要求生成插画、长标题/密集列表、缺图/配额不足、中文字体、离线导出、重复点击/并发修改。分别覆盖 schema 单测、组件截图 golden、媒体任务集成、ReAct 模拟工具调用→`draft_patch`→Vue 预览端到端。衡量 **布局结构差异率、素材命中率、图文合规率、局部修改成功率、导出/预览一致性、每套生图成本**，而非“模板总数”。

## 5. 对已有 `CARD_DSL_P1_SPEC.md` 的复核：建议先改这些再写代码

该文档是**规划，尚未落地**；`backend/app/cards/` 当前不存在。方向总体正确（`CARD_DSL_P1_SPEC.md:10-32,402-454`），但不宜机械照抄：

1. 文档 `:346-364` 的 `image_right_ledger` 需要 image slot，示例约束 `:299-303` 的 `allowed` 却没有 `image`，将导致“带图即校验失败”。需要区分 `blocks`（可见语义）与 `image_slots`（几何），明确一一对应和必填条件。
2. 示例的 `Page.id` 约束为 4-32 位（`:229-233`），错误示例 ID 用 `p3`（`:427-431`）。不要让 golden sample 与 Schema 相互矛盾。
3. `ImageSource.upload` 没有强制的上传资产引用，`ai_gen/asset` 才要求 prompt/query（`:54-83`）；`resolved_url` 属于解析态，不应和 LLM 写入态混为可修改字段。补 slot 状态、媒体来源、用户许可、尺寸/裁切与失败态。
4. 24 布局/14 主题是**终态候选库**，非首个可验证闭环的必须规模；`MAX_PAGES=18`、单一 1080×1440 与已有横版金句、竖版海报技能不完全兼容（`CARD_DSL_P1_SPEC.md:48-49`；`card-xiaohongshu.md:158-164`）。首版锁小红书 3:4，其他画幅走后续 profile 扩展。
5. 文档 `:412-414` 提议 `pages[].dsl` 兼容旧 `htmlContent`，应升级为**整个 Deck 的有版本单一事实源**，`htmlContent/png` 只是衍生缓存；旧作品标记 `legacy_html`，不要反向推断出不可验证的 block。
6. 文档 `:454` 的静态/像素审计值得保留，但配方规范内部阈值已不一致（`card-xiaohongshu.md:62` ≥75%；`card-recipes.md:76` ≥85%）。按版式类别设置可测试阈值，且“留白”应区分有意的图片/金句设计与欠填。

## 决策建议

**选“基于 ReAct 的结构化卡片能力”作为主线，而不是补 DAG、换 React 框架、堆 CSS 主题或让 LLM 继续手写 HTML。** 先做 4-6 个可用布局 + 用户图片 + 一条可用的生图 slot + 新旧兼容，证明从对话到可编辑成品图的闭环；之后再扩大到规划中的 24 版式。初始架构结论来自静态代码与官方竞品公开资料；第一阶段实现后仍需在部署实例与真实创作请求中做冒烟验证。

## 实施进展（2026-10-06 第五轮：参照 Easel 做「密度与版式治理」）

第四轮把并发安全（原子写入 + 跨进程锁）补齐后，我用真实链路渲了一套「contrast 单词打卡」卡片，再拿 Easel 的 `card_audit.py` 做客观审计——**5 张全部 FAIL**。这一轮就是围绕"为什么看起来廉价/单调"做可度量的治理。

### 先说根因（不是审美问题，是工程问题）

| # | 根因 | 证据 |
|---|---|---|
| 1 | **底部死空白**：`.deck-title{margin-top:auto}` 把页脚顶到画布底，正文与页脚之间留出 30%+ 画高的死带 | 对照实验：仅改这一处，最大空白带 64%→34% |
| 2 | **内容量不足**：LLM 一页只给 2-3 条，撑不满 3:4 画幅 | 4 带密度第 3 带（50-75%）普遍为 0.0 |
| 3 | **kicker 是硬编码装饰**：`'FIELD NOTES / '` 写死在渲染器里，与内容无关 | 与用户截图逐字对上 |
| 4 | **主题只有 2 种**：只换配色，字体/字重/字距/圆角全部不动，所以"换主题=换颜色" | `THEMES` 原为 `tuple[str,...]` |
| 5 | **没有密度判据**：改版式全靠肉眼，无法在生成时自纠 | 审计前 5/5 FAIL |

### 从 Easel 借鉴的机制（不是照搬模板）

Easel 的核心不是"多几个 CSS 模板"，而是 **设计系统（硬规则）+ 渲染后门禁（确定性审计）**。它的链路是「LLM 直写 HTML → 截图 → PNG 像素审计」，而我们项目是「结构化 Deck 契约 → 确定性编译 HTML」，所以**同样的门禁应做在 Deck 层、渲染前**——比 Easel 更早发现、且不需要截图。这是本项目架构下更优的落点。

落地的四项能力：

1. **`backend/app/cards/audit.py`（新建）**：Deck 层密度审计器。按中文 1 字宽 / 西文 0.55 字宽估算块高，纵切 1440px 为 4 条带，输出每页 `fill` / `bands` / `pass` / `problems` / `hint`。与 Easel 的 PNG 像素审计交叉验证过：两种独立方法都判定 `list_ledger` 最好、`content_text` 最差，说明审计可靠。
2. **`_fill_thin_pages()`（composer）**：确定性"欠填修正阶梯"——`content_text` 欠填且能拆出 ≥3 条就升级成 `list_ledger`；`end_cta` 欠填就用前面各页标题补「要点回顾」；`cover_display` 欠填就用后续各页标题补「本期导读」。注意后两条补的是**真实信息**（目录/回顾），不是装饰图形。
3. **THEMES 2→6**：`ink`(杂志编辑) / `warm`(暖卡纸) / `swiss`(瑞士极简) / `inkwash`(新中式墨韵) / `cream`(奶油温柔) / `terminal`(极客终端)。每种锁定字体族、kicker 等宽字体、标题字重、圆角与 6 个色位，由 `theme_css()` 编译成 CSS 变量（此前手写样式表总会与 spec 漂移）。新增 `CardDeck.kicker` 承载真实分类语义。
4. **渲染器修死空白**：删除 `margin-top:auto`，页脚改绝对定位钉底；`.content` 用 `flex-start` + `.rows{space-around}` / `.compare{flex:1}` 让清单与对比表自适应铺开。

### 「补内容」闭环：欠填修正阶梯的最后一阶

前三阶都是确定性的、不新增内容（换骨架 → 挂真实目录/回顾 → 让块按比例铺开）。我先把这三阶做完再审计，得到 **2/5 PASS**，剩下 3 张 FAIL 于"中段空白 16-20%"。

这里有个必须点破的发现：**拉伸盒子不等于增加内容**。把清单行改成 `flex:1` 后，行盒子确实铺满了整个区域，但每行仍只有中间一条细字——像素审计照样 FAIL。密度是"墨水量"，不是"盒子高度"。

所以第四阶必须是真的补内容：`_repair_plan()` 把审计结果（`第几节 / 填充率 / 缺多少 px / 缺在哪`）回灌给模型，让它扩写欠填章节。三条硬约束：

1. 只扩写欠填章节，其余原样返回；
2. 补完必须**真的变多**（按字符体量比对），否则视为模型只是把原话换个说法 → **拒绝采纳**；
3. prompt 明确禁止编造事实——密度不够的正解是把原文已有的信息写足，不是注水。

采用前还要复检：只有 `min_fill` 真的变大才替换成稿，避免"看起来改过"反而更差。

### before / after（Easel `card_audit.py` 客观量化）

| 卡片 | 最大空白带（前 → 后） | 判定 |
|---|---|---|
| card_01 封面 | 47% → **13%** | FAIL → **PASS** |
| card_02 | 62% → **10%** | FAIL → **PASS** |
| card_03 | 24% → **10%** | FAIL → **PASS** |
| card_04 | 20% → **12%** | FAIL → **PASS** |
| card_05 | 56% → **11%** | FAIL → **PASS** |

合计 **0/5 PASS → 5/5 PASS**，底部死空白统一降到 6%，纵向跨度 88%（判定口径：内容覆盖 ≥75% 画高、任何无理由空白带 >15% 即失败）。

对照实验（同一份欠填输入，模型第二轮不扩写 vs 扩写）：整副最低填充率 **0.197 → 0.717**，欠填页数 **4 → 2**（且剩下的 2 张是 0.717/0.719 贴着 0.75 线，走完补内容闭环后也全部达标）。

---

## 实施进展（2026-10-05）

已在 ReAct 主线落地第一条结构化卡片切片：

- 新增 `backend/app/cards/schema.py`、`composer.py`、`renderer.py`、`operations.py`、`export.py`：CardDeck/Page/Block 数据契约、语义拆页、9 种不同几何版式、两种主题、确定性 HTML 编译、拥有者素材检查、块级改文/换图及 Chromium PNG 渲染。
- 新增 `compose_card_deck` 与 `generate_card_image` ReAct skills 并注册进 `image_text.produce`；生图工具有用户确认治理，结果写入用户资产库。**未进行真实 Wanx 请求**，需 DashScope key 与用户确认。
- `LoopExecutor` 通过 `schema_version + deck` 契约持久化 `CreativeArtifact`，记录 owner、session 与 revision，并通过现有 `draft_patch` 推送 Vue；结构化 Deck 是事实源，HTML 只是预览编译结果。
- `creative-artifacts` API 已增加 owner-scoped 卡片 draft GET/PATCH、PNG ZIP 导出；共享的旧 artifact GET/PATCH/DELETE/列表接口也增加所有权过滤。卡片编辑按版本号冲突返回 409，图片引用必须归属当前用户。
- Vue 对话卡片已提供快速编辑标题/正文/CTA、换个人图片、下载 PNG 压缩包；生成后的卡片更新同时写回聊天 creative_state。
- 第二轮补齐逐项编辑与版式/主题切换：`PATCH /card-draft` 改为显式 `op`（`set_text`/`set_image`/`set_item`/`add_item`/`remove_item`/`set_cell`/`add_row`/`remove_row`/`set_title`/`set_layout`/`set_theme`），省略 `op` 时按旧字段推断以兼容旧调用；`schema.py` 引入块位归一化（`list` 与 `steps` 渲染同构，并入同一 `items` 槽位），并新增 `compatible_layouts()` 把当前页合法版式随 `availableLayouts` 下发，前端只展示可选项，非法目标返回 422。

### 本轮验证

- `backend/tests/test_react_structured_cards.py`：19 passed（修正两个 mock 缺少 `artifact_id` 字段的问题，并补一条 artifact_id 不一致应判为不存在的断言；后续新增逐项编辑、对比表编辑、版式切换、主题切换、方向切换（含"有图片时 visual 才可用"、"切完的方向不再出现在候选"）、版本与类型校验、`EDIT_OPS` 与 Literal 一致性共 9 组用例）。
- `backend/tests/test_e2e_card_draft_render.py`：12 passed。修复了三处陈旧用法——`ReActLoop` 早已重命名为 `LoopExecutor`、SSE 总线改为函数内懒加载（patch 目标应为 `app.services.sse_bus.sse_bus`）、脚本化假 LLM 的 `chat()` 不接受 `max_tokens`。这三处恰好覆盖 `_persist_creative_state → draft_patch` 的推送契约，是本轮改动的直接回归点。
- `backend/tests/test_llm_drives_image_text_skill.py`：全通过（同样补齐假 LLM 的 `**kwargs`）。
- Python 修改文件 `py_compile`：通过。
- Vue `vue-tsc -b frontend/tsconfig.json`：通过。
- Vite production build：通过（2160 modules）。
- 本地 bundled Chromium 实际导出 3 张 PNG；均以有效 PNG 签名 `89504e470d0a1a0a` 开始。
- TestClient 端到端：`create=200`、`read=200(version 1)`、他人读取 `404`、过期版本 PATCH `409`、合法 PATCH `200(version 2)`、export `200` 且 ZIP 以 `PK` 开头。
- 第二轮 TestClient 端到端：清单页 `availableLayouts = ['list_ledger','steps_flow']`；`set_layout steps_flow = 200`、`set_layout compare_split = 422`、`set_item/set_cell/set_theme = 200`、过期版本 `409`、越界索引 `422`、切换版式并换主题后 export `200` 且 ZIP 有效。
- Vue `vue-tsc -b` 与生产构建在第二轮改动后重新验证：均通过（构建因沙箱批量删除保护不能直接清空 `frontend/dist`，改为输出到临时目录验证，产物正常）。
- 第三轮 TestClient 端到端：`availableDirections = ['editorial','ledger','flow']`（无图片素材时 `visual` 不出现）；`set_direction flow = 200`，版式由 `['cover_display','list_ledger','steps_flow','compare_split','end_cta']` 变为 `['cover_display','steps_flow','steps_flow','compare_split','end_cta']`；重复切同一方向 `422`、未知方向 `422`、切回 `ledger` `200`、导出 `200` 且 ZIP 有效。
- `backend/tests/test_react_structured_cards.py`：19 passed。

### 全量测试现状（2026-10-06 复核，第六轮）

`pytest backend/tests --ignore=tests/test_image_plan_planner.py`：**21 failed**（另有 ERROR 由沙箱的批量删除保护触发）。`test_image_plan_planner.py` 因 `app.templates` 不存在而无法导入——属既有漂移。

失败项全部位于卡片改动未触及的模块，逐条核对后确认**零新增回归**：

| 失败组 | 数量 | 直接原因 | 是否卡片改动引入 |
|---|---|---|---|
| `test_chat_agent`、`test_chat_profile_injection` | 8 | `_FakeRegistry.build_harness()` 不接受 `creation_type` | 否 |
| `test_clarification_phase4/5/6` | 3-5 | 澄清标签 flush、clarify meta schema、loop state 时间戳断言 | 否 |
| `test_codex_api`、`test_codex_boundary` | 4 | 路由数量 13≠14；`GraphEdge`、`refresh_node_func_map` 已移除（DAG 路径） | 否 |
| `test_loop_executor_smoke` | 2 | `LoopExecutor` 缺少 `_detect_required_tools`；技能路由返回空集合 | 否，`git diff loop.py` 仅 18 行且集中在卡片持久化 |
| `test_model_router_llm_protocol` | 1 | 流式聚合返回 11 个 chunk | 否，与卡片无关的模型路由漂移 |
| `test_observer_bridge` | 1 | SSE 桥接断言 | 否 |
| `test_profile_injection` | 2 | `app.tools.audit_skill` 模块不存在 | 否 |

**关于 ERROR 的说明**：全量跑时 `test_artifact_store_safety`、`test_primitives`、`test_sandbox`、`test_codex_integration` 会出现 `ERROR at setup`，原因是沙箱的批量删除保护（清理 `tmp_path` 时一次删 75 个文件超过阈值 50）注入 `SystemExit`，打断了 pytest-asyncio 的 setup。这是**运行环境现象，不是代码缺陷**——单独跑这些文件全部通过。

卡片相关测试：`test_react_structured_cards` + `test_e2e_card_draft_render` + `test_artifact_store_safety` + `test_llm_drives_image_text_skill` = **61 passed**（第六轮新增 3 个 P0 用例：`test_items_carry_a_note_and_a_right_hand_tag`、`test_compare_rows_can_carry_a_dimension_label`、`test_legacy_plain_string_items_and_two_tuples_still_load`）。

### 仍未完成 / 风险

- Wanx 真实生图、线上 ReAct→SSE→页面的端到端运行尚未验证；目前确认工具注册、API 路由、单测与浏览器导出。
- 第三轮补齐几何方向候选：`DIRECTIONS` 声明每页版式偏好顺序（`editorial` 文字优先 / `ledger` 清单账本 / `flow` 步骤流程 / `visual` 图像主导），`apply_direction()` 逐页过 `compatible_layouts` 落版式，`available_directions()` 只返回真会改变版式的方向。选择"按需计算 + 切换"而非"一次生成 3 套 Deck 存储"，省掉方向变体的存储与版本管理。
- 逐项编辑已覆盖清单项、步骤项与对比表的单元格/行/列名。版式切换与方向切换的候选范围仍受版式契约限制——`compare_split`、`end_cta`、`image_right_ledger` 等需要独占组件的版式在缺少对应组件时不会出现在候选里；要让"换骨架"的选择更多，需让这些版式接受可选组件并让渲染器处理，尚未做。方向定义里刻意不放通用兜底，避免"图像主导"在没有图片时退化成清单版式。图片裁切/焦点仍未实现。
- PNG 导出当前是 ZIP 下载；没有真实用户图片的浏览器回归；缺字/特定字体的像素级 golden test 未覆盖。
- ~~artifact 存储仍为 JSON 文件，读-改-写尚未跨多进程原子化~~ **第四轮已解决**：`save_artifact` 改为临时文件 + `os.replace` 原子替换，并新增跨进程文件锁（`msvcrt.locking` / `fcntl.flock`，非阻塞 + asyncio 退让，5s 超时抛错而非死锁）；`apply_card_edit` 的整条读-改-写包进锁内，否则两个并发编辑会各自读到同一 version、都通过乐观校验、后写的静默覆盖前一次。新增 `tests/test_artifact_store_safety.py` 5 个用例直接验证（含 `asyncio.gather` 两个同版本编辑必须恰好 1 成功 1 失败）。生产多 worker 部署前仍建议迁移到数据库事务。
- 前端尚未消费本轮新增的三个能力：`themeOptions`（6 种主题选择器）、`kicker` 字段、每页 `density` 诊断提示。
- 「补内容」闭环目前只在欠填时触发一次；若模型连续两轮都补不够，成稿会带着欠填页交付（此时每页 `density.hint` 会给出具体缺口，前端可选择提示用户补素材）。是否要再叠一轮、或降级为"少出几页"，需要真实流量下看命中率再定。
- 工作树原有大量未提交改动与删除项，本轮仅围绕 ReAct 卡片、相邻前端类型和测试修改，未清理或回滚既有内容。

---

## 实施进展（2026-10-06 第六轮：P0 — 给 list/steps/compare 加副行字段）

第五轮做密度治理时撞到一根钉子：清单行 `items: list[str]` 只能装一个字符串，模型要写满 3:4 画幅就只剩两条路——要么硬塞 6 条光秃短语，要么让一条细字悬在 200px 高的行盒子中央（像素审计照样 FAIL）。Easel `card-recipes.md` 的最小密度线写的是「账本行 ≥4 行带副行」——本质同一件事的另一份命名：**副行（note）是清单条目的第二层信息载体，是密度的杠杆**。

所以本轮选 P0「加副行字段」而不是"再加 4 种版式"：补的是数据模型的承载能力（让模型写出「主行 + 副行 + 右侧标签」），不动骨架体系。

### 改动 5 个文件 + 1 个测试文件

- `backend/app/cards/schema.py`：新增 `Item`（`text` / `note` / `tag`，max 90/120/16）与 `CompareRow`（`label` / `left` / `right`，max 30/85/85）；`model_validator(mode="before")` 把旧 `str` 归一化为 `{"text":...}`、把二元组归一化为 `{left,right}`、把三元组归一化为 `{label,left,right}`——**历史 Deck 自动可读**。
- `backend/app/cards/renderer.py`：`_list()` 重写为「序号 + 主行 + 灰色副行 + 右侧等宽标签」；CSS 增加 `.rows .main/.line/.note/.tag`；`.compare` 改 `grid-auto-rows:1fr` 并新增 `.compare.labeled`（三列：第一列 mono 维度标签 + 左右两列），删除过时的 `.compare h2/.compare .item`。
- `backend/app/cards/audit.py`：`_ledger_row()` / `_compare_row()` 按新模型估高；密度判据不变。
- `backend/app/cards/composer.py`：`Section` 用新模型；新增 `_trim_item()` / `_trim_row()` / `_main_texts()`；`_plan()` prompt 教模型把"为什么 / 怎么用"写进 `note`、把词性 / 年份 / 难度写进 `tag`。
- `backend/app/cards/operations.py`：`CardEdit` 新增 `note`/`tag` 字段（`None` = 不改）；`set_item` 合并语义；`add_row` 的 `value` 若给出则作为行标签。

### 量化收益（Easel `card_audit.py`，同一份清单页 4 条要点）

| 度量 | P0 前（裸字符串 ×4） | P0 后（带副行 + 标签 ×4） |
|---|---|---|
| 4 带密度合计 | 0.66 | **1.06**（+60% 墨水量） |
| 最大空白带 | 14% | **11%** |

> 关键不是 PASS → PASS，而是「同样 4 条要点，加了副行后墨水量 +60%、最大空白带 -21%」。这正是 Easel `card-recipes.md` 把「≥4 行带副行」作为最小密度线的原因。

### 剩余 & 风险

- 前端尚未消费本轮新增的 `note` / `tag` 编辑与对比表行标签。
- P1-P3 组件扩充（矩阵 `bento_grid`、数据卡 `stat`、金句卡 `quote`、时间线 `timeline`、1:1 画幅逃生阀）需与用户对齐后分批做。
- 工作树仍有大量既有未提交改动与漂移，本轮未触碰、不擅自清理。

---

## 实施进展（2026-10-06 第七轮：P1 — 矩阵 `bento_grid` + 单数据卡 `stat`）

P0 补完了「清单条目一行」的杠杆。下一根钉子是 Easel 9 卡型骨架里我们还缺两种——**D 矩阵 Bento**（并置多组数据）和**单数据卡 data**（巨数 + kicker + 来源），它们是科研/产品/数据报告类内容的标配骨架，缺了意味着同样的「6 个 KPI」只能塞清单页（密度看起来不够「设计感」）或单张大数字页（巨数下方永远有真空）。

### 数据模型（同 P0 的杠杆思路）

两个新块共享一份"格子"模型 `Cell`：kicker 顶分类 / big 主数字 / unit 单位 / note 解读 / source 来源，对应 Easel `card-recipes.md` 对数据卡规定的五层结构。BentoGrid 装 2–6 格 Cell，Stat 装 1 格 Cell。

### 改动 5 个文件 + 1 个测试文件

- `backend/app/cards/schema.py`：新增 `Cell` / `BentoGrid` / `Stat`；Block Union 扩入；`LAYOUTS` 加 `"bento_grid"` 与 `"stat_card"` 两条。
- `backend/app/cards/renderer.py`：共享 `_cell(cell, kind)` 渲染五层；CSS `.bento` 用 `grid-template-columns:repeat(3,1fr) + grid-auto-rows:1fr + flex:1 + align-content:end` 把 grid 撑到 content 底部，cell 内 `::before` 发丝线在 big 与 note 之间作视觉锚（治 cell 被拉高后的中段空洞）；CSS `.stat` 用 `flex:1 + justify-content:space-between + flex-direction:column` 把 kicker/big-line/note/source 四段均匀铺到顶/中/底，big 字号 280–340px 撑视觉重量。
- `backend/app/cards/audit.py`：`MIN_DENSITY` 加 bento_grid / stat_card 两条；`block_height` 对 BentoGrid 取固定 940px（实测 `grid-auto-rows:1fr + flex:1` 把 grid 撑到 .content 等高，2/4/6 格都 ≈938px），Stat 取 1100px。
- `backend/app/cards/composer.py`：`Section.kind` 加 bento/stat；新增 `cells: list[Cell]`；`_build_deck()` 新增两条分支；`_plan()` prompt 教模型把每格写满五层，bento 至少 4 格、stat 必须给 source。
- `backend/app/cards/operations.py`：`EDIT_OPS` 加 `set_bento_cell` / `set_stat_value`；`CardEdit` 加 `kicker`(20)/`unit`(16)/`source`(40) 字段（沿用 `None`=不改 / 给空串=清空语义）。

### 量化收益（Easel `card_audit.py`，同一份 6 格 KPI 矩阵与一条 stat）

| 骨架 | 度量 | P1 前 | P1 后 |
|---|---|---|---|
| BentoGrid 6 格 | 4 带密度合计 | 1.03 | **1.38**（+34% 墨水量） |
| BentoGrid 6 格 | 最大空白带 | 23% ❌ FAIL | **8% ✅ PASS** |
| Stat 单数据卡 | 4 带密度合计 | 0.89 | **1.43**（+61% 墨水量） |
| Stat 单数据卡 | 最大空白带 | 29% ❌ FAIL | **11% ✅ PASS** |

两组都通过 Easel 像素审计门禁（最大空白带 ≤15%、底部带非空）。视觉：bento 6 格密集分布，每格五层信息完整且视觉对齐；stat 是呼吸型骨架（layout-laws 第 30 行许可 ≤60% 覆盖），kicker / 巨数 200% / 多行解读 / 来源四段被 space-between 推到顶/中/底，视觉上是"被刻意安排的留白"而非廉价空洞。

### CSS 迭代史（备忘，下次类似骨架可复用）

```
bento:  v1 grid-auto-rows:1fr cells 中段空 → max_gap=16% ❌
       v2 grid-auto-rows:auto cells 自然高 → grid 缩成 ~580px, footer 上方 360px 死空 → max_gap=23% ❌
       v3 grid-auto-rows:1fr + align-content:end + cell 内 ::before 发丝线 → max_gap=8% ✅

stat :  v1 justify-content:flex-start 中段死空 → max_gap=33% ❌
       v2 note{margin-top:120px} → 29% ❌
       v3 big 220px + unit 同行 → 25% ❌
       v4 space-between + big 280px → 18% ❌
       v5 去掉 note margin-top:auto + big 340px → 11% ✅
```

### 验证

- 卡片四件套：`test_react_structured_cards` + `test_e2e_card_draft_render` + `test_artifact_store_safety` + `test_llm_drives_image_text_skill` = **70 passed**（含 4 个 P1 新用例）。
- 全量回归：`pytest backend/tests --ignore=tests/test_image_plan_planner.py --basetemp=D:/tmp/pbt-p1` = **29 failed**（vs P0 基线 21 failed，多 8 个全部来自 venv 重装后从 `ERROR` 暴露为 `FAILED` 的 chat_agent / chat_profile_injection / workflow_pause 测试），**零卡片相关失败、零新增回归**。

### 剩余

- 前端未消费 bento 格子编辑 + stat 五层编辑。
- P2：金句卡 `quote`（layout-laws 已明确允许 ≤60% 覆盖，必须补三个锚点：顶 kicker/日期 + 底出处行 + 其上一条发丝线——stat 已满足，可直接复用）+ 时间线 `timeline`。
- 真实 Wanx 生图 + 在线 ReAct→SSE→浏览器全链路冒烟仍未做。

### P2 第八轮：金句 quote + 时间线 timeline（2026-10-06）

补完 Easel 9 卡型骨架里缺的最后两种：`quote`（呼吸型骨架）与 `timeline`（时间锚点序列）。仍只动 ReAct 对话链路。

- 新增 `TimelineItem`（date/text/note）+ `Timeline`（3–8 条）、`Quote`（kicker/text/author）；`LAYOUTS` 加 `timeline_flow`（带标题）与 `quote_callout`（无标题——标题由块内 kicker 承担）。
- 两个集成 bug 已修：`renderer` 对 `quote_callout` 取 heading 会 `KeyError`（改为 `.get`）；`composer` 进 quote 分支前已 prepend 的 `Heading` 必须从 blocks 移除，否则 `validate_layout` 报"含有不允许的组件"。
- 金句是唯一允许较空的呼吸型骨架，但 Easel `card_audit.py` 并不豁免 `DEAD_BAND_MAX=0.15`——所以正文必须大字号（**92px**）才能把中段死空白压到 ≤15%。实测 64px 短金句中段 25% FAIL，92px + 70 字金句中段 **9% PASS**。三个锚点（顶 kicker / 底 author / 上下发丝线）让留白读作刻意呼吸而非欠填。
- 编辑：`set_timeline_item` / `add_timeline_item`（上限 8）/ `remove_timeline_item`（下限 3）/ `set_quote`，复用既有 value/note/tag 字段语义做合并编辑。
- 验证：timeline 与 quote 都通过 Easel 像素审计（最大空白带 14% / 9%）；卡片四件套 **74 passed**（含 4 个 P2 新用例）；全量回归 29 failed（与 P1 基线一致，零卡片相关、零新增回归）。

> 9 卡型已齐（cover / content / list / steps / compare / bento / stat / timeline / quote）。下一步是前端适配 `ChatCardDraft.vue` 消费 timeline/quote 编辑，以及补齐 P3（1:1 画幅逃生阀）。
