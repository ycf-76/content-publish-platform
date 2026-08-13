# 多智能体小红书发布平台 PRD

| 字段 | 内容 |
|---|---|
| 文档版本 | v1.0 (MVP) |
| 创建日期 | 2026-07-24 |
| 状态 | 待评审 |
| 产品代号 | XHS-Agent-Flow |

---

## 1. 文档信息

### 1.1 编写目的
本文档定义"多智能体小红书发布平台"MVP版本的产品需求，作为产品设计、研发实施、测试验收的统一基准。

### 1.2 适用范围
- 前端工程师（Vue3）
- 后端工程师（FastAPI）
- 算法/Agent工程师
- QA
- 产品/设计

### 1.3 术语约定
见第3章术语表。

---

## 2. 产品概述

### 2.1 产品背景
小红书爆款内容生产高度依赖人工经验（选题→拆解→配图→文案→发布），环节多、链路长、质量不稳定。本平台通过**多智能体协作工作流**将整条链路自动化：用户只需给定主题（如"科技类"），系统自动完成爆款搜索、要素分析、配图生成、文案编写、合规审核、一键发布。

### 2.2 目标用户
- 个人内容创作者（科技/生活/美食等垂类）
- 小团队内容运营
- MVP阶段：单用户、单小红书账号

### 2.3 核心价值
1. **全链路自动化**：6个专业智能体 + 1个监督智能体协作，用户只在关键节点审核。
2. **爆款方法论沉淀**：分析Agent拆解爆款要素，让"为什么火"可复用。
3. **可视化可控**：流程图式UI，用户对每一步可见、可审、可回退。
4. **稳定可发布**：扫码登录 + MCP发布，规避模拟登录风控。

### 2.4 核心设计决策（已锁定）

| # | 模块 | 决策 | 决策理由 |
|---|---|---|---|
| D1 | 账号接入 | 分层登录：浏览器插件复用登录态（首选，无需扫码）→ 已存储Session自动刷新（次选）→ 扫码登录（兜底）。Session本地加密存储 | 插件方式风控最低且用户无感；扫码作为兜底保证可用性；与D17 MCP双模式架构对齐 |
| D2 | 多模态架构 | Qwen-VL做爆款图理解打标签；通义万相/即梦做生图；解耦可替换 | VL是理解专家，生图用专业Diffusion模型，解耦后可换模型 |
| D3 | 监督Agent架构 | 分层：硬规则(代码) → 软语义(轻量LLM) → 状态机(硬编码路由) | 全程LLM监督会导致无限循环、Token爆炸、决策不可控 |
| D4 | 监督Agent权限 | 建议权（判断+推荐+用户拍板） | 完全观察权太弱，完全执行权太危险 |
| D5 | 多账号 | DB层面User:Account=1:N；MVP前端只暴露1个账号 | 预留扩展，降低首版复杂度 |
| D6 | 回退语义 | 采用LangGraph原生：回退到目标checkpoint，下游节点重跑，旧产出丢弃 | 与LangGraph checkpoint机制对齐，实现简单可靠，避免自维护stale状态的复杂度 |
| D7 | 记忆范围 | 仅任务内上下文传递 | MVP不做跨任务记忆/向量库 |
| D8 | 前端形态 | React 18 + TypeScript + Zustand + 可视化流程图（React Flow） | 满足回退+审核的强交互需求；React Flow原版更稳定；TS+Zustand类型安全贯穿全栈 |
| D9 | 工作流执行 | 异步可离开，SSE推送状态，退出时审核提醒 | 工作流跑5-15分钟，用户不应被绑在页面 |
| D10 | 工作流并发 | 单工作流（一次一条，跑完才能开下一条） | MVP简化 |
| D11 | 爆款图处理 | 只分析不存储原图，只存VL输出的标签 | 规避反爬与版权风险 |
| D12 | 模型路由 | 文案Agent用DeepSeek-R1；其他文本Agent用DeepSeek-V3；监督软语义用V3；理解用Qwen-VL；生图用通义万相/即梦 | 文案质量优先，其他成本优先 |
| D13 | Agent技术架构 | LangGraph(编排) + 自研Harness(运行时) + 显式声明Skills + MCP服务 | 编排/执行/能力三层解耦，配置驱动，新增Agent=加配置 |
| D14 | 监督Agent形态 | 分散式守卫（散落在各节点边上的guard+conditional edge），非中心化监督节点 | 避免中心化性能瓶颈和单点故障，契合LangGraph图模型 |
| D15 | 监督-修复循环 | Harness内Recovery Loop（max_attempts=3+智能退避+熔断）→ 监督Agent分层决策（技术性自动/结构性拍板）→ 30分钟超时挂起 | 三层兜底避免死循环，30分钟挂起避免资源永久占用 |
| D16 | Agent过程透明化 | 实时推送Agent内部过程（工具调用/思考/决策/进度/模型切换）到前端执行详情面板，分层推送（L1必推/L2思考流式/L3仅存DB），用户可切简洁/详细模式 | 变"结果透明"为"过程透明"，消除黑盒等待焦虑；零额外LLM成本（R1 reasoning是流式副产品） |
| D17 | 小红书数据获取 | MCP服务化双模式：浏览器插件MCP（生产首选，复用用户登录态+真实IP，风控最低）+ uv run MCP（开发/兜底，基于社区项目二次开发）。统一接口+自动降级。配图用base64返回，不存原图 | MCP化符合D13能力可插拔；插件方式绕过签名问题和风控；双模式降级保证可用性 |

---

## 3. 术语表

| 术语 | 定义 |
|---|---|
| Agent（智能体） | 基于LLM、具备特定Skills和Prompt、能完成单一职责的智能单元 |
| Skills | Agent可调用的工具/能力集合（如搜索API、生图API、MCP发布） |
| Orchestrator（监督Agent） | 负责质量判断、异常建议、回退推荐的中心智能体 |
| 工作流（Workflow） | 一次完整的内容生产-发布任务，由6个Agent节点串联构成 |
| 节点（Node） | 流程图上的一个Agent执行单元 |
| Checkpoint（检查点） | 每个Agent产出后保存的快照，用于回退恢复（由LangGraph原生提供） |
| Harness | 每个Agent节点的运行时容器，封装LLM+Memory+Skills+Prompt+硬规则+软语义，是Agent的外壳 |
| Skills | Agent可调用的工具/能力，分为本地@tool函数和MCP服务调用，由Agent显式声明后注入 |
| 硬规则 | 由代码执行的确定性检查（超时/空返回/HTTP错误），不经过LLM |
| 软语义 | 由轻量LLM执行的质量判断（调性匹配/内容空洞等） |
| 状态机 | 工作流引擎中硬编码的节点状态流转与路由逻辑（基于LangGraph StateGraph） |
| 分散式守卫 | 监督Agent以guard+conditional edge形式散落在各节点边上，非中心化监督节点 |
| Recovery Loop | Agent内部的恢复循环，max_attempts=3次策略重试，配合智能退避和熔断器 |
| Recovery Strategy | 可插拔的恢复策略（原样重试/拓宽关键词/减少输入/简化prompt/切备用模型） |
| 智能退避 | 指数退避+抖动，避免雪崩式重试打爆下游 |
| 熔断器 | 滑动窗口失败率达阈值后熔断，防止崩溃Agent被反复重试拖垮系统 |
| 技术性恢复 | 切模型/刷新Token等纯技术决策，监督Agent自动执行，不打断用户 |
| 结构性恢复 | 回退到上游节点等需改变流程的决策，建议权，用户拍板 |
| 超时挂起 | 结构性恢复30分钟无响应，自动挂起任务释放资源，定时拉起 |
| MCP | Model Context Protocol，本项目中特指小红书发布MCP服务 |
| Refresh Token | 扫码登录后获得的长效凭证，用于自动刷新Session |

---

## 4. 系统架构总览

### 4.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (Vue3 + 流程图)                        │
│   账号管理 │ 工作流发起 │ 可视化流程图 │ 人工审核 │ 回退操作        │
└───────────────┬─────────────────────────────────┬───────────────┘
                │ WebSocket(状态推送)              │ HTTP REST
                │                                  │
┌───────────────▼──────────────────────────────────▼───────────────┐
│                        后端 (FastAPI)                             │
│  ┌──────────┐  ┌──────────────┐  ┌────────────┐  ┌───────────┐  │
│  │ 账号服务  │  │ 工作流引擎    │  │ Agent调度  │  │ MCP代理层  │  │
│  │ (扫码/   │  │ (状态机/检查 │  │ (6+1 Agent │  │ (小红书   │  │
│  │  Token)  │  │  点/回退)    │  │  编排)     │  │  发布)    │  │
│  └──────────┘  └──────────────┘  └────────────┘  └───────────┘  │
│                      │                                            │
│  ┌───────────────────▼────────────────────────────────────────┐  │
│  │              监督Agent (分层架构)                            │  │
│  │  Layer1 硬规则(代码) → Layer2 软语义(LLM) → Layer3 状态机   │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────┬──────────────┬──────────────┬──────────────┬──────────┘
           │              │              │              │
    ┌──────▼──────┐ ┌─────▼─────┐ ┌──────▼─────┐ ┌──────▼──────┐
    │ DeepSeek    │ │ Qwen-VL   │ │通义万相/即梦│ │ 小红书MCP   │
    │ (V3/R1)     │ │ (图理解)  │ │ (生图)     │ │ (发布/搜索) │
    └─────────────┘ └───────────┘ └────────────┘ └─────────────┘
```

### 4.2 智能体角色清单（6+1）

| # | Agent | 职责 | 模型 | 输入 | 输出 |
|---|---|---|---|---|---|
| 1 | 搜索Agent | 按主题在小红书搜索爆款笔记 | DeepSeek-V3 | 主题关键词 | 爆款笔记列表(标题/摘要/链接/互动数) |
| 2 | 分析Agent | 拆解爆款原因、提取内容结构与要素 | DeepSeek-V3 + Qwen-VL | 爆款笔记列表 | 爆款要素总结(选题/结构/情绪点/视觉标签) |
| 3 | 图片生成Agent | 根据视觉标签生成配图 | 通义万相/即梦 | 视觉标签+数量需求 | 图片URL列表 |
| 4 | 文案Agent | 编写发布文案 | DeepSeek-R1 | 爆款要素+图片标签 | 完整笔记文案(标题+正文+话题标签) |
| 5 | 审核Agent | 合规与质量审核 | DeepSeek-V3 | 完整笔记(文案+图) | 通过/打回+原因+建议回退点 |
| 6 | 发布Agent | 调用MCP发布到小红书 | 无LLM(纯工具调用) | 通过的笔记+账号Token | 发布结果(成功/失败+链接) |
| 7 | 监督Agent | 质量判断、异常建议、回退推荐 | DeepSeek-V3(软语义层) | 工作流日志摘要+当前节点产出 | 建议指令(建议权) |

### 4.3 编排架构：硬规则 + 软语义 + 状态机 三层

```
节点产出
   │
   ▼
┌──────────────────────────────────┐
│ Layer1: 硬规则守卫 (代码, <10ms)   │
│  · 超时(>15s无返回) → 重试/熔断    │
│  · 空返回/JSON错误/缺字段 → 回退   │
│  · HTTP 500/404 → 切备用模型/报错 │
│  通过 → 进入Layer2；失败 → 状态机  │
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ Layer2: 软语义仲裁 (轻量LLM)      │
│  · 质量判断(调性匹配/内容空洞)     │
│  · 只判质量,不控制流程             │
│  输出: quality_pass + issues[]    │
└──────────────┬───────────────────┘
               ▼
┌──────────────────────────────────┐
│ Layer3: 状态机 (硬编码路由)        │
│  · quality_pass=true → 下一节点   │
│  · quality_pass=false → 建议回退  │
│  · 硬规则失败 → 重试N次后报错      │
│  · 路由完全确定,LLM不参与跳转      │
└──────────────────────────────────┘
```

---

## 5. 功能需求详述

### 5.1 账号管理

#### 5.1.1 扫码登录
- **功能**：用户在前端点击"绑定小红书账号"，后端调用MCP服务的`login()`方法，生成二维码。
- **交互**：
  1. 前端展示二维码（轮询或WebSocket获取状态）
  2. 用户用小红书App扫码确认
  3. 后端获取Refresh Token，**本地加密存储**（AES-256，密钥由用户主密码派生）
  4. 前端显示"绑定成功"，展示账号昵称/头像
- **Token管理**：
  - Refresh Token有效期较长（参考xiaohongshu-mcp-py实现）
  - 后端自动检测Session过期，过期时用Refresh Token静默刷新
  - 刷新失败 → 前端提示"登录态失效，请重新扫码"

#### 5.1.2 账号状态查询
- 接口：`GET /api/account/status`
- 返回：`{bound: bool, nickname, avatar, session_valid: bool, last_refresh_at}`

#### 5.1.3 解绑账号
- 接口：`POST /api/account/unbind`
- 行为：清除本地加密存储的Token，不影响小红书账号本身

#### 5.1.4 多账号预留
- 数据模型：User 1:N Account（见第8章）
- MVP前端：只展示/操作1个账号，隐藏"切换账号"入口
- 二期：开放多账号切换

---

### 5.2 工作流引擎（基于LangGraph，D13决策落地）

#### 5.2.1 工作流定义
固定线性DAG（MVP不支持用户编辑），由LangGraph `StateGraph` 描述：
```
[开始] → [搜索] → [分析] → [图片生成] → [人工审图] → [文案] → [审核] → [人工终审] → [发布] → [结束]
```
- 每个节点 = 一个自研Harness实例（见技术架构文档）
- 节点间的条件路由通过 `add_conditional_edges` 实现（质量通过→下一节点；不通过→建议回退分支）
- 人工审核节点通过 `interrupt_before` / `interrupt` + `Command(resume=...)` 实现暂停-恢复

#### 5.2.2 节点状态机

| 状态 | 含义 | 后续可流转 |
|---|---|---|
| `pending` | 待执行 | → running |
| `running` | 执行中 | → awaiting_review / passed / error |
| `awaiting_review` | 等待人工审核(仅图片/终审节点)，LangGraph图处于interrupt | → passed / rejected |
| `passed` | 通过，进入下一步 | → (下一节点pending→running) |
| `rejected` | 被打回 | → (回到目标checkpoint重新running) |
| `error` | 异常 | → running(监督Agent建议重试) / terminated |
| `suspended` | 30分钟超时挂起，等待用户响应或定时拉起 | → running(用户手动恢复/定时拉起) / terminated |
| `terminated` | 终止 | (终态) |
| `completed` | 全流程完成 | (终态) |

#### 5.2.3 检查点（Checkpoint，LangGraph原生）
- 由 LangGraph `PostgresSaver` / `SqliteSaver` 自动持久化每步状态
- 每个节点执行后自动生成checkpoint，无需自研快照逻辑
- 支持从任意checkpoint恢复执行（回退的基础）

#### 5.2.4 回退语义（D6决策落地，LangGraph原生）
- **触发方式**：
  - 用户在流程图上点击某已完成节点 → 选择"重跑从此节点开始"
  - 监督Agent建议回退（建议权）→ 前端弹出确认框，用户确认
  - 审核节点打回 → 自动回退到指定节点
- **回退执行**：
  - 通过 LangGraph 的 checkpoint 恢复机制，回到目标节点对应的checkpoint
  - 从该节点起重新执行，**下游所有节点重跑，旧产出丢弃**（不再标记stale）
  - 回退操作前端表现为：目标节点变running，下游节点变pending后依次推进
- **回退范围**：单一语义"重跑从此节点开始"，简化交互

#### 5.2.5 异步执行与状态推送（D9决策落地）
- **后端**：工作流在后台Worker中执行（建议Celery或asyncio task）
- **前端**：通过WebSocket订阅工作流状态变更
- **推送事件类型**：
  - `node_status_changed`：节点状态变更
  - `review_required`：需要人工审核（关键，见5.6）
  - `supervisor_suggestion`：监督Agent建议
  - `workflow_completed` / `workflow_error`
- **离线审核提醒**：用户离开当前界面时，若工作流进入`awaiting_review`：
  - WebSocket推送 `review_required`
  - 前端全局通知（浏览器Notification + 站内消息中心）
  - 用户回到页面时，自动定位到待审核节点

#### 5.2.6 单工作流约束（D10决策落地）
- 同一用户同时只能有1个`running`状态的工作流
- 发起新工作流前，若已有运行中的工作流 → 前端提示"请先完成或终止当前工作流"

#### 5.2.7 超时挂起与恢复（D15决策落地）
当工作流进入"结构性恢复待用户确认"状态，30分钟内用户未响应：
1. **自动挂起**：工作流状态改为`suspended`，释放Worker资源
2. **保存恢复点**：记录pending recovery信息 + LangGraph thread_id
3. **通知用户**：WebSocket推送 `workflow_suspended` 事件
4. **定时拉起**：每小时检查依赖是否恢复，恢复则重新进入待确认状态
5. **手动恢复**：用户可随时手动拉起挂起的任务

> 挂起不等于终止。挂起是为了释放资源不永久阻塞；用户或定时任务可随时拉起继续。

---

### 5.3 六个Agent详述

#### 5.3.1 搜索Agent
- **职责**：按主题在小红书搜索爆款笔记
- **Skills**：`xhs_search(keyword, limit)` — 调用MCP搜索接口
- **输入**：`{theme: "科技", keyword: "AI硬件"}`（主题+可选细分关键词）
- **输出**：
  ```json
  {
    "notes": [
      {"title": "...", "summary": "...", "url": "...", "likes": 1200, "comments": 80}
    ]
  }
  ```
- **Prompt要点**：根据主题生成多个搜索关键词组合，按互动量排序取Top N
- **模型**：DeepSeek-V3
- **硬规则**：搜索结果为空 → 重试（换关键词）；连续3次空 → 报错

#### 5.3.2 分析Agent
- **职责**：拆解爆款原因、提取内容结构与要素
- **Skills**：`vl_analyze(image_url)` — 调用Qwen-VL理解爆款配图
- **输入**：搜索Agent输出的笔记列表
- **处理**：
  1. 对每条爆款笔记，调用Qwen-VL理解其配图，输出视觉标签（**不存储原图，只存标签**，D11决策）
  2. 文本部分由DeepSeek-V3分析选题角度、标题结构、情绪点、内容框架
- **输出**：
  ```json
  {
    "factors": {
      "topic_angles": ["...", "..."],
      "title_patterns": ["数字开头+痛点", "..."],
      "emotion_hooks": ["焦虑共鸣", "..."],
      "content_structures": ["清单体", "..."],
      "visual_tags": [["暖色调","俯拍","手冲咖啡","极简背景"], ...]
    },
    "summary": "爆款要素总结"
  }
  ```
- **模型**：DeepSeek-V3（文本） + Qwen-VL（图理解）
- **软语义检查点**：监督Agent判断"爆款因子是否符合科技类调性"

#### 5.3.3 图片生成Agent
- **职责**：根据视觉标签生成配图
- **Skills**：`generate_image(prompt, size, style)` — 调用通义万相/即梦
- **输入**：分析Agent输出的`visual_tags` + 用户配置的图片数量
- **输出**：`{images: [{url, prompt_used, model}]}`
- **模型**：通义万相（默认，中文场景优）或即梦（艺术风格灵活），可配置
- **人工审核**：生成后节点进入`awaiting_review`，用户可：
  - 通过
  - 重新生成（可修改prompt）
  - 上传自有图片替换
- **硬规则**：生图API失败 → 重试2次；仍失败 → 切备用模型

#### 5.3.4 文案Agent
- **职责**：编写发布文案
- **输入**：分析Agent的爆款要素 + 图片生成Agent的图片标签
- **输出**：
  ```json
  {
    "title": "...",
    "body": "...",
    "tags": ["#AI硬件", "#科技好物"]
  }
  ```
- **模型**：**DeepSeek-R1**（D12决策，质量优先）
- **Prompt要点**：融合爆款要素，保持调性一致，标题抓人，正文结构清晰，自然植入话题标签
- **软语义检查点**：监督Agent判断"大纲是否过于空洞"

#### 5.3.5 审核Agent
- **职责**：合规与质量审核
- **输入**：完整笔记（文案+图片URL）
- **输出**：
  ```json
  {
    "passed": false,
    "issues": ["涉嫌绝对化用语", "图片与文案关联度低"],
    "suggested_rollback_node": "文案Agent",
    "suggestions": ["将'最好'改为'出色'"]
  }
  ```
- **模型**：DeepSeek-V3
- **检查项**：广告法违禁词、小红书社区规范、图文一致性、标题党过度
- **行为**：
  - `passed=true` → 进入人工终审
  - `passed=false` → 分散式守卫的软语义复核建议 → 前端展示问题+建议回退点

#### 5.3.6 发布Agent
- **职责**：调用MCP发布到小红书
- **Skills**：`xhs_publish(title, body, images, tags, account_token)` — 调用MCP发布接口
- **输入**：人工终审通过的笔记 + 账号Token
- **输出**：`{success: bool, post_url: "...", error?: "..."}`
- **模型**：无LLM，纯工具调用
- **硬规则**：
  - 发布失败 → 重试2次
  - 仍失败 → 报错，不自动回退（发布问题通常需人工排查）
- **安全**：发布前最后确认Token有效性，无效则中断并提示重新扫码

---

### 5.4 监督Agent（分散式守卫，D3+D14决策落地）

#### 5.4.1 形态：分散式守卫（非中心化节点）
监督Agent不是一个常驻的中心节点，而是**散落在各节点边上的 guard + conditional edge**。这种形态契合LangGraph的图模型，避免中心化性能瓶颈和单点故障。

落地方式：
- **硬规则guard**：作为每个Harness的内置前置/后置检查，在节点内部执行，不进图
- **软语义conditional edge**：在质量敏感节点（分析/文案/审核）的出边上，加一个软语义判断节点，用 `add_conditional_edges` 路由（通过→下一业务节点；不通过→建议回退分支）
- **状态机路由**：全部由LangGraph的conditional edges硬编码，LLM不参与跳转

#### 5.4.2 分层架构（D3决策落地）

**Layer1：硬规则守卫（代码执行，Harness内置）**
- 不经过LLM，<10ms，零Token成本
- 检查项：
  - 超时（>15秒无返回）→ 重试或熔断
  - 空返回（JSON格式错误/缺失关键字段）→ 触发回退
  - HTTP状态码（500/404）→ 切备用模型或报错终止
- 结果：通过则进入Layer2，失败则直接进入Layer3状态机处理
- 落地位置：每个Harness的run()方法内置前置/后置guard

**Layer2：软语义仲裁（轻量LLM，仅质量敏感节点）**
- 仅在硬规则通过后唤醒
- 模型：DeepSeek-V3（成本低）
- **只判质量，不控制流程**
- 仲裁内容示例：
  - "分析Agent总结的爆款因子是否真的符合'科技类'调性？"
  - "文案Agent产出的大纲是否过于空洞？"
  - "图片标签与文案主题是否匹配？"
- 输出：`{quality_pass: bool, issues: [...], severity: "low/medium/high"}`
- 落地位置：质量敏感节点出边的独立判断节点（LangGraph node）

**Layer3：状态机（LangGraph conditional edges，硬编码路由）**
- 完全确定性，LLM不参与跳转
- 路由规则：
  - `quality_pass=true` → 进入下一节点
  - `quality_pass=false` → 生成"建议回退"指令（建议权），前端弹确认框
  - 硬规则失败 → 重试N次后报错，标记节点`error`

#### 5.4.3 决策权限（D4决策落地）
- **建议权**：判断+推荐，用户拍板
- 不允许软语义层直接命令Agent重跑（防止LLM幻觉乱调度）
- 例外：硬规则层的重试/熔断是代码自动执行的，不需用户确认（工程行为非调度行为）

#### 5.4.4 触发规则（分级触发）
- **每个节点产出后必经Layer1硬规则**（零成本，Harness内置）
- **质量敏感节点（分析/文案/审核）额外经Layer2软语义**（成本可控）
- **纯工具节点（搜索/发布）只走Layer1**，不唤起LLM

#### 5.4.5 Recovery 决策层（Layer4，D15决策落地）
当 Agent 内部 Recovery Loop（max_attempts=3 + 智能退避 + 熔断器）三次策略全失败，触发 `escalate_to_supervisor`，进入Recovery决策层。**采用分层决策机制**：

| 恢复类型 | 例子 | 决策权限 | 是否打断用户 |
|---|---|---|---|
| **技术性恢复** | 切换备用模型（R1→V3）、刷新Token | **自动执行** | 否 |
| **结构性恢复** | 回退到上游节点重跑 | **用户拍板** | 是 |
| **无法恢复** | 所有方案都试过仍失败 | **终止+告警** | 是 |

- **Recovery Loop**（Harness内，每个Agent独立配置）：原样重试 → 调整输入/参数 → 切备用模型，配合指数退避+抖动+熔断器
- **技术性恢复**：监督Agent自动执行（如切模型），不打断用户，本地重试
- **结构性恢复**：建议权，用户拍板，启动30分钟超时计时器（见5.2.7）
- **Recovery策略配置化**：每个Agent的YAML含独立`recovery`节，声明自己的策略组合，可入Git版本管理

**三层兜底避免死循环**：
1. Recovery Loop：max_attempts=3 上限
2. 熔断器：failure_threshold=5 触发熔断，60秒后半开试探
3. 30分钟超时挂起：不永久阻塞，资源释放，定时拉起

---

### 5.5 可视化流程图前端

#### 5.5.1 流程图渲染
- 技术选型建议：Vue3 + **VueFlow**（或AntV X6）
- 节点布局：横向线性DAG，从左到右
- 节点元素：图标 + 名称 + 状态徽章 + 进度指示

#### 5.5.2 节点状态视觉
| 状态 | 视觉 |
|---|---|
| pending | 灰色，低饱和 |
| running | 蓝色，脉动动画，加载圈 |
| awaiting_review | 橙色高亮，脉动+铃铛图标（强提示） |
| passed | 绿色，对勾 |
| rejected | 红色，叉号 |
| error | 红色+错误图标 |
| completed | 深绿，完成徽章 |

#### 5.5.3 交互
- **点击节点** → 弹出侧边抽屉：节点详情（输入/输出/Prompt/模型/耗时/质量报告）
- **右键/AI建议按钮** → 对已完成节点：重跑从此节点开始 / 查看历史检查点
- **awaiting_review节点** → 进入审核交互（见5.6）
- **软语义建议** → 节点旁出现"AI建议"气泡，点击查看详情+确认回退/忽略

#### 5.5.4 全局视图
- 顶部：工作流主题、进度条、耗时、当前阶段
- 底部：工作流日志流（WebSocket实时推送）
- 侧边：监督Agent决策时间线

---

### 5.6 人工审核交互

#### 5.6.1 图片审核节点
- **触发**：图片生成Agent产出后，节点进入`awaiting_review`
- **界面**：
  - 大图预览区（支持多图轮播）
  - 每张图下方：生成prompt、所用模型
  - 操作按钮：`通过` / `重新生成(可改prompt)` / `上传自有图片`
- **上传自有图片**：替换对应位置的生成图，后续文案Agent会收到新图标签

#### 5.6.2 人工终审节点
- **触发**：审核Agent通过后，节点进入`awaiting_review`
- **界面**：
  - 小红书发布预览样式（模拟小红书卡片：封面图+标题+正文+标签）
  - 操作按钮：`通过并发布` / `打回到指定节点` / `手动编辑后发布`
- **打回到指定节点**：弹出节点选择器（流程图上可选），选择后通过LangGraph checkpoint回退，该节点重新`running`，下游重跑
- **手动编辑后发布**：内联编辑文案，编辑后直接进入发布Agent（跳过再次审核）

#### 5.6.3 离线审核提醒（D9决策落地）
- 工作流进入`awaiting_review`时：
  1. WebSocket推送`review_required`事件
  2. 浏览器Notification（需用户授权）
  3. 站内消息中心记录
- 用户回到页面：
  - 自动滚动定位到待审核节点
  - 顶部横幅提示"有待审核任务"

---

### 5.7 MCP发布服务集成

#### 5.7.1 MCP服务选型
- 基于社区 `xiaohongshu-mcp-py` 改造封装
- 提供 Skills：
  - `login()` — 扫码登录，返回二维码
  - `search(keyword, limit)` — 搜索笔记
  - `publish(title, body, images, tags, token)` — 发布笔记
  - `check_session(token)` — 检查Session有效性
  - `refresh_token(refresh_token)` — 刷新Token

#### 5.7.2 集成方式
- 后端通过MCP协议调用上述Skills
- MCP服务作为独立进程部署，FastAPI通过HTTP/stdio与之通信
- Token传递：FastAPI从加密存储读取 → 注入MCP调用 → 不在前端暴露Token

#### 5.7.3 异常处理
- MCP服务不可用 → 健康检查告警，发布节点直接`error`
- 发布失败 → 重试2次（硬规则），仍失败 → 报错，不自动回退

---

## 6. 非功能需求

### 6.1 性能
- 单条工作流端到端时长：目标 < 15分钟（含人工审核等待除外）
- 单个Agent节点响应：LLM调用 < 30秒，生图 < 60秒
- WebSocket状态推送延迟：< 1秒
- 前端流程图渲染：节点<20个时 < 200ms

### 6.2 安全
- 账号Token本地加密存储（AES-256，密钥由用户主密码派生）
- Token不从前端暴露，所有MCP调用经后端代理
- 用户主密码不存储，仅用于派生密钥
- API鉴权：JWT
- 爆款原图不存储（D11），只存VL输出的标签

### 6.3 可扩展性
- Agent模型可配置（DeepSeek/千问/通义万相均通过适配器接口接入）
- 生图模型可热切换（通义万相↔即梦）
- 多账号DB已预留（D5），二期前端开放
- 工作流DAG当前固定，二期支持用户编辑

### 6.4 可靠性
- 检查点机制保证回退一致性
- 硬规则层的重试/熔断保证工程稳定性
- 工作流状态持久化，服务重启可恢复

### 6.5 可观测性
- 每个Agent调用记录：模型、prompt、输入输出、耗时、Token消耗、成本
- 监督Agent决策日志
- 工作流执行日志（可导出）

---

## 7. 技术栈与依赖

### 7.1 前端
- Vue 3 + TypeScript
- Vite
- Vue Router / Pinia
- **VueFlow**（流程图渲染）
- Tailwind CSS
- Axios + WebSocket客户端
- 浏览器Notification API

### 7.2 后端
- Python 3.11 + FastAPI
- Uvicorn
- **任务队列**：Celery + Redis（或asyncio + 后台任务）
- **WebSocket**：FastAPI原生支持
- **ORM**：SQLAlchemy + PostgreSQL（或SQLite for MVP）
- **加密**：cryptography库（AES-256）
- JWT鉴权
- **Agent编排**：LangGraph（StateGraph / checkpoint / interrupt / conditional edges）
- **Agent运行时**：自研轻量Harness（封装LLM+Skills+硬规则+软语义）
- **Skills/工具抽象**：langchain-core `@tool` 装饰器 + 自研MCP适配层

### 7.3 AI模型
| 用途 | 模型 | 说明 |
|---|---|---|
| 文本(默认) | DeepSeek-V3 | 搜索/分析/审核/监督软语义 |
| 文本(文案) | DeepSeek-R1 | 文案Agent，质量优先 |
| 图像理解 | Qwen-VL | 爆款配图打标签 |
| 图像生成 | 通义万相 / 即梦 | 默认通义万相，可配置切换 |

### 7.4 外部服务
- 小红书MCP服务（基于xiaohongshu-mcp-py改造）
- DeepSeek API
- 阿里云百炼（Qwen-VL + 通义万相）
- 即梦API（备用生图）

---

## 8. 数据模型（关键表结构）

### 8.1 用户表 `users`
| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | UUID |
| username | varchar | 用户名 |
| password_hash | varchar | 密码哈希（用于派生加密密钥的口令） |
| master_password_salt | varchar | 主密码盐 |
| created_at | timestamp | |

### 8.2 小红书账号表 `xhs_accounts`（D5多账号预留）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | UUID |
| user_id | FK → users.id | 1:N |
| nickname | varchar | 小红书昵称 |
| avatar | varchar | 头像URL |
| encrypted_refresh_token | text | 加密存储的Refresh Token |
| encrypted_session | text | 加密存储的Session |
| session_valid | bool | Session是否有效 |
| last_refresh_at | timestamp | 最后刷新时间 |
| is_active | bool | MVP仅1个active |
| created_at | timestamp | |

### 8.3 工作流表 `workflows`
| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | UUID |
| user_id | FK | |
| account_id | FK | |
| theme | varchar | 主题(科技/美食等) |
| keyword | varchar | 细分关键词 |
| status | varchar | running/awaiting_review/completed/terminated |
| current_node | varchar | 当前节点 |
| started_at | timestamp | |
| completed_at | timestamp | |

### 8.4 工作流节点表 `workflow_nodes`
| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | UUID |
| workflow_id | FK | |
| node_type | varchar | search/analyze/image_gen/image_review/copywrite/audit/final_review/publish |
| status | varchar | pending/running/awaiting_review/passed/rejected/error/completed |
| langgraph_thread_id | varchar | LangGraph checkpoint线程ID，用于回退恢复 |
| input | jsonb | 节点输入 |
| output | jsonb | 节点输出 |
| prompt | text | 使用的prompt |
| model | varchar | 使用的模型 |
| started_at | timestamp | |
| completed_at | timestamp | |
| duration_ms | int | 耗时 |
| token_cost | int | Token消耗 |
| error_msg | text | 错误信息 |

### 8.5 检查点表 `checkpoints`（LangGraph原生管理，本表为业务侧冗余索引）
| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | UUID |
| workflow_id | FK | |
| node_id | FK | |
| langgraph_thread_id | varchar | 对应LangGraph checkpoint线程 |
| langgraph_checkpoint_id | varchar | LangGraph checkpoint ID |
| node_label | varchar | 节点标签（业务可读） |
| created_at | timestamp | |

> 注：checkpoint的实际状态数据由LangGraph的 `PostgresSaver` 持久化，本表仅做业务侧的快速索引，用于前端"查看历史检查点"列表。

### 8.6 监督Agent决策日志 `supervisor_logs`
| 字段 | 类型 | 说明 |
|---|---|---|
| id | PK | UUID |
| workflow_id | FK | |
| node_id | FK | |
| layer | varchar | hard_rule/soft_semantic/state_machine |
| quality_pass | bool | |
| issues | jsonb | 问题列表 |
| suggestion | jsonb | 建议指令 |
| model | varchar | |
| token_cost | int | |
| created_at | timestamp | |

---

## 9. API设计要点

### 9.1 账号
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/account/login/qrcode` | 生成扫码登录二维码 |
| GET | `/api/account/login/status` | 轮询登录状态 |
| GET | `/api/account/status` | 查询当前绑定账号状态 |
| POST | `/api/account/unbind` | 解绑账号 |

### 9.2 工作流
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/workflow/start` | 发起工作流(传theme/keyword) |
| GET | `/api/workflow/{id}` | 查询工作流详情 |
| GET | `/api/workflow/{id}/nodes` | 查询所有节点状态 |
| POST | `/api/workflow/{id}/rollback` | 回退(传target_node, scope) |
| POST | `/api/workflow/{id}/terminate` | 终止工作流 |
| WS | `/api/ws/workflow/{id}` | WebSocket订阅状态推送 |

### 9.3 节点审核
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/node/{id}/review` | 提交审核结果(pass/reject/edit) |
| POST | `/api/node/{id}/retry` | 重跑节点 |
| POST | `/api/node/{id}/upload-image` | 上传自有图片替换 |
| PATCH | `/api/node/{id}/content` | 手动编辑节点内容 |

### 9.4 MCP代理
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/mcp/search` | 代理调用MCP搜索(内部用) |
| POST | `/api/mcp/publish` | 代理调用MCP发布 |

---

## 10. MVP边界与二期规划

### 10.1 MVP包含
- 扫码登录 + 单账号
- 固定线性工作流（6+1 Agent）
- 硬规则+软语义+状态机三层监督
- 可视化流程图 + 回退 + 人工审核
- WebSocket异步推送 + 离线审核提醒
- DeepSeek-V3/R1 + Qwen-VL + 通义万相/即梦
- MCP发布集成

### 10.2 MVP不包含（二期）
- 多账号切换（DB已预留）
- 工作流DAG用户可视化编辑
- 跨任务记忆 / 向量库 / 爆款模式学习
- 工作流模板保存与复用
- 多工作流并发
- 数据看板（成本/爆款率统计）
- 团队协作

### 10.3 三期（远期）
- SaaS多租户
- 账号矩阵管理
- 跨平台发布（抖音/微博）

---

## 11. 风险矩阵与应对

| 风险 | 等级 | 影响 | 应对 |
|---|---|---|---|
| 小红书MCP发布不稳定/封控 | 高 | 发布失败率高 | 重试机制+备用方案；MCP服务做成可替换适配器；监控发布成功率 |
| 扫码登录Token失效 | 中 | 无法发布 | 自动刷新+失效告警+引导重新扫码 |
| DeepSeek-R1文案质量不达标 | 中 | 内容不可用 | Prompt工程迭代；保留切V3降级；人工终审兜底 |
| Qwen-VL图片理解偏差 | 中 | 视觉标签不准 | 多图交叉验证；人工审图环节兜底 |
| 生图模型版权/合规 | 中 | 侵权风险 | 只分析不存原图；生图prompt避免直接复刻 |
| 工作流长时执行用户流失 | 低 | 体验差 | 异步+WebSocket+离线通知 |
| 监督Agent软语义误判 | 中 | 错误回退建议 | 建议权非执行权；用户可忽略建议 |
| Token成本失控 | 中 | 费用超支 | 模型分级路由；硬规则零成本；监控Token消耗 |
| 工作流状态不一致 | 低 | 回退后数据错乱 | LangGraph原生checkpoint保证一致性 |
| LangGraph版本升级破坏兼容 | 低 | 编排层失效 | 锁定版本；封装薄适配层隔离API变更 |
| Recovery死循环 | 中 | Token/资源耗尽 | 三层兜底：max_attempts=3 + 熔断器 + 30分钟超时挂起 |
| 挂起任务占用资源 | 中 | Worker池耗尽 | 挂起即释放Worker；定时拉起依赖检查后才重新占用 |
| 用户长期不响应结构性恢复 | 中 | 任务永久挂起 | 30分钟超时挂起+定时拉起+用户可手动恢复；超过N天自动terminated |

---

## 12. 附录

### 12.1 关键决策溯源
本PRD的所有核心决策来自产品经理与需求方的深度讨论，关键决策记录于第2.4章，共17项（D1-D17），均为双方确认锁定。其中D13/D14/D15/D17为技术架构层决策，详细落地见《技术架构设计文档》；D16为前端体验层决策，详细落地见《前后端通信协议》第5.7章与《前端样式规范》第7.10章。

### 12.2 开放问题（待二期或研发中解决）
- 生图模型默认选通义万相还是即梦，需A/B测试
- 监督Agent软语义的`severity`阈值如何调参
- LangGraph checkpoint保留策略（PostgresSaver滚动保留 vs 全量保留）
- 挂起任务的"自动terminated"阈值（N天未响应，N=7？）
- 熔断器failure_threshold和recovery_timeout的初始值需根据实际负载调参

### 12.3 参考资料
- xiaohongshu-mcp-py（社区小红书MCP实现）
- DeepSeek API文档
- 阿里云百炼（Qwen-VL / 通义万相）文档
- VueFlow文档
- FastAPI WebSocket文档
- LangGraph文档（StateGraph / Checkpoint / Human-in-the-loop）
- langchain-core `@tool` 文档

---

**文档结束。技术架构层落地详见同目录《技术架构设计文档》。**
