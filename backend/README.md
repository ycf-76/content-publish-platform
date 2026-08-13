# 多智能体小红书发布平台 - 后端

## 概述

基于 FastAPI + LangGraph + 自研 Harness + MCP + Recovery 子系统的小红书内容自动化生产平台后端。

对应文档：
- 产品需求：`../PRD.md`
- 架构设计：`../技术架构设计文档.md`
- 通信协议：`../前后端通信协议.md`
- 开发红线：`../开发红线手册.md`

## 技术栈

| 组件 | 选型 |
|---|---|
| Web 框架 | FastAPI (Python 3.11+) |
| 编排层 | LangGraph (StateGraph + conditional_edges) |
| Agent 运行时 | 自研 Harness（子包结构） |
| LLM | DeepSeek-V3 (default) + DeepSeek-R1 (copywrite only) |
| 多模态 | Qwen-VL (图片理解) |
| 图片生成 | 通义万相 / 即梦 |
| MCP | 浏览器插件（主） + uv run（备） |
| 数据库 | PostgreSQL (asyncpg) |
| 实时通信 | SSE + HTTP POST 双通道（禁用 WebSocket） |
| Checkpoint | PostgresSaver（禁用 MemorySaver） |

## 目录结构

```
backend/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                  # 全局配置（pydantic-settings）
│   ├── account/                   # 账号绑定 + 扫码登录
│   ├── agents/                    # Agent 层
│   │   ├── graph.py               # LangGraph 编排（Layer A）
│   │   ├── state.py               # WorkflowState TypedDict
│   │   ├── adapters/              # LLM/VL/ImageGen 适配器
│   │   ├── core/harness/          # 自研 Harness（Layer B）
│   │   │   ├── runtime.py
│   │   │   ├── executor/          # single_shot / loop
│   │   │   ├── memory/
│   │   │   ├── observer/          # D16 过程透明
│   │   │   └── recovery/          # Recovery 子系统
│   │   ├── harnesses/             # Harness 工厂
│   │   ├── prompts/               # Prompt 模板
│   │   ├── skills/                # Skill 能力（Layer C）
│   │   │   ├── mcp/               # MCP Client Manager
│   │   │   └── ...
│   │   └── configs/               # Agent YAML 配置
│   ├── api/                       # FastAPI 路由
│   │   ├── routers/
│   │   └── schemas/
│   ├── crypto/                    # AES-GCM 加密
│   ├── db/                        # SQLAlchemy ORM
│   └── services/                  # 服务层
│       ├── workflow.py            # 工作流编排服务
│       ├── sse_bus.py             # SSE 事件总线
│       ├── recovery_service.py    # Recovery 决策服务
│       └── ...
├── scripts/
│   ├── manual_test.py             # 端到端手动验证脚本
│   └── redline_check.py           # 红线自检脚本
├── tests/
│   ├── test_minimal_flow.py       # 最小闭环测试
│   └── mocks/                     # Mock 适配器
├── .env.example
├── run_server.py
└── pyproject.toml
```

## 环境准备

### 1. 创建虚拟环境

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. 安装依赖

```powershell
pip install -r requirements.txt
```

### 3. 配置环境变量

```powershell
Copy-Item .env.example .env
# 编辑 .env，填入真实 API Key
```

关键字段（详见 `.env.example`）：

| 变量 | 必填 | 说明 |
|---|---|---|
| `DATABASE_URL` | 是 | PostgreSQL 异步连接串 |
| `DEEPSEEK_API_KEY` | 是 | DeepSeek API Key |
| `DASHSCOPE_API_KEY` | 是 | 阿里云百炼 API Key（Qwen-VL + 通义万相） |
| `XHS_MCP_MODE` | 否 | `plugin` / `local` / `disabled`（默认 plugin） |
| `XHS_MCP_PLUGIN_URL` | 否 | 浏览器插件 MCP 服务地址 |
| `AES_SECRET_KEY` | 是 | 32 字节 base64，加密小红书 Token |
| `JWT_SECRET_KEY` | 是 | JWT 签名密钥 |
| `CORS_ORIGINS` | 否 | 前端域名白名单（默认 localhost:5173） |

## 启动命令

### 开发服务器

```powershell
.\.venv\Scripts\python.exe run_server.py
```

服务监听 `http://127.0.0.1:8007`，API 文档 `http://127.0.0.1:8007/docs`。

### 直接 uvicorn

```powershell
.\.venv\Scripts\uvicorn.exe app.main:app --host 0.0.0.0 --port 8007 --reload
```

## 测试命令

### 单元测试

```powershell
$env:DATABASE_URL="sqlite+aiosqlite:///./xhs_platform_test.db"
$env:DEEPSEEK_API_KEY=""
$env:DASHSCOPE_API_KEY=""
$env:PERMISSIONS_ALLOW=""
.\.venv\Scripts\python.exe -m pytest tests/ -v
```

### 端到端手动验证

```powershell
.\.venv\Scripts\python.exe scripts\manual_test.py --topic "科技" --timeout 25
```

事件流落盘 `manual_test_events.json`。

### 红线自检

```powershell
.\.venv\Scripts\python.exe scripts\redline_check.py
```

检查 7 项硬红线：harness 不 import langgraph / 禁用 WebSocket / 禁用 MemorySaver / copywrite 用 R1 / 监督用 V3 / Token 加密 / User:Account 1:N。

## API 概览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/workflows` | 启动新工作流 |
| GET | `/api/workflows/{id}` | 查询工作流状态 |
| POST | `/api/workflows/{id}/pause` | 暂停 |
| POST | `/api/workflows/{id}/resume` | 恢复 |
| POST | `/api/workflows/{id}/terminate` | 终止 |
| POST | `/api/workflows/{id}/rollback` | 回退到指定节点 |
| POST | `/api/workflows/{id}/reviews/{review_id}` | 提交人工审核结果 |
| GET | `/api/sse/workflow/{id}` | 订阅 SSE 事件流 |
| GET | `/api/accounts` | 列出已绑定小红书账号 |
| POST | `/api/accounts/check-plugin` | 查询浏览器插件登录态 |
| POST | `/api/accounts/qrcode` | 生成扫码登录二维码 |
| POST | `/api/accounts/qrcode/{qr_id}/poll` | 轮询扫码状态 |
| POST | `/api/accounts/qrcode/{qr_id}/confirm` | 确认扫码登录 |
| POST | `/api/accounts/bind` | 绑定账号 |
| POST | `/api/recovery/suggestions/{id}/confirm` | 用户确认结构性恢复 |
| POST | `/api/recovery/suggestions/{id}/reject` | 用户拒绝结构性恢复 |
| POST | `/api/recovery/workflows/{id}/resume-from-suspension` | 用户主动恢复挂起工作流 |

## 工作流节点

固定线性流程（MVP 不可拖拽）：

```
search → analyze → quality_check_analyze → image_gen → image_review
       → copywrite → quality_check_copywrite → audit → quality_check_audit
       → final_review → publish
```

- `quality_check_*`：软语义判断节点（D14 分散式守卫），用 V3 评估上游产出质量
- `image_review` / `final_review`：人工审核节点（`interrupt_before`）
- 软语义 fail 时路由到 END，workflow 进入 `suspended` 状态，等待用户拍板

## 已知限制（MVP 边界）

1. **单工作流**：不支持多工作流并发（DB 已预留 user_id 索引）
2. **单账号前端**：DB 已支持 1:N，前端只展示单账号
3. **固定流程**：8 个业务节点 + 3 个软语义节点，不可拖拽编排
4. **LangGraph Checkpoint**：MVP 阶段 in-memory（`checkpointer=None`），生产需启用 PostgresSaver
5. **LLM 可选**：未配置 `DEEPSEEK_API_KEY` 时软语义自动放行，业务节点走 fallback output
6. **MCP 双模式**：浏览器插件（主） + uv run（备），未配置时 `XHS_MCP_MODE=disabled`
7. **SSE 多实例**：当前 SSE 事件总线是进程内 dict，多实例部署需替换为 Redis Pub/Sub
8. **多账号扫码**：扫码登录通过独立 Playwright Worker 进程，避免与 uvicorn 事件循环冲突
