# 项目优化待办

> 生成日期：2026-08-21
> 基于全量代码审查，按优先级 P0/P1/P2 分级

---

## P0 — 必须立即修（影响正确性 / 安全性 / 可维护性）

### TODO-01: main.py 手写增量迁移迁移到 Alembic

- **现状**：`backend/app/main.py` 的 `lifespan` 函数内有大量手写 `ALTER TABLE ADD COLUMN` 逻辑（v2/v6/v7 字段补齐），每次启动都 `_has_col` 检查
- **风险**：
  - 启动慢、生产环境锁表风险
  - 不可回滚（ALTER 无法 undo）
  - 和 Alembic 版本迁移并存，容易冲突
- **方案**：
  1. 将所有手写 ALTER 迁移到 `alembic/versions/` 新版本文件
  2. `lifespan` 只保留 `Base.metadata.create_all`（或改为 `alembic upgrade head`）
  3. 删除 `lifespan` 中 `_has_col` 相关代码
- **涉及文件**：`backend/app/main.py`、`backend/alembic/versions/`
- **状态**：[x] 已完成（手写 ALTER 迁移到 003_consolidate_handwritten_alters.py，lifespan 精简为 create_all）

### TODO-02: 清理 backend/ 根目录散落的临时脚本

- **现状**：根目录有大量 `_test_*.py` / `_fix_*.py` / `_check_*.py` / `_debug_*.py` / `_create_test_user.py` 等临时脚本
- **风险**：
  - 污染仓库，影响可维护性
  - 可能包含硬编码的测试数据/密钥
  - 新成员难以区分正式代码和临时脚本
- **方案**：
  1. 有用的调试脚本迁移到 `backend/scripts/` 或 `backend/tools/`
  2. 临时测试脚本迁移到 `backend/tests/` 或删除
  3. 在 `.gitignore` 中添加 `_*.py` 规则
- **涉及文件**：`backend/_test_api.py`, `backend/_test_e2e_chain.py`, `backend/_fix.py`, `backend/_fix_install.py`, `backend/_check.py`, `backend/_debug_intent.py`, `backend/_create_test_user.py`, `backend/_test_upload.py`, `backend/_check_cat.py`, `backend/_test_proxy.py`, `backend/_test_auth.py`, `backend/_test_http.py`, `backend/_test_api2.py`, `backend/_test_seed.py`, `backend/_fix_updated_at.py`, `backend/test_plugins_api.py`, `backend/test_list_plugins.py`, `backend/test_sync_plugins.py`
- **状态**：[x] 已完成（21 个临时脚本已删除，.gitignore 已加 backend/_*.py 规则）

### TODO-03: 排除 .pnpm-store 和 pw-browsers 入库

- **现状**：`.pnpm-store/` 和 `pw-browsers /` 目录被 git 追踪，体积巨大
- **风险**：
  - 仓库膨胀（pnpm store 和浏览器二进制可达数百 MB）
  - clone 慢、CI 慢
- **方案**：在 `.gitignore` 中添加：
  ```
  .pnpm-store/
  pw-browsers*/
  ```
  然后执行 `git rm -r --cached .pnpm-store pw-browsers\ ` 清理已追踪文件
- **涉及文件**：`.gitignore`
- **状态**：[x] 已完成（.gitignore 已有规则，git 未追踪这两个目录）

---

## P1 — 应尽快修（影响工程质量 / 生产就绪度）

### TODO-04: 开发红线手册技术栈与实际实现不一致

- **现状**：`开发红线手册.md` 声明前端必须用 React 18 + Zustand + React Flow，但实际实现是 Vue 3 + Pinia + Vue Flow
- **风险**：AI 辅助开发时按红线生成 React 代码，与项目实际不符
- **方案**：更新红线手册，将前端技术栈改为实际使用的：
  - 框架：Vue 3 + TypeScript
  - 状态管理：Pinia
  - 流程图：Vue Flow
  - 路由：Vue Router v4
- **涉及文件**：`开发红线手册.md`
- **状态**：[x] 已完成（React 18→Vue 3, Zustand→Pinia, React Flow→Vue Flow, React Router→Vue Router v4, Lucide React→Lucide Vue Next, React Hook Form→VeeValidate, 函数组件+Hooks→Composition API+setup语法糖）

### TODO-05: SSE 总线单进程限制 — 添加注释或升级方案

- **现状**：`SSEEventBus` 是进程内单例（`__new__` + `defaultdict`），多 worker/多 Pod 部署时事件不跨进程
- **风险**：水平扩展后用户可能收不到事件
- **方案**（二选一）：
  - **短期**：在 `sse_bus.py` 顶部加注释说明单进程限制，文档中注明部署要求
  - **中期**：引入 Redis Pub/Sub 或 PostgreSQL LISTEN/NOTIFY 做跨进程广播
- **涉及文件**：`backend/app/services/sse_bus.py`
- **状态**：[ ] 待办

### TODO-06: Checkpointer 策略统一

- **现状**：`graph.py` 和 `workflow.py` 各自 try import `PostgresSaver`，逻辑重复且不一致
- **方案**：
  1. 统一到 `graph.py` 的 `init_global_checkpointer()` 一处
  2. `workflow.py` 只调用 `get_global_checkpointer()`
  3. 删除 `workflow.py` 中重复的 `PostgresSaver` import
- **涉及文件**：`backend/app/agents/graph.py`, `backend/app/services/workflow.py`
- **状态**：[ ] 待办

### TODO-07: 添加 backend/pyproject.toml 统一工具链配置

- **现状**：CI 里跑 black/isort/flake8/mypy，但项目缺少 `pyproject.toml` 统一配置，本地和 CI 可能不一致
- **方案**：创建 `backend/pyproject.toml`，收敛以下配置：
  - `[tool.black]`：line-length, target-version
  - `[tool.isort]`：profile = "black"
  - `[tool.mypy]`：python_version, strict, ignore-missing-imports
  - `[tool.ruff]`：替代 flake8（更快），规则配置
  - `[project]`：dependencies, optional-dependencies
- **涉及文件**：`backend/pyproject.toml`（新建）
- **状态**：[ ] 待办

### TODO-08: 前端添加测试

- **现状**：后端有 16 个测试文件，前端零测试
- **风险**：composables / stores / 关键组件无回归保护
- **方案**：
  1. 安装 Vitest + @vue/test-utils
  2. 优先给 composables（`useSearchFlow`, `useNotifications`, `useTypewriter`）加单测
  3. 给 Pinia stores（`auth`, `workflow`, `account`）加单测
  4. 关键组件（`WorkflowStepper`, `SearchCard`）加集成测试
- **涉及文件**：`frontend/package.json`, `frontend/vitest.config.ts`（新建）, `frontend/src/**/*.spec.ts`（新建）
- **状态**：[ ] 待办

### TODO-09: 插件目录命名不一致

- **现状**：`plugins/third_party/` 下同时存在 `cat-companion`（连字符）和 `cat_companion`（下划线）两个目录
- **方案**：
  1. 确认哪个是正在使用的
  2. 删除废弃的那个
  3. 在文档/代码中统一插件目录命名规范（建议用下划线，与 Python 包名一致）
- **涉及文件**：`backend/plugins/third_party/cat-companion/`, `backend/plugins/third_party/cat_companion/`
- **状态**：[x] 已完成（删除连字符版本 cat-companion，保留下划线版本 cat_companion，与 Python 包名规范一致）

---

## P2 — 有空再修（锦上添花 / 长期演进）

### TODO-10: 架构文档与代码同步校验

- **现状**：`技术架构设计文档.md` 和 `PRD.md` 是 v1.0，部分内容可能已落后于实际实现（如 Phase 1 补漏、Plugin 系统等）
- **方案**：
  1. 通读现有文档，标注已过时章节
  2. 补充实际已实现但文档未覆盖的部分（Esther Factory、选题池监控、Chat Agent 等）
  3. 版本号升级到 v2.0
- **涉及文件**：`技术架构设计文档.md`, `PRD.md`, `前后端通信协议.md`
- **状态**：[ ] 待办

### TODO-11: LangGraph Checkpointer 持久化策略文档化

- **现状**：SQLite vs PostgreSQL checkpointer 切换逻辑散落在代码中，无文档说明
- **方案**：在架构文档中新增一节，说明：
  - 开发环境：AsyncSqliteSaver（零依赖）
  - 生产环境：PostgresSaver（需 psycopg_binary）
  - 切换方式：环境变量 `LANGGRAPH_USE_SQLITE`
- **涉及文件**：`技术架构设计文档.md`
- **状态**：[ ] 待办

### TODO-12: Recovery 策略端到端测试

- **现状**：`recovery_service.py` 有完整的恢复策略（技术性/结构性/terminate），但 `tests/` 下只有 `test_search_recovery.py`，缺少对 RecoveryService 全链路的端到端测试
- **方案**：
  1. 添加 `test_recovery_service.py`
  2. 覆盖：RecoveryLoop 耗尽 → Supervisor 决策 → Suggestion 创建 → 用户确认/拒绝 → Rollback/Terminate
  3. 覆盖：30min 超时挂起 → 自动 terminate
- **涉及文件**：`backend/tests/test_recovery_service.py`（新建）
- **状态**：[ ] 待办

### TODO-13: 敏感信息扫描

- **现状**：`backend/app/rpa/` 下有 `.wechat_credentials_*.json` 文件被追踪
- **风险**：可能包含敏感的微信登录凭证
- **方案**：
  1. 检查这些文件是否包含真实凭证
  2. 如果是，立即从 git 历史中清除（`git filter-branch` 或 BFG Repo-Cleaner）
  3. 在 `.gitignore` 中添加 `.wechat_credentials_*.json`
  4. 改为从环境变量或加密存储读取
- **涉及文件**：`backend/app/rpa/.wechat_credentials_*.json`, `.gitignore`
- **状态**：[ ] 待办

### TODO-14: CI 补充前端 lint + test

- **现状**：`ci.yml` 只跑后端 Python 的 lint + test，前端无 CI 覆盖
- **方案**：
  1. 添加 frontend job：`pnpm install` → `pnpm lint` → `pnpm test` → `pnpm build`
  2. 配置 Vite 构建失败时 CI 失败
- **涉及文件**：`.github/workflows/ci.yml`
- **状态**：[ ] 待办

### TODO-15: 性能指标采集文档化

- **现状**：有 `performance_collector.py` 但无文档说明采集了哪些指标、如何查看、告警阈值
- **方案**：在运维文档中补充性能监控章节
- **涉及文件**：`backend/app/services/performance_collector.py`
- **状态**：[ ] 待办

---

## 已完成 — Chat 驱动 Agent 集成修复记录

> 以下问题在 2026-08-21 的开发过程中发现并修复，记录于此供追溯。

### FIX-01: explore agent 包含不可用的 vl_analyze skill

- **问题**：explore agent 的 skills 列表包含 `vl_analyze`，但 `VLAnalyzeSkill.execute()` 会抛 `NotImplementedError`（Qwen-VL 适配器未实现）。LoopExecutor 的 `_dispatch_tool` 虽能 catch 异常不崩循环，但浪费一轮 iteration 且给 LLM 返回 error observation。
- **修复**：从 explore agent 的 skills 中移除 `vl_analyze`，等 Qwen-VL 适配器实现后再加回。
- **改动文件**：
  - `backend/app/agents/registry.py`：skills 从 `["trending_search", "vl_analyze", "copywrite"]` → `["trending_search", "copywrite"]`
  - `backend/tests/test_agent_registry.py`：断言同步更新
- **验证**：52 passed

### FIX-02: analyze 单步 prompt 缺失（ChatAgent ANALYZE_ONLY 路径）

- **问题**：用户说"分析一下AI教育" → IntentParser 识别为 `ANALYZE_ONLY` → ChatAgent 构建 analyze harness → SingleShotExecutor 用空泛 prompt（"请分析主题「{topic}」的爆款规律"）调 LLM → LLM 没有搜索数据，返回空泛结果。DAG 管线中 analyze_node 拿到的是 search 节点的真实搜索结果，走三层分析（规则层 + LLM粗分析 + LLM深度归因），但 ChatAgent 的单步路径完全没走这套逻辑。
- **根因**：ChatAgent 对 `ANALYZE_ONLY` 的处理和其他单步意图（SEARCH_ONLY / EXPLORE）一样，走通用 prompt harness。但 analyze 的特殊性在于——它必须有搜索数据才能产出有意义的分析，不能只靠一个空泛 prompt。
- **修复**：ChatAgent 新增 `_run_analyze_standalone` 方法，`ANALYZE_ONLY` 路径改为「先搜索再三层分析」，和 DAG 管线中 analyze_node 的逻辑完全对齐：
  1. Step 1：调用 `TrendingSearchSkill` 搜索真实数据
  2. Step 2：`analyze_viral`（Layer 1 规则层，0 LLM 成本）
  3. Step 3：`run_layer2`（Layer 2 LLM 粗分析，top 5 模式识别）
  4. Step 4：`run_layer3`（Layer 3 LLM 深度归因，趋势信号 + 选题建议）
  - 搜索无结果时返回友好提示（`_model_used: "none"`）
  - LLM 不可用时降级为仅 Layer 1（`_model_used: "layer1_only"`）
  - 异常时返回 error_fallback 而非崩溃
- **改动文件**：
  - `backend/app/agents/chat_agent.py`：
    - `_ACTION_TO_AGENT` 移除 `ANALYZE_ONLY` 映射（不再走通用 harness）
    - 新增 `_run_analyze_standalone` 方法
    - `process` 方法中 `ANALYZE_ONLY` 分流到新方法
    - `FULL_PIPELINE` / `FOLLOW_UP` 显式返回"由工作流处理"
  - `backend/tests/test_chat_agent.py`：
    - 新增 `test_chat_agent_analyze_only_runs_search_then_layers`（mock 四层，验证三层分析全走通）
    - 新增 `test_chat_agent_analyze_only_no_results`（搜索无结果降级）
- **验证**：54 passed

### FIX-03: DB 集成测试缺少 xhs_accounts 表

- **问题**：`test_chat_session_db.py` 的 `_get_last_workflow_topic` 用例插入 Workflow 行时失败，因为 Workflow 表的 `account_id` 有外键指向 `xhs_accounts.id`，但测试只创建了 User / WorkflowDefinition / Workflow / ChatSession / ChatMessage 五张表。
- **修复**：在表创建列表中加入 `XhsAccount.__table__`（在 Workflow 之前），清理列表同步更新。
- **改动文件**：
  - `backend/tests/test_chat_session_db.py`：导入 `XhsAccount`，建表/清理列表加入 `XhsAccount.__table__`
- **验证**：9 个 DB 集成测试全绿

### FIX-04: 数据库 index 重复定义

- **问题**：`WorkflowDefinition` 的 `user_id` 列同时有 `index=True`（列级）和 `__table_args__` 中的显式 `Index("ix_workflow_definitions_user_id", ...)`，导致 Alembic / SQLite 报 index 已存在。
- **修复**：移除 `user_id` 列的 `index=True`，保留 `__table_args__` 中的显式 Index。
- **改动文件**：
  - `backend/app/db/models.py`
- **验证**：DB 集成测试全绿

### FIX-05: 前端 handleWorkflowEvent 事件映射缺失

- **问题**：`ChatView.vue` 的 `handleWorkflowEvent` 缺少 `workflow_started`、`review_required`、`workflow_cancelled` 三种事件的处理逻辑。
- **修复**：补全事件处理，更新 `agentMeta` 状态。
- **改动文件**：
  - `frontend/src/components/chat/ChatView.vue`

### FIX-06: 前端进度卡片未渲染 agentMeta.steps 数据

- **问题**：ChatView 模板中没有组件渲染 `agentMeta.steps`，工作流进度信息无法展示。
- **修复**：创建 `AgentProgressCard.vue` 组件，在 ChatView 模板中引入并绑定 steps 数据。
- **改动文件**：
  - `frontend/src/components/chat/AgentProgressCard.vue`（新建）
  - `frontend/src/components/chat/ChatView.vue`

### FIX-07: search 节点空结果不触发 recovery

- **问题**：DAG 管线中 search 节点返回空结果时，不触发 recovery 机制，导致后续 analyze 节点拿到空数据。
- **修复**：search 节点空结果时触发 recovery loop。
- **改动文件**：
  - `backend/app/agents/nodes/search.py`

### FIX-08: 僵尸工作流堆积

- **问题**：PAUSED 状态的工作流仍被计入活跃计数器，导致资源不释放、僵尸工作流堆积。
- **修复**：将 PAUSED 状态的工作流从活跃计数器中移除。
- **改动文件**：
  - `backend/app/services/workflow.py`

### FIX-09: 前端未处理 agent_output 同步返回

- **问题**：用户说"搜一下AI教育"或"分析一下AI教育"时，后端返回 `status: "agent_output"` + `output: {...}`（单步 search/analyze/explore 的同步结果），但前端 `ChatView.vue` 只处理了 `blocked`、`chat`、`workflow_id` 三种情况，`agent_output` 的数据被丢弃，用户看到的是空白回复。
- **根因**：前端 fetch `/api/v1/chat/agent` 后的响应处理逻辑缺少 `agent_output` 分支。DAG 全流程有 SSE 流式推送，但单步路径是同步 HTTP 返回，前端没有对应的渲染逻辑。
- **修复**：在 ChatView.vue 的响应处理中新增 `agent_output` 分支：
  - 有 `results` 数组时：区分搜索结果（显示 top5 + 互动数据）和分析结果（显示标题钩子/内容结构/选题方向）
  - 有 `_message` 时（如搜索无结果）：直接显示友好提示
  - 有 `_error` 时：显示错误信息
  - 其他情况：JSON 序列化兜底
  - 设置 `workflowStatus = 'completed'`
- **改动文件**：
  - `frontend/src/components/chat/ChatView.vue`
- **验证**：后端 54 passed；前端逻辑补全，三种 output 格式均有渲染路径

---

## 完成进度

| 优先级 | 总数 | 已完成 | 完成率 |
|--------|------|--------|--------|
| P0     | 3    | 3      | 100%   |
| P1     | 6    | 0      | 0%     |
| P2     | 6    | 0      | 0%     |
| **合计** | **15** | **3** | **20%** |
| FIX（集成修复） | 9 | 9 | 100% |

---

## 修改记录

| 日期 | 操作 | 条目 |
|------|------|------|
| 2026-08-21 | 创建 | 初始生成，基于全量代码审查 |
| 2026-08-21 | 完成 | FIX-01 ~ FIX-09，Chat 驱动 Agent 集成修复（54 passed） |