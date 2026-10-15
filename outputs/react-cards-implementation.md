# ReAct 结构化卡片纵向切片实施记录

日期：2026-10-05（2026-10-06 第五轮增补：密度治理与主题系统；第六轮增补：P0 加副行字段；第七轮增补：P1 矩阵 + 单数据卡）
范围：后端 ReAct 对话链路与 Vue 卡片预览，不涉及 LangGraph/DAG、不改前端框架。

## 交付结果

把结构化卡片从模型协议接到会话预览、持久化、块级编辑与 PNG 导出：

```text
ReAct compose_card_deck
  → CardDeck JSON（Pydantic 校验）
  → 确定性 renderer 编译 HTML
  → CreativeArtifact（owner + session + version）
  → creative_state / draft_patch SSE
  → Vue iframe 预览
  → PATCH 单块文案/替换图片
  → Chromium 生成 PNG ZIP
```

旧版 HTML 卡片仍走既有预览分支；新卡片将 Deck 作为可编辑事实源，HTML 为派生预览。

## 后端实现

- `backend/app/cards/schema.py`：Deck/Page 与 Heading、Text、List、Steps、Compare、Image、CTA blocks；限定页面尺寸、页数、图片路径、版式必需组件及封面顺序。
- `backend/app/cards/composer.py`：从语义规划产生不同几何布局，包括 `cover_display`、`cover_top_image`、`content_text`、`list_ledger`、`steps_flow`、`compare_split`、`image_right_ledger`、`image_bg_overlay`、`end_cta`。
- `backend/app/cards/renderer.py`：结构化 Deck 确定性编译为 HTML；文本转义，不接受模型自由 CSS/HTML。
- `backend/app/cards/operations.py`：卡片 owner/session 权限、用户素材归属校验、期望版本校验、文字修改/换图，并回写 session 的 `_card_draft`。
- `backend/app/cards/export.py`：使用同一 renderer 和本地 Chromium 截图；导出前检查素材、图片加载及页面溢出。
- ReAct Skill `compose_card_deck` 和 `generate_card_image` 已注册到 `image_text.produce`。生图结果复用现有资产库，Guardian 要求用户确认。
- `CreativeArtifact` 保存 `card_deck` 与 `owner_user_id`；旧 artifact 按来源会话所有者兼容。通用读、写、删除、列表接口增加所属用户过滤。

新增/使用的 API：

- `GET /api/creative-artifacts/{artifact_id}/card-draft`：取当前用户卡片及版本。
- `PATCH /api/creative-artifacts/{artifact_id}/card-draft`：传 `expected_version`、页/块 ID 与新文字或新 `asset_id`；冲突返回 409，权限外对象隐藏为 404。
- `GET /api/creative-artifacts/{artifact_id}/export`：下载包含每页 PNG 的 ZIP。

## 块级编辑操作集

`PATCH /{artifact_id}/card-draft` 现在接受显式 `op`，一个请求只改一处，便于乐观并发与审计：

| op | 作用对象 | 参数 |
|---|---|---|
| `set_text` | heading / text / cta | `value` |
| `set_image` | image | `value` = 用户资产 ID |
| `set_item` / `add_item` / `remove_item` | list / steps 的条目 | `index`、`value` |
| `set_cell` / `add_row` / `remove_row` | compare 的单元格与行 | `index`、`column`、`value`、`value_pair` |
| `set_title` | compare 的左右列名 | `column`、`value` |
| `set_layout` | 整页版式 | `value` = 版式 ID |
| `set_direction` | 整副卡片的几何方向 | `value` = 方向 ID |
| `set_theme` | 整副卡片主题 | `value` ∈ `THEME_IDS` |

省略 `op` 时按旧字段 `new_text` / `new_asset_id` 推断，旧调用方不受影响。

## 第五轮：密度治理与主题系统

### Deck 层密度审计（`backend/app/cards/audit.py`，新建）

参照 Easel 的"渲染后 PNG 像素审计"思路，但落点前移到 **Deck 层、渲染前**——因为本项目是「结构化 Deck → 确定性编译 HTML」，在 Deck 上估高就能判密度，不需要截图，也就能在生成阶段自纠。

- 块高估算：`_cjk_len()` 按中文 1 字宽、西文 0.55 字宽折算；`block_height()` 按版式给出每类块的高度。
- 4 带密度：把 1440px 纵切成 4 条 360px 带，逐带看有没有内容。
- 判据：内容覆盖 ≥75% 画高；任何无理由空白带 >15% 画高即失败；底部带必须有实质内容。
- `MIN_DENSITY` 最小密度线：`list_ledger`/`image_right_ledger` ≥4 行、`steps_flow` ≥4 步、`compare_split` ≥5 行。
- 产物：`audit_page()` 返回 `fill`/`bands`/`pass`/`problems`/`hint`；`to_card_draft()` 每页带 `density`，前端可直接展示诊断。

与 Easel 的 PNG 审计做过交叉验证：两种完全独立的方法都判定 `list_ledger` 最好、`content_text` 最差，证明审计可信。

### 欠填自动修正（`composer._fill_thin_pages()`）

确定性阶梯，不新增 LLM 调用：

1. `content_text` 页欠填且能拆出 ≥3 条 → 升级为 `list_ledger`（`_split_to_items` 按 `\n；;。，,` 拆分，过滤 <4 字碎片）。
2. `end_cta` 页欠填 → 用前面各页 Heading 补「要点回顾」（≥3 条）。
3. `cover_display` 页欠填 → 用后续各页 Heading 补「本期导读」（≥3 条）。

后两条补的是**真实信息**（目录/回顾），不是装饰图形——这是 Easel "填满"法则里唯一正当的填法。对应地 `optional_blocks()` 放开：`cover_display` 与 `end_cta` 允许挂 `items`。

### 主题系统：THEMES 2→6

从 `tuple[str, ...]` 改为 `dict[str, dict[str, str]]`，每种风格锁定**字体族 + kicker 字体 + 标题字重 + 圆角 + 6 个色位**，由 `theme_css()` 编译成 CSS 变量（此前手写样式表总会与 spec 漂移）：

| theme_id | 风格 | 标题字重 | 特征 |
|---|---|---|---|
| `ink` | 杂志编辑 | 500 | 衬线标题 + 细分隔线 |
| `warm` | 暖卡纸 | 600 | 米黄底 + 圆角卡片 |
| `swiss` | 瑞士极简 | 400 | 强网格 + 无装饰 |
| `inkwash` | 新中式墨韵 | 500 | 低饱和墨色 |
| `cream` | 奶油温柔 | 600 | 高明度低对比 |
| `terminal` | 极客终端 | 700 | 等宽 + 单色描边 |

新增 `CardDeck.kicker` 承载真实分类语义（渲染进 `.kicker`，用等宽大写 + 字距），此前渲染器里硬编码的 `'FIELD NOTES / '` 已删除——它与内容无关，是"AI 味"的直接来源。

### 第四阶：审计回灌补内容（`composer._repair_plan()`）

**关键认知：拉伸盒子 ≠ 增加内容。** 把清单行改成 `flex:1` 后行盒子铺满了整个区域，但每行仍只有中间一条细字，像素审计照样 FAIL。密度是"墨水量"，不是"盒子高度"。所以确定性手段用尽后，必须真的补内容。

流程：构建 Deck → `_fill_thin_pages()` → `audit_deck()` → 有欠填页就把「第几节 / 填充率 / 缺多少 px / hint」回灌给模型扩写 → 用同一套规则重建 → 只有 `min_fill` 真的变大才采用。

三条硬约束：只扩写欠填章节；补完体量必须**真的变大**（否则视为复述，拒绝采纳）；prompt 明确禁止编造事实。`llm is None` 或补内容失败时静默沿用原稿，不影响主流程。

### 渲染器修死空白

- 删除 `.deck-title{margin-top:auto}`（头号元凶：把页脚顶到底，正文与页脚间留出 30%+ 死带），页脚改绝对定位钉底，`.card` padding-bottom 76→190 让位。
- `.content{flex:1; justify-content:flex-start}` + `.rows{space-around}` / `.compare{flex:1}`：让清单与对比表自适应铺开，而不是全部堆在顶部。

### 几何方向（多候选骨架）

方向不是"一次生成 3 套 Deck 存起来"，而是**按需计算**：`DIRECTIONS` 只声明每页版式的偏好顺序，应用时逐页过 `compatible_layouts` 筛选，落点永远是当前组件撑得起的版式，不需要额外存储。

| 方向 | 特征 |
|---|---|
| `editorial` 文字优先 | 有正文块的页面走段落版式，封面切小标题 |
| `ledger` 清单账本 | 条目页统一走 `list_ledger` |
| `flow` 步骤流程 | 条目页统一走 `steps_flow` |
| `visual` 图像主导 | 图片页走整版铺图的 `image_bg_overlay` |

`available_directions(deck)` 只返回**真的会改变版式**的方向，避免给用户一堆点了没反应的选项；没有图片时 `visual` 直接不出现。方向定义里不放通用兜底——否则"图像主导"在没有图片时会退化成清单版式，名不副实。

版式切换不靠"先改后校验"碰运气：`compatible_layouts(page)` 会把当前页组件集合合法的版式算出来，随 `card-draft` 的每页 `availableLayouts` 返回，前端只展示这些候选，非法目标返回 422。为了让切换真的有得选，`schema.py` 引入块位归一化——`list` 与 `steps` 渲染同构，归并为同一个 `items` 槽位，因此"清单账本"与"步骤流程"可以互换。

## Vue 交互

`ChatCardDraft.vue` 的编辑面板已扩展：

- 顶部一行四个下拉：组件、版式（只列 `availableLayouts`）、主题、几何方向（只列 `availableDirections`，点完复位成"换个骨架…"）；改动即时保存。主题下拉改为消费后端下发的 `themeOptions`（6 种主题全量可选，不再写死墨色/暖砂两种）。
- 标题/正文/CTA 用文本框，图片位用个人素材下拉。
- 清单项与步骤项逐条编辑，每条暴露 **要点 + 副行(note) + 右侧标签(tag)** 三层（修复了旧 `String(item)` 把对象渲染成 `[object Object]` 的缺陷），支持新增与删除；steps 最少保留 2 条、list 最少 1 条。
- 对比表可按单元格编辑，支持新增行、删除行、改左右列名。
- **矩阵 Bento（P1）**：格子选择器（多格时）+ 每格五层字段 `kicker/big/unit/note/source` 编辑，逐层部分写入（空字段不发送，避免被后端 `_text` 校验拒绝）。后端无增删格子的 op，故只支持改现有格子。
- **单数据卡 Stat（P1）**：同五层字段编辑，复用 `set_stat_value`。
- **时间线 Timeline（P2）**：每条暴露 `日期(date)/标题(text)/副行(note)` 三字段，前端映射为 `set_timeline_item` 的 `value=date`、`note=text`、`tag=note`；3–8 条，删除下限 3。
- **金句 Quote（P2）**：三锚点 `正文(text)/作者(author)/顶部标签(kicker)`，映射为 `set_quote` 的 `value=text`、`note=author`、`tag=kicker`。
- 每次保存都用服务端返回的新 `version` 替换本地草稿，并回写对话内的卡片预览。
- 字段映射妥协说明：后端 `operations.CardEdit` 复用 `value/note/tag/kicker/unit/source` 承载不同块型语义（如 timeline 的 `note` 实指 text），前端在 `runEdit` 调用处做显式字段映射，避免语义错乱。

## 验证

- `backend/tests/test_react_structured_cards.py`：**9 passed**，覆盖版式差异、HTML 转义、上传图片、越权素材拒绝、schema 拒绝、技能输出、owner 隔离、版本冲突及 ReAct artifact owner 持久化。
- `backend/tests/test_e2e_card_draft_render.py`：**12 passed**。该文件中的 3 个 `draft_patch` 用例引用了已重命名的 `ReActLoop`，且 patch 的 SSE 总线目标仍是模块级 `sse_bus`（实现早已改为函数内懒加载）；另有 2 个用例的脚本化假 LLM 不接受 `max_tokens`。一并修复后，本轮改动所依赖的 `_persist_creative_state → draft_patch` 契约重新获得回归覆盖。
- `backend/tests/test_llm_drives_image_text_skill.py`：全部通过（补齐假 LLM 的 `**kwargs`）。
- `backend/tests/test_artifact_store_safety.py`（新建）：**5 passed**。走真实文件系统（`monkeypatch` 把 `_STORE_DIR` 指向 `tmp_path`、`_LOCK_TIMEOUT` 调到 0.05），验证原子写入、写失败保留旧内容、文件锁互斥、锁超时抛错而非死锁、`asyncio.gather` 两个同版本编辑恰好 1 成功 1 失败且 version 只 +1。
- 卡片相关四个文件合计 **61 passed**（`test_react_structured_cards` + `test_e2e_card_draft_render` + `test_artifact_store_safety` + `test_llm_drives_image_text_skill`）。
- 后端全量 `pytest backend/tests`（2026-10-06 复核）：**23 failed**，全部位于卡片改动未触及的模块（`test_chat_agent`/`test_chat_profile_injection` 8、`test_clarification_phase4/5/6` 5、`test_codex_api`/`test_codex_boundary` 4、`test_loop_executor_smoke` 2、`test_model_router_llm_protocol` 1、`test_observer_bridge` 1、`test_profile_injection` 2），逐条核对后**零新增回归**。全量跑时 `test_artifact_store_safety`/`test_primitives`/`test_sandbox`/`test_codex_integration` 会出现 `ERROR at setup`，根因是沙箱批量删除保护清理 `tmp_path` 时注入 `SystemExit` 打断 pytest-asyncio setup——单独跑这些文件全部通过，属运行环境现象。`test_image_plan_planner.py` 因 `app.templates` 缺失无法导入。
- Easel `card_audit.py` 客观审计（5 张「contrast 单词打卡」）：**0/5 PASS → 2/5 PASS**，最大空白带 card_01 47%→16%、card_02 62%→19%、card_03 24%→10%、card_05 56%→11%，底部死空白统一降到 6%。
- TestClient 端到端：`create=200`、`read card-draft=200(version 1)`、他人读取 `404`、过期 `expected_version` PATCH `409`、合法 PATCH `200(version 2)`、export `200` 且 ZIP 以 `PK` 开头。
- 第二轮（逐项编辑与版式切换）TestClient 端到端，全部断言通过：清单页 `availableLayouts = ['list_ledger','steps_flow']`；`set_layout steps_flow = 200`、`set_layout compare_split = 422`、`set_item = 200`、`set_cell = 200`、`set_theme = 200`、过期版本 `409`、越界索引 `422`、切换版式并换主题后 `export = 200` 且 ZIP 以 `PK` 开头。
- Python `py_compile`：通过。
- Vue `vue-tsc -b frontend/tsconfig.json`：通过。此前对话状态类型/ES lib 中已有的类型错误已修正：补齐 `confirmation_expired`、对 skills 数据做数组校验，并以 reverse/find 替代不受 target 支持的 `findLast`。
- Vite production build：通过，2160 modules。
- 本地 Chromium 实测导出 3 张 PNG，PNG 文件签名校验通过。

## 未验证与生产注意事项

- 未调用真实 Wanx 生图；需配置 `DASHSCOPE_API_KEY` 且用户确认，避免产生未授权费用。
- 版式切换的可选范围受版式契约限制：`compare_split`、`end_cta`、`image_right_ledger` 这类需要独占组件的版式，在缺少对应组件时不会出现在候选里。要让"换骨架"的选择更多，需要让这些版式接受可选组件（例如允许正文或图片作为可选块），并让渲染器处理它们——目前尚未做。
- 未在运行中的服务中验证完整登录态 ReAct→SSE→浏览器 UI；当前已有单测、路由注册检查、类型检查、前端构建与本地截图验证。
- 暂无真实用户图片的浏览器导出回归及字体/像素 golden tests。
- ~~artifact 以 JSON 文件持久化，跨进程读-改-写非原子~~ 已解决：`save_artifact` 改为临时文件 + `os.replace` 原子替换；新增跨进程文件锁（Windows `msvcrt.locking` / POSIX `fcntl.flock`，非阻塞 + asyncio 退让），`apply_card_edit` 的整条读-改-写包进锁内。多 worker 部署前仍建议迁移到数据库事务。
- 前端已消费 `themeOptions`（6 种主题全量可选）；尚未消费每页 `density` 诊断做"这一页太空"的红色提示，也未在前端把 `kicker` 单页顶部标签显式呈现（由后端渲染器负责）。
- 剩余 3 张卡片 FAIL 于"中段空白带 16-20%"（阈值 15%），根因是**源内容量不足**而非布局 bug。下一步应把 `audit_deck()` 结果回灌 composer 触发二次补内容，不应继续调 CSS。
- 本轮不清理工作区原有的未提交修改与删除项。

---

## 2026-10-06 第六轮：P0 — 给 list/steps/compare 加副行字段（选用户已做）

### 为什么要做这一步（而不是直接扩骨架）

第五轮做"密度治理"时，反复撞到一根钉子：清单行 `items: list[str]` 只能装一个字符串，模型要写满 3:4 画幅就只剩两个选择——**要么硬塞 6 条光秃短语**，要么让中间一条细字挂在 200px 高的行盒子正中央（被像素审计照样判 FAIL）。Easel `card-recipes.md` 的最小密度线写的是"账本行 ≥4 行带副行"，这是同一个问题在另一份设计系统里的命名：**副行（note）是清单条目的第二层信息载体，是密度的杠杆**。

所以本轮选「P0 加副行字段」而不是"再加 4 种版式"：补的是数据模型的承载能力（让模型能写出「主行 + 副行 + 右侧标签」），不动骨架体系——风险最低，收益最大。

### 改动落点（5 个文件 + 1 个测试文件）

| 文件 | 改动 |
|---|---|
| `backend/app/cards/schema.py` | 新增 `Item` 与 `CompareRow` 模型；`ListBlock.items`、`Steps.items`、`Compare.rows` 改用新模型；`model_validator(mode="before")` 把旧 `str` 归一化成 `{"text":...}`、把二元组归一化为 `{left,right}`、把三元组归一化为 `{label,left,right}`——历史 Deck 自动可读 |
| `backend/app/cards/renderer.py` | `_list()` 重写为渲染「序号 + 主行 + 副行 + 右侧等宽标签」；CSS 增加 `.rows .main/.line/.note/.tag`；`.compare` 改 `grid-auto-rows:1fr` 并新增 `.compare.labeled`（三列：第一列 mono 维度标签 + 左右两列），删除过时的 `.compare h2/.compare .item`；`.image_right_ledger .rows .main` 字重降 6px 以给副行留高度 |
| `backend/app/cards/audit.py` | 新增 `_ledger_row(item, wrap, base)` / `_compare_row(row)`：副行字号小可多吃一行高度，但每行不会因此变形；`block_height` 按新模型估高，密度上限判定仍以 `MIN_DENSITY` / `FILL_MIN=0.75` 为准 |
| `backend/app/cards/composer.py` | `Section.items/rows` 用新模型；新增 `_trim_item()` / `_trim_row()` / `_main_texts()` 辅助；`_volume()` 与 `_split_to_items()` 重写；`_plan()` prompt 教模型把「为什么 / 怎么用」写进 `note`、把词性/年份/难度写进右侧 `tag` |
| `backend/app/cards/operations.py` | `CardEdit` 新增 `note`/`tag` 字段（`str \| None`，默认 `None` 表示"不改"）；`set_item` 合并语义（只给 note 时主行保留）；`add_item` / `set_cell` / `add_row` 用新模型；新增 `_optional_text()` 允许副行留空（清空语义） |
| `backend/tests/test_react_structured_cards.py` | 5 处旧断言适配新模型；新增 3 组用例：副行+标签的合并与清空、对比表行标签切到三列网格、旧 string/tuple 自动归一化 |

### 前后对照（Easel `card_audit.py`，同一份清单页）

| 度量 | P0 前（裸字符串 ×4） | P0 后（带副行 + 标签 ×4） |
|---|---|---|
| 4 带密度合计 | 0.66 | **1.06**（+60% 墨水量） |
| 最大空白带 | 14% | **11%** |
| 卡片判定 | PASS | PASS |

账本行 4 条带副行 vs 4 条裸字符串，墨水量上升 60%，最大空白带下降 21%——直接对上 Easel 的「≥4 行带副行」最小密度线。

### 真实 5 张卡（同一文案，P0 后的 plan）

| 卡 | P0 前最大空白带 | P0 后最大空白带 | 4 带密度合计 |
|---|---|---|---|
| card_01 封面 | 13% | 13% | 1.17 → 1.17（不变，封面没改） |
| card_02 | 10% | 10% | 0.87 → 0.87（不变，文本+清单） |
| card_03 词根清单 | 10% | **9%** | 0.85 → **1.44**（+69% 墨水） |
| card_04 对比表 | 12% | 10% | 0.78 → 0.76（差异在测量噪点内） |
| card_05 收尾 | 11% | 11% | 0.86 → 0.86（不变，CTA） |

清单页（card_03）才是 P0 的目标场景——同样 6 条词根家族，标签 + 副行把墨水量撑高了 70%。对比表（card_04）行标签列会稍微占用宽度，但读者从"两列词"升级成"一张有表头的表"，可读性 > 数值差异。

### 测试

- `tests/test_react_structured_cards.py` + `tests/test_e2e_card_draft_render.py` + `tests/test_llm_drives_image_text_skill.py` = **61 passed**（其中 `test_react_structured_cards` 含 3 个 P0 新用例）。
- 全量回归：`pytest backend/tests --ignore=tests/test_image_plan_planner.py`：**21 failed**，全部为与卡片无关的既有漂移（chat_agent / clarification / codex / loop_executor_smoke / model_router / observer_bridge / profile_injection），逐条核对后**零新增回归**。`test_image_plan_planner.py` 因 `app.templates` 缺失无法导入——属工作区既有漂移。

## 2026-10-06 第七轮：P1 — 矩阵 `bento_grid` + 单数据卡 `stat`（选用户已做）

### 决策依据

P0 解决了「清单条目只有一行」的杠杆问题。下一根钉子：Easel 9 卡型骨架里我们还缺两种——**D 矩阵 Bento**（并置多组数据）和**单数据卡 data**（巨数 + kicker + 来源）。这两类是科研/产品/数据报告类内容的标配骨架，缺少它们意味着同样的"6 个 KPI"，模型只能堆成清单页（密度看起来不够「设计感」）或者塞进单张大数字页（巨数下方永远有真空）。补上后，整套卡型从「清单 + 对比 + 步骤 + CTA」升级到「清单 + 对比 + 步骤 + 矩阵 + 单数据 + CTA」，覆盖到 Scikit 研究所／科技产品／数据报告三类高频品类。

### 数据模型（同 P0 的杠杆思路）

两个新块共享同一份"格子"模型——`Cell`：kicker 顶分类 / big 主数字 / unit 单位 / note 解读 / source 来源，对应 Easel `card-recipes.md` 对数据卡规定的五层结构。BentoGrid 装 2–6 格 Cell；Stat 装 1 格 Cell。

```python
class Cell(BaseModel):
    kicker: str = Field(default="", max_length=20)
    big:    str = Field(default="", max_length=24)
    unit:   str = Field(default="", max_length=16)
    note:   str = Field(default="", max_length=80)
    source: str = Field(default="", max_length=40)
    @model_validator(mode="after")
    def _require_content(self) -> Cell:
        if not (self.big or self.kicker or self.note):
            raise ValueError("格子不能为空（至少给 big / kicker / note 其中之一）")
        return self

class BentoGrid(BaseModel):
    id: str; type: Literal["bento_grid"] = "bento_grid"
    cells: list[Cell] = Field(min_length=2, max_length=6)

class Stat(BaseModel):
    id: str; type: Literal["stat"] = "stat"
    cell: Cell
```

### 改动清单

| 文件 | 关键改动 |
|---|---|
| `backend/app/cards/schema.py` | 新增 `Cell` / `BentoGrid` / `Stat`；`Block` Union 扩入；`LAYOUTS` 新增 `"bento_grid": ("heading", "bento_grid")` 与 `"stat_card": ("heading", "stat")` |
| `backend/app/cards/renderer.py` | 共享渲染 `_cell(cell, kind)` 把五层堆叠（bento 时包 `<div class="cell">`）；CSS `.bento` 用 `grid-template-columns:repeat(3,1fr) + grid-auto-rows:1fr + flex:1 + align-content:end` 把 grid 撑到 content 底部，cell 内 `::before` 发丝线在 big 与 note 之间作视觉锚（治 cell 被拉高后的中段空洞）；CSS `.stat` 用 `flex:1 + justify-content:space-between + flex-direction:column` 把 kicker/big-line/note/source 四段均匀铺到顶/中/底，big 字号 280–340px 撑出视觉重量；`render_page()` 新增 `bento_grid` / `stat_card` 两条分支 |
| `backend/app/cards/audit.py` | `MIN_DENSITY` 新增 `"bento_grid": ("格子", 4)` 与 `"stat_card": ("数据卡", 1)`；`block_height` 对 BentoGrid 取固定 940px（实测 `grid-auto-rows:1fr + flex:1` 把 grid 撑到 .content 等高，2/4/6 格都在 938px 附近），Stat 取 1100px；`_count_of` 与 `_hint_for` 各加 bento/stat 提示 |
| `backend/app/cards/composer.py` | `Section.kind` 枚举加 `"bento"` / `"stat"`；新增 `cells: list[Cell]` 字段；`_trim_cell()` 把五层字段统一限制到上限；`_build_deck()` 新增两条分支（bento 走 `bento_grid` 版式，stat 走 `stat_card` 版式）；`_plan()` prompt 教模型把每格写满五层，bento 至少 4 格，stat 至少 1 格且必须给 source |
| `backend/app/cards/operations.py` | `EDIT_OPS` 加 `"set_bento_cell"` 与 `"set_stat_value"`；`CardEdit` 加 `kicker`(20)/`unit`(16)/`source`(40) 可选字段（沿用 `None` = 不改 / 给空串 = 清空语义）；两个 op 的 handler 都按"给哪个字段改哪个"合并，bento 禁止误用 `tag`（提示请用 `kicker`） |
| `backend/tests/test_react_structured_cards.py` | 导入补 `audit_page` / `render_page`；新增 4 个 P1 用例：bento 6 格五层信息完整、stat 五层信息完整、bento 最小密度线 ≥4 格、bento/stat 的 5 字段合并编辑 |

### 量化收益（Easel `card_audit.py`，同一份 6 格 KPI 矩阵）

| 度量 | P1 前（3 行 ×300px cells，big 64px） | P1 后（3×2 grid，big 96px，发丝线锚） |
|---|---|---|
| 4 带密度合计 | 1.03 | **1.38（+34% 墨水量）** |
| 最大空白带 | 23% ❌ FAIL | **8% ✅ PASS** |
| 纵向跨度 | 7% ❌ FAIL | 88% ✅ PASS |

| 度量 | P1 前（stat big 184px） | P1 后（stat big 340px，space-between 三段） |
|---|---|---|
| 4 带密度合计 | 0.89 | **1.43（+61% 墨水量）** |
| 最大空白带 | 29% ❌ FAIL | **11% ✅ PASS** |
| 纵向跨度 | 33% ❌ FAIL | 88% ✅ PASS |

两组都通过 Easel 像素审计门禁（最大空白带 ≤15%、底部带非空）。视觉效果：bento 是 6 格紧密矩阵，每格内 kicker（蓝灰 mono 大写）+ 大数字 + 单位 + 发丝线 + 解读 + 来源，五层信息完整且视觉对齐；stat 是呼吸型骨架（layout-laws 第 30 行许可 ≤60% 覆盖），kicker / 巨数 200% / 多行解读 / 来源四段被 `space-between` 推到顶/中/底，视觉上是"被刻意安排的留白"而非廉价空洞。

### CSS 迭代史（备忘，下次类似骨架可复用）

```
bento:  v1 grid-auto-rows:1fr cells 中段空 → max_gap=16% ❌
       v2 grid-auto-rows:auto cells 自然高 → grid 缩成 ~580px,footer 上方 360px 死空 → max_gap=23% ❌
       v3 grid-auto-rows:1fr + align-content:end + cell 内 ::before 发丝线 → max_gap=8% ✅

stat :  v1 justify-content:flex-start 中段死空 → max_gap=33% ❌
       v2 note{margin-top:120px} → 29% ❌
       v3 big 220px + unit 同行 → 25% ❌
       v4 space-between + big 280px → 18% ❌
       v5 去掉 note margin-top:auto + big 340px → 11% ✅
```

### 测试

- 卡片四件套：`tests/test_react_structured_cards.py` + `tests/test_e2e_card_draft_render.py` + `tests/test_artifact_store_safety.py` + `tests/test_llm_drives_image_text_skill.py` = **70 passed**（含 4 个 P1 新用例）。
- 全量回归：`pytest backend/tests --ignore=tests/test_image_plan_planner.py --basetemp=D:/tmp/pbt-p1` = **29 failed**（vs P0 基线 21 failed，多 8 个全部来自 venv 重装后从 `ERROR` 暴露为 `FAILED` 的 chat_agent / chat_profile_injection / workflow_pause 测试），**零卡片相关失败、零新增回归**。

### 下一步

- **P2**：金句卡 `quote`（layout-laws 已明确允许 ≤60% 覆盖，必须补三个锚点：顶 kicker/日期 + 底出处行 + 其上一条发丝线——stat 已满足，可直接复用）+ 时间线 `timeline`。
- **前端适配**：`ChatCardDraft.vue` 消费 bento 格子编辑 + stat 五层编辑 —— **已完成（2026-10-06 第九轮，见下）**。
- **真实 Wanx 生图 + 在线 ReAct→SSE→浏览器全链路冒烟**仍未做。

## P2 第八轮：金句 quote + 时间线 timeline（2026-10-06）

范围：后端 ReAct 对话链路。补完 Easel 9 卡型骨架里缺的最后两种——`quote`（呼吸型骨架）与 `timeline`（时间锚点序列），与 P0/P1 同一条结构化契约接上。

### 数据模型

```python
class TimelineItem(BaseModel):
    date: str = Field(default="", max_length=20)   # mono 时间戳
    text: str = Field(default="", max_length=90)   # 标题
    note: str = Field(default="", max_length=120)  # 背景说明

class Timeline(BaseModel):
    id: str; type: Literal["timeline"] = "timeline"
    items: list[TimelineItem] = Field(min_length=3, max_length=8)

class Quote(BaseModel):
    id: str; type: Literal["quote"] = "quote"
    text: str = Field(min_length=1, max_length=120)
    author: str = Field(default="", max_length=40)
    kicker: str = Field(default="", max_length=30)
```

`Block` Union 扩入 `Timeline` / `Quote`；`LAYOUTS` 新增 `"timeline_flow": ("heading", "timeline")`（带标题）与 `"quote_callout": ("quote",)`（**无标题**——金句页标题由块内 kicker 承担）。

### 关键修复（两个集成 bug）

- `renderer.render_page()` 开头 `heading = by_type["heading"]` 对 `quote_callout`（LAYOUTS 无 heading）会 `KeyError`。改为 `heading = by_type.get("heading")` + `isinstance` 判定，金句页 `title` 降级为空。
- `composer._build_deck()` 每个 section 先 `blocks=[Heading(...)]`，进 quote 分支时要把这个 Heading 清掉（`[b for b in blocks if not isinstance(b, Heading)]`），否则 `CardPage.validate_layout()` 报"版式 quote_callout 含有不允许的组件"。
- 附带：`to_card_draft()` 的 `next(block.text for block in page.blocks if isinstance(block, Heading))` 对无 heading 的 quote 页会 `StopIteration`，改为带默认值的 `next(..., "")`。

### 渲染与密度（呼吸型骨架的特殊处理）

- **timeline**：`.timeline` 用 `flex:1 + justify-content:space-around`，date(24px mono) 在左、text(36px)+note(24px muted) 在右，上下发丝线分隔。3–8 条均匀铺满内容区，所以 `block_height` 取常数 **1080**（实测 flex:1 吃满 heading 以下）。最小密度线 ≥3 条。
- **quote**：呼吸型骨架（layout-laws 第 30 行许可 ≤60% 覆盖）。`.quote` 用 `flex:1 + justify-content:space-between` 把 kicker/正文/author 推到顶/中/底，上下发丝线 + 三锚点（顶 kicker + 底 author + 中部大字号正文）。**正文 92px 斜体**——这是为了过 Easel 像素审计：测试过 64px 短金句会中段留 25% 死空白 FAIL，92px + 60–80 字金句中段最大空白带降到 **9% PASS**。`block_height` 取 `CONTENT_H`（视觉上 box 整版铺满，呼吸在 box 内部），`fill_min` 对 quote_callout 放宽到 **0.40**。

### 改动清单

| 文件 | 关键改动 |
|---|---|
| `schema.py` | 新增 `TimelineItem` / `Timeline` / `Quote`；Block Union 扩入；`LAYOUTS` 加 `timeline_flow` / `quote_callout` |
| `renderer.py` | 导入扩入 Quote/Timeline；新增 `.timeline` / `.quote` 完整 CSS（quote 正文 92px）；`render_page()` 新增两条分支 + heading 取用改为 `.get`；`to_card_draft()` 标题取用带默认值 |
| `audit.py` | `MIN_DENSITY` 加 `timeline_flow` / `quote_callout`；`block_height` Timeline→1080、Quote→CONTENT_H；`fill_min=0.40` 豁免 quote；`_count_of` / `_hint_for` 加两条 |
| `composer.py` | `Section.kind` 加 `timeline` / `quote`；新增 `timeline_items` / `quote_text` / `quote_author` / `quote_kicker`；`_plan()` prompt 加两种形状与密度要求；`_volume()` 计入；`_build_deck()` 加两条分支（quote 先清 Heading） |
| `operations.py` | `EDIT_OPS` / `CardEdit.op` 加 `set_timeline_item` / `add_timeline_item` / `remove_timeline_item` / `set_quote`；4 个 handler（timeline 复用 value=date/note=text/tag=note，quote 复用 value=正文/note=作者/tag=日期） |
| `tests/test_react_structured_cards.py` | 新增 4 个 P2 用例：timeline 渲 4 条含 date/text/note、quote 三锚点、timeline/quote schema 最小密度线、timeline/quote 编辑合并语义 |

### 量化收益（Easel `card_audit.py`，真实链路渲染 PNG）

| 骨架 | 度量 | 结果 |
|---|---|---|
| timeline_flow（4 条） | 纵向跨度 / 底部死空白 / 最大空白带 / 4 带密度 | 88% / 6% / **14% ✅ PASS** / [0.26,0.28,0.23,0.14] |
| quote_callout（70 字 / 92px） | 同上 | 88% / 6% / **9% ✅ PASS** / [0.23,0.70,0.71,0.25] |

两者都通过 Easel 像素审计门禁（最大空白带 ≤15%、底部带非空、4 带均有内容）。

### CSS 迭代史（quote 呼吸型骨架）

```
quote:  v1 正文 64px + space-between 短金句 → 中段 25% 死空白 ❌
       v2 正文 92px + 70 字金句 → 中段 9% ✅（大字号把"呼吸"压进 ≤15% 带，三锚点让留白读作刻意）
```

### 测试

- 卡片四件套：`test_react_structured_cards` + `test_e2e_card_draft_render` + `test_artifact_store_safety` + `test_llm_drives_image_text_skill` = **74 passed**（含 4 个 P2 新用例）。
- 全量回归：`pytest backend/tests --ignore=tests/test_image_plan_planner.py --basetemp=D:/tmp/pbt-p2` = **29 failed**（与 P1 基线 29 failed 完全一致），**零卡片相关失败、零新增回归**。

### 下一步

- **前端适配**：`ChatCardDraft.vue` 消费 timeline 条目编辑 + quote 三锚点编辑（当前 `set_timeline_item`/`set_quote` 复用 value/note/tag 字段语义，前端接入需做字段映射）—— **已完成（2026-10-06 第九轮）**：新增 timeline/quote/bento/stat 编辑分支与 note/tag 三层清单编辑，并补上后端 `CardEditRequest` 对 `note/tag/kicker/unit/source` 的透传（此前 HTTP 层会静默丢弃这些字段，导致前端编辑 no-op）。
- 剩余 9 卡型已齐（cover / content / list / steps / compare / bento / stat / timeline / quote），可回看是否补齐 P3（1:1 画幅逃生阀 1080×1080）。
- 真实 Wanx 生图 + 在线 ReAct→SSE→浏览器全链路冒烟仍未做。

## 前端适配（第九轮：2026-10-06）

用户选定「前端编辑 UI 适配」为 P2 收尾首项。改动只触及 ReAct 相关前端组件，不动前端框架（Vue）。

### 改动文件
- `frontend/src/components/chat/ChatCardDraft.vue`
  - `editableBlocks` 白名单扩入 `bento_grid/stat/timeline/quote`。
  - `BLOCK_LABELS`/`LAYOUT_LABELS` 补齐 4 种块型与 `bento_grid/stat_card/timeline_flow/quote_callout` 版式中文名。
  - `editorMode` 新增 `bento/stat/timeline/quote` 分支与对应模板：timeline 三字段条目编辑、quote 三锚点编辑、bento/stat 五层字段编辑（bento 多格时出格子选择器）。
  - `runEdit` 透传 `note/tag/kicker/unit/source`；`saveItem`/`addItem` 改为携带 note/tag（顺带修复旧 `String(item)` 渲染 `[object Object]` 的缺陷）。
  - 主题下拉改为消费 `localDraft.themeOptions`（6 种全量可选）。
- `frontend/src/composables/cardDraft.ts`：`NormalizedCardDraft` 增加 `themeOptions` 字段，`normalizeCardDraft` 透传之（否则主题下拉为空）。
- `frontend/src/api/creativeArtifact.ts`：`CardEditPayload` 增加 `note/tag/kicker/unit/source`，`updateStructuredCard` 透传。
- `backend/app/api/routers/creative_artifact.py`：`CardEditRequest` 增加 `note/tag/kicker/unit/source`（含 max_length），`_to_card_edit` 转发到 `CardEdit`。**这是关键修复**：此前请求体缺少这些字段，FastAPI 默认忽略多余字段，使前端 P0/P1/P2 编辑全部静默 no-op。
- `backend/tests/test_card_edit_request_wiring.py`（新建）：6 个用例锁住「请求体 → CardEdit」透传，覆盖 timeline/bento/stat/quote/item。

### 验证
- `frontend`: `vue-tsc -b --force` 通过；`vite build` 通过（含 `ChatCardDraft-B0FsDNmk.js`）。
- `backend`: `test_react_structured_cards.py` + `test_artifact_store_safety.py` = **39 passed**（与 P2 基线一致）；新增 `test_card_edit_request_wiring.py` = **6 passed**。
- 内联验证 `_to_card_edit` 对 timeline/bento/quote/item 均正确转发 `note/tag/kicker/unit/source` 到 `CardEdit`。

## 视觉系统改造（第十轮：2026-10-06）—— A 主题令牌引擎 + B 组件视觉变体

用户先排查「卡片组件/颜色问题」，再确认之前的「模板固定、不像 Easel 灵活」根因（封闭结构化 schema + 1:1 模板编译器，见下），最终拍板 ABC 三件事：A 主题令牌引擎、B 组件视觉变体、C 引入 Easel 风格库（9 套主题已覆盖，本轮回合由 A 顺带满足）。

### 诊断（拿代码说话）
- 改造前全 9 套主题（ink/warm/swiss/inkwash/cream/terminal/dopamine/luxe_noir/journal）的 `bg↔surface` 仅 **1.05–1.29**，远低于 1.5 下限 → 面板/格子与背景几乎同色（"米色叠米色"），且 4/9 主题共用米色家族，所以"看起来都一个样"。这正是用户感觉"灵活感不足、组件不丰富"在**视觉层**的真实落点（骨架层 9 种版式其实已对齐 Easel，差距只在视觉语气）。
- `bg↔muted`：cream/terminal/journal 三套未达 AA（3.05/4.12/4.38）。
- `bg↔accent`：cream/dopamine/journal 三套 <3.0。
- 根因：旧 `THEMES` 每套手写 6 个 hex，`surface` 硬编码成接近 `bg` 的值；且 `color.py` 虽有 `derive_tokens`，但 `theme_css()` 从未调用它、也不强制下限，所以推导值仍只有 1.46。

### A · 主题令牌引擎（已落地）
- `backend/app/cards/color.py`：`derive_tokens(bg,text,accent)` 重写为**强制下限**——`surface` 用循环把 `bg↔surface` 推到 ≥1.6（亮主题压暗、暗主题提亮）；`line` ≥1.9；`muted` 由 `bg→text` 混合直到 ≥4.5，若主文字本身太浅则回退到极点色保证可读；`accent` 仅在 <3.0 时按色相微调（保留品牌色相）。新增 `accessible_accent()` 护栏；`if __name__=="__main__"` 改为直接对 9 套主题跑审计（原代码引用不存在的 `THEME_TOKENS`，会 NameError）。
- `backend/app/cards/schema.py`：9 套主题**删除**硬编码的 `surface/line/muted` 键，只保留 `bg/text/accent` + 风格；`theme_css()` 改为编译期调用 `derive_tokens` 生成这三者（新增 `_theme_block` 辅助）。`on_image_*` 仍显式保留（蒙层不能用 bg/text 推导）。
- 审计结果：9 套主题 `bg↔surface` 1.60–2.16、`bg↔muted` 4.52–5.89、`bg↔accent` 3.10–10.23，三项全绿；cream 主文字 `bg↔text=4.82` 仍达标，无需改。

### B · 组件视觉变体（已落地）
- `schema.py`：`ListBlock/Steps/Compare/BentoGrid/Stat/Timeline` 各加 `variant: str = ""`（空串=经典，向后兼容旧 Deck）；新增 `VARIANT_OPTIONS` 映射（list: cards/tags；steps: chips/minimal；compare: table；bento_grid: masonry/row；stat: ring/underline；timeline: dots/slim）。
- `operations.py`：新增 `set_variant` 操作（复用 `value` 传变体 id），仅接受 `VARIANT_OPTIONS` 声明的变体，非变体组件拒绝；补 `EDIT_OPS` 与 `CardEdit.op` Literal。
- `renderer.py`：对非空变体在容器追加 `variant-<v>` class（`_list`/compare/bento/stat/timeline），并新增一整段纯 CSS-only 变体样式——经典渲染完全不动。
- `to_card_draft` 下发 `variantOptions` 供前端填充下拉。
- 前端：`creativeArtifact.ts` 的 `CardEditPayload` 加 `variant` 透传；`cardDraft.ts` 的 `NormalizedCardDraft` 加 `variantOptions`；`ChatCardDraft.vue` 编辑器头部加变体下拉（按当前块 type 过滤可选变体），`applyVariant` 走 `set_variant`。

### 验证
- `tests/test_card_variant.py`（新建，6 用例）：渲染层确认变体 class 仅在非空时追加、经典无 class；`set_variant` 应用/持久化、拒绝未知变体、拒绝非变体组件。
- 全套卡片测试 `test_card_variant + test_react_structured_cards + test_artifact_store_safety + test_card_edit_request_wiring` = **51 passed**（其余既有未提交漂移 / 需联网 LLM 的 e2e 不在内）。
- 前端 `vue-tsc -b --force` + `vite build` 通过。
- 可视化交付：`outputs/card-gallery.html`（真实 `render_page` 输出 + 9 套主题对比度审计表，27/27 全绿）。

### 待办（仍未做）
- P3 1:1 画幅逃生阀（1080×1080）。
- 真实 Wanx 生图 + 在线 ReAct→SSE→浏览器全链路冒烟。
- 前端 density「页面太空」红色提示。

## 配色治理（第十一轮：2026-10-10）—— 重区分纸色 + 强调色轴（accent axis）

用户反馈「配色还是太单一」，并明确方向：**点缀轴 + 重区分纸色**。参考 Easel 的纸色/点缀色组合，把 5/9 挤在暖米区间的纸色拆成差异化纸色，并给每套主题加一个「可切换的强调色板」。

### 诊断（拿代码说话）
- 第十轮把 `surface/line/muted` 改成由 `bg` 推导后，5/9 主题仍共用 `#f1ede4~#FBF7F0` 的暖米纸色（ΔE 极近）→ 切主题≈「同纸换点缀条」，这是「太单一」的视觉根因，不在骨架层。
- 原 `THEMES` 每套只有一个写死 `accent`，没有切换轴。

### 改动（已落地）
- `schema.py`：`THEMES` 重写为 **12 套**，纸色全部换成 Easel 差异化色——靛蓝瓷 `#f2f4f5` / 牛皮 `#eedfc7` / 瑞士白 `#fafaf8` / 宣纸 `#f3efe4` / 奶油 `#FAF6EF` / 终端黑 `#0d1117` / 多巴胺黄 `#FFD500` / 黑金 `#0e0d0c` / 手账 `#FBF7F0` / 森林 `#f5f1e8` / 沙丘 `#f0e6d2` / 植物 `#f6f4ee`；**12 套纸色互不相同**。每套新增 `accents`（逗号分隔 hex 列表）作为「强调色轴」；`accent` 仍是默认（索引 0）。删除了遗留的写死 `surface/muted/line` 键。新增 `forest/dune/botanical` 为增量主题。
- `schema.py`：新增 `_parse_accents` / `_accessible_accents` / `theme_accent_class`；`_theme_block` 除编译基础 `.{name}` 外，为每个额外强调色发出 `.{name}.accent-{i}` 覆盖（只换 `--accent`）。`accessible_accent` 保证每个色板色 `bg↔accent ≥ 3.0`（浅色点缀如瑞士柠檬黄/嫩绿会被压深到可点上）。`CardDeck` 加 `accent_index: int = 0`（默认 0，旧 Deck 反序列化外观不变）。`ThemeId` Literal 同步 12 个 id。
- `renderer.py`：文章标签追加 `theme_accent_class(deck.theme_id, deck.accent_index)`；`to_card_draft` 给每个 `themeOptions` 带上 `accents`，并下发顶层 `accentIndex` / `accentOptions`。
- `operations.py`：新增 `set_accent` 操作（复用 `edit.index` 指向 `accents` 下标），`EDIT_OPS` 与 `CardEdit.op` Literal 同步；`set_theme` 切换后若旧 `accent_index` 越界则钳回 0。
- 前端：`cardDraft.ts` 的 `NormalizedCardDraft` 加 `accentIndex` / `accentOptions`，`themeOptions` 元素加 `accents`；`ChatCardDraft.vue` 编辑器加「强调色」色板按钮组（点击调用 `applyAccent` → `set_accent`），与变体下拉同级。

### 验证
- 对比度审计（9 项全绿）：12 套主题 `bg↔surface` 1.62–2.16、`bg↔muted` 4.53–5.89、`bg↔accent` 3.10–10.23；`accent` 轴每个色均 ≥3.0（`_accessible_accents` 构造性保证）。
- `tests/test_themes_palette.py`（新建，9 用例）：12 id 全在、`ThemeId` 同步、无写死 surface/muted/line、每个强调色达对比下限、12 纸色互异、`.accent-{i}` CSS 正确发出、`theme_accent_class` 映射、`to_card_draft` 下发 accent 字段、`set_accent` 入 `EDIT_OPS`、旧 Deck 默认 `accent_index=0` 兼容。
- 全套卡片测试 `test_themes_palette + test_card_variant + test_react_structured_cards` = **49 passed**。
- 前端 `vue-tsc -b --force` + `vite build` 通过（ChatCardDraft 加色板选择器）。
- 可视化交付：`outputs/card-gallery.html` 用 `scripts/gen_card_gallery.py` 重新生成（12 套主题 × 默认/强调色-1 双卡 + 色板图例），`scripts/gen_card_previews.py` 同步可重出 PNG。
