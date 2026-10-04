# Pulse Studio 开发路线图

> 日期: 2026-09-02
> 定位: AI 式的内容创作平台
> 策略: 渐进桌面化 — 先 web 上线验证，再 Tauri 套壳做桌面版

---

## 一、项目定位

### 1.1 一句话定位

**Pulse Studio 是 AI 式的内容创作平台。用户一句话给出意图，多智能体自主跑完从选题到发布的全流程。**

### 1.2 核心能力

| 能力 | 说明 |
|------|------|
| 意图解析 | TopPlanner 一次 LLM 调用，同时输出工具选择 + 执行策略 + 上下文理解 |
| Skill 链执行 | LoopExecutor ReAct 循环（max_iterations=12），按序/按需调用独立 Skill |
| 全过程透明 | SSE 流式推送思考过程和工作流进度到前端 |
| 三层分析 | 规则层筛选 + LLM 模式识别 + LLM 深度归因 |
| 工具集 | bash/glob/grep/file_read/file_write，PathGuard 工作区沙箱 + 命令白名单 |
| 插件扩展 | MCP 协议桥，支持动态接入外部 Skill |

### 1.3 核心价值主张

LLM 通过工具链（搜索 → 分析 → 文案 → 图片 → 审核 → 发布）自主完成从选题到发布的全流程，用户像聊天一样指挥多智能体完成创作。

---

## 二、当前状态（2026-09-02）

### 2.1 已完成

- ✅ 多智能体对话式工作流（TopPlanner 意图解析 → Skill 链执行）
- ✅ SSE 流式推送（思考过程 + 工作流进度）
- ✅ 三层分析架构（规则层筛选 + LLM 模式识别 + LLM 深度归因）
- ✅ 作品上下文注入（WorkContext 传递到分析工具）
- ✅ LoopExecutor ReAct 工作流（max_iterations=12，空 thought 兜底）
- ✅ 工具链：搜索/分析/文案/图片/审核/发布/视频制作
- ✅ MCP 插件桥（Chrome 扩展 + 本地代理）
- ✅ 工作流可视化编辑器（Vue Flow）
- ✅ 多平台支持（小红书/抖音/B站/微信/Instagram/Threads）

### 2.2 待解决

- ✅ BashSkill 白名单已收紧（删 python/node/pip/npm/npx + 拦截 -exec 绕过 + PathGuard 默认隔离到 data/workspace）
- ⚠️ 项目品牌名已改为"多智能体内容创作与发布平台"，但 README 未更新
- ⚠️ 未部署上线（无公网演示链接）
- ⚠️ 无桌面端（LLM 无法操作本地素材）

---

## 三、开发路线图

### 阶段 1：Web 版上线（当前优先级 P0）

**目标**: 把现有 web 版做扎实，部署上线，能投简历、能演示。

**工期**: 1 周

**任务清单**:

- [x] **P0-1 安全收紧**: BashSkill 白名单删除 `python`/`node`/`pip`/`npm`/`npx`，保留 `git`/`ffmpeg`/`ls`/`cat`/`find`/`grep` 等只读或专用工具；额外拦截 `-exec`/`-execdir`/`-ok` 防白名单绕过；PathGuard 默认隔离到 `data/workspace/` 防读到 `.env`
- [ ] **P0-2 部署上线**: Docker 化后端 + 前端，部署到轻量云服务器（阿里云学生机），提供公网演示链接
- [ ] **P0-3 README 重写**: 按"面向内容创作的 AI 智能体平台"定位重写，包含架构图、演示视频、技术栈
- [ ] **P0-4 演示视频**: 录制 2 分钟全流程演示（登录 → 对话 → 分析 → 文案 → 图片 → 发布）
- [ ] **P0-5 简历项目描述**: 按"Cursor for Content"定位撰写，突出多智能体工作流 + 安全设计

**验收标准**:
- 公网链接可访问，面试官点开能看
- README 顶部有演示视频
- 简历项目描述能讲清楚定位

---

### 阶段 2：桌面版 v2（拿到面试后启动）

**目标**: Tauri 套壳做桌面版，让 LLM 能真正操作本地素材，对标 Cursor 桌面端。

**工期**: 2 周

**任务清单**:

#### 2.1 架构改造

- [ ] **P1-1 Tauri 壳搭建**: 初始化 Tauri 项目，配置 `tauri.conf.json`，前端 `dist` 嵌入
- [ ] **P1-2 后端进程托管**: PyInstaller 打包 FastAPI 为单 exe，Tauri 启动时拉起子进程
- [ ] **P1-3 端口协商**: 后端启动随机端口，写 stdout，Tauri 读后注入前端 `window.__BACKEND_URL__`
- [ ] **P1-4 前端适配**:
  - vue-router: `history` → `hash` 模式
  - axios baseURL: 硬编码 → 运行时注入
  - Vite base: `/` → `./`（相对路径）
  - public/icons 路径: 绝对 → 相对
- [ ] **P1-5 数据库切换**: MySQL → SQLite（`session.py` 已支持，改 `DATABASE_URL` 即可）
- [ ] **P1-6 配置存储**: `.env` → 用户数据目录 `config.json`（Windows: `%APPDATA%/PulseStudio/`）
- [ ] **P1-7 凭证加密**: 小红书 cookie → Windows Credential Manager（钥匙串）

#### 2.2 桌面端能力增强

- [ ] **P2-1 本地素材库**: LLM 能扫描本地目录，读取图片/视频/音频素材
- [ ] **P2-2 本地命令执行**: bash 工具在桌面端真正可用（ffmpeg 做封面、SD 生成图片）
- [ ] **P2-3 本地模型接入**: 支持调本地 Stable Diffusion / LLaVA（localhost）
- [ ] **P2-4 文件落盘**: 生成结果直接写本地，不再走"下载"

#### 2.3 体验优化

- [ ] **P3-1 启动闪屏**: FastAPI 冷启动 3-8 秒，需 splash window + 进度提示
- [ ] **P3-2 崩溃恢复**: 子进程崩溃检测 + 自动重启 + 错误上报
- [ ] **P3-3 系统托盘**: 常驻后台，关闭窗口最小化到托盘
- [ ] **P3-4 自动更新**: Tauri updater + GitHub Release

#### 2.4 打包发布

- [ ] **P4-1 PyInstaller 打包**: 后端打成单 exe，处理隐式依赖（LangGraph/SQLAlchemy 动态 import）
- [ ] **P4-2 Tauri bundle**: 生成 msi/nsis 安装包
- [ ] **P4-3 代码签名**: Windows 证书，避免 SmartScreen 拦截

**验收标准**:
- 双击安装包能装上
- 启动后能跑通"对话 → 分析 → 发布"闭环
- LLM 能读取本地素材目录
- LLM 能调本地 ffmpeg 做封面

---

### 阶段 3：双版本分化（长期）

**目标**: web 版和桌面版定位分化，服务不同用户群。

| 版本 | 目标用户 | 核心能力 |
|------|---------|---------|
| Web 版 | 云端创作用户 | 素材在平台，不碰本地，浏览器即用 |
| 桌面版 | 重度创作用户 | 素材在本地，跑 ffmpeg/SD，多账号本地管理 |

**任务清单**:

- [ ] **P5-1 功能开关**: 桌面版启用本地文件操作，web 版禁用
- [ ] **P5-2 配置同步**: 两版配置可互通（可选）
- [ ] **P5-3 插件市场**: 外部 Skill 可上架，用户一键安装（importlib 动态加载）

---

## 四、技术决策记录

### 4.1 为什么先 web 后桌面

1. **验证优先**: web 版能快速验证产品逻辑，桌面化是工程优化不是产品验证
2. **简历友好**: web 版有公网链接可演示，桌面版要下载安装，面试官大概率不装
3. **风险控制**: 桌面化有不可控坑（PyInstaller 隐式依赖、SSE 在 webview 行为、路径问题），不应在简历冲刺期冒险

### 4.2 为什么选 Tauri 不选 Electron

| 维度 | Tauri | Electron |
|------|-------|----------|
| 体积 | 10MB 级 | 100MB+ |
| 内存 | 低 | 高 |
| 安全 | Rust 壳，默认禁用 Node 集成 | Node 集成，历史漏洞多 |
| 生态 | 新但够用 | 成熟 |
| 面试加分 | Rust 壳是技术亮点 | 太常见 |

**结论**: Tauri。体积小、安全好、Rust 壳是简历加分项。

### 4.3 为什么 bash 工具收紧不删除

- **保留理由**: 桌面版需要 LLM 跑本地命令（ffmpeg/git），这是"Cursor for Content"定位的核心能力
- **收紧理由**: 白名单里的 `python`/`node` 是任意代码执行入口，`python -c "import os; os.system('...')"` 能绕过所有防护
- **决策**: 删 5 个危险命令，保留只读/专用工具，桌面版才真正发挥价值

### 4.4 为什么数据库用 SQLite 不用 MySQL

- 桌面版单机免安装，用户不应被迫装 MySQL
- `session.py` 已做 SQLite/MySQL 双兼容，迁移成本几乎为零
- SQLite 单文件，方便打包和用户数据迁移

### 4.5 为什么登录方式保留小红书扫码

- 现有账号体系就是小红书账号，改了要重写后端
- 小红书作为"支持平台之一"保留，不改登录方式
- 桌面版可后续加"本地账号"模式（免登录用本地模型）

---

## 五、面试话术

### 5.1 项目一句话介绍

> Pulse Studio 是 AI 式的内容创作平台。用户一句话给出意图，多智能体自主跑完从选题到发布的全流程。

### 5.2 为什么做这个

> 我想做一个 AI 式的内容创作平台：用户一句话给出意图，多智能体自主跑完选题到发布。先做了 web 版快速验证产品逻辑，后续计划用 Tauri 套壳做桌面版，让 LLM 能操作本地素材（ffmpeg 做封面、本地图片库），这是 web 做不到的。

### 5.3 技术亮点

1. **TopPlanner 意图解析**: LLM 识别用户意图，生成工具调用计划
2. **Skill 链执行**: 按序调用独立 Skill 完成分析任务（ReAct 风格）
3. **SSE 流式推送**: 实时推送思考过程和工作流进度到前端
4. **三层分析架构**: 规则层筛选 + LLM 模式识别 + LLM 深度归因
5. **安全设计**: 命令白名单 + shlex 解析 + PathGuard 工作区沙箱
6. **MCP 协议**: 插件化扩展，支持动态接入外部 skill

### 5.4 安全设计讲法

> bash 工具让 LLM 自己拼命令字符串执行，有提示词注入风险——即使白名单里有 python，`python -c` 就能绕过所有防护。所以我把白名单里的 python/node/pip/npm/npx 删掉，只保留只读或专用工具（git/ffmpeg/ls/cat）。所有命令行需求优先写成专用 Skill，命令由代码拼，LLM 只传业务参数，从根上杜绝注入。

---

## 六、风险与对策

| 风险 | 概率 | 影响 | 对策 |
|------|------|------|------|
| PyInstaller 隐式依赖打包失败 | 高 | 桌面版不可用 | 逐个补 `--hidden-import`，用 `pyinstaller --debug` 排查 |
| SSE 在 Tauri webview 行为异常 | 中 | 流式推送失效 | 改用 Tauri 的 IPC 事件，或 WebSocket |
| 冷启动慢（3-8 秒黑屏） | 高 | 体验差 | splash window + 进度提示 + 预编译 `.pyc` |
| Windows SmartScreen 拦截 | 中 | 用户不敢装 | 代码签名（需购买证书） |
| 本地素材路径权限 | 低 | LLM 读不到 | Tauri fs API + 用户授权对话框 |

---

## 七、里程碑

| 里程碑 | 目标日期 | 验收 |
|--------|---------|------|
| M1: Web 版上线 | 2026-09-09 | 公网链接可访问，README 完成 |
| M2: 简历投递 | 2026-09-10 | 项目描述按定位写好 |
| M3: 桌面版 v2 启动 | 拿到面试后 | Tauri 壳跑通最小闭环 |
| M4: 桌面版发布 | M3 后 2 周 | 安装包可双击安装，跑通全流程 |

---

## 八、附录

### 8.1 相关文档

- [skills-architecture.md](./skills-architecture.md) — Skill 架构设计
- [DEV_TOOLS_GUIDE.md](./DEV_TOOLS_GUIDE.md) — 开发工具指南
- [PLUGIN_SDK_GUIDE.md](./PLUGIN_SDK_GUIDE.md) — 插件 SDK 指南
- [fix-plan-2026-08-31.md](./fix-plan-2026-08-31.md) — 全面修复计划

### 8.2 技术栈

- **前端**: Vue3 + Vite + Pinia + Vue Router + Vue Flow + TipTap + TailwindCSS
- **后端**: FastAPI + SQLAlchemy + LangGraph + MCP 协议
- **AI**: OpenAI / Claude / 本地模型（桌面版）
- **数据库**: MySQL（web） / SQLite（桌面）
- **部署**: Docker（web） / Tauri + PyInstaller（桌面）

---

> 本文档随开发进度持续更新。每完成一个阶段任务，勾选对应 checkbox 并记录实际工期。