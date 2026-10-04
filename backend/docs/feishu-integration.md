# 飞书集成方案

## 1. 目标

将飞书作为外部数据源和消息通道接入多智能体小红书创作平台，实现：

- **飞书笔记 → 创作素材**：通过飞书机器人指令，将飞书文档/笔记导入平台作为创作材料
- **平台数据 → 飞书**：将平台生成的选题、文案、分析结果推送到飞书文档/多维表格，方便学习归档
- **飞书机器人交互**：在飞书群内通过 @机器人 发送指令，触发平台工作流

## 2. 技术选型

| 项目 | 选择 | 理由 |
|------|------|------|
| SDK | `lark-oapi` (官方 Python SDK) | 官方维护、类型完整、API 覆盖全 |
| 认证方式 | 自建应用 (App) | 支持 tenant_access_token，适合服务端调用 |
| 消息接收 | Webhook 回调 | 飞书开放平台配置事件订阅，推送消息到后端 |
| 文档读取 | docx API | 获取飞书文档内容（Markdown 格式） |
| 数据导出 | bitable API | 写入多维表格，结构化存储选题/文案数据 |

## 3. 模块划分

```
backend/app/
├── adapters/
│   └── feishu.py              # 飞书 SDK 适配器（封装所有 API 调用）
├── rpa/
│   └── feishu_bot.py          # 飞书机器人引擎（生命周期、消息路由）
├── api/routers/
│   └── feishu_bot.py          # API 路由（RESTful 控制接口 + Webhook 回调）
└── config.py                  # 新增飞书配置项
```

### 3.1 适配器层 `adapters/feishu.py`

**职责**：封装 `lark-oapi` SDK，提供类型安全的高级 API

```python
class FeishuClient:
    """飞书适配器：封装 lark-oapi SDK 调用"""
    
    def __init__(self, app_id: str, app_secret: str): ...
    
    # 消息
    async def send_text(self, receive_id: str, text: str, receive_type="chat_id") -> dict: ...
    async def send_card(self, receive_id: str, card: dict, receive_type="chat_id") -> dict: ...
    
    # 文档
    async def get_document_content(self, document_id: str) -> str: ...      # 返回 Markdown
    async def get_wiki_node(self, wiki_token: str) -> dict: ...             # 知识库节点
    
    # 多维表格
    async def list_bitable_records(self, app_token: str, table_id: str, filter_str="") -> list: ...
    async def create_bitable_record(self, app_token: str, table_id: str, fields: dict) -> dict: ...
    async def batch_create_bitable_records(self, app_token: str, table_id: str, records: list) -> list: ...
```

**设计原则**：
- 所有方法均为 async，与 FastAPI 异步架构一致
- 统一错误处理：SDK 返回非 0 时抛出 `FeishuAPIError`
- 适配器不包含业务逻辑，仅做 API 映射

### 3.2 机器人引擎层 `rpa/feishu_bot.py`

**职责**：管理飞书机器人生命周期、消息路由、指令分发

```python
class FeishuBotEngine:
    """飞书机器人引擎"""
    
    def __init__(self, client: FeishuClient, verification_token: str, encrypt_key: str): ...
    
    # 生命周期
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    
    # 消息处理
    async def handle_event(self, event_data: dict) -> None: ...   # 处理飞书回调事件
    async def handle_command(self, chat_id: str, command: str, args: str) -> None: ...  # 指令分发
    
    # 业务桥接
    async def import_document(self, document_id: str) -> dict: ...   # 导入飞书文档到平台
    async def export_to_bitable(self, data: list, table_id: str) -> dict: ...  # 导出到多维表格
    
    @property
    def is_running(self) -> bool: ...
```

**指令设计**（@机器人 触发）：
- `/import <文档链接>` — 导入飞书文档作为创作素材
- `/export <选题/文案ID>` — 导出指定内容到飞书多维表格
- `/status` — 查看机器人状态

### 3.3 API 路由层 `api/routers/feishu_bot.py`

**职责**：提供 RESTful 控制接口 + Webhook 回调端点

```
POST /api/feishu/webhook          — 飞书事件回调（飞书开放平台推送）
POST /api/feishu/start            — 启动机器人
POST /api/feishu/stop             — 停止机器人
GET  /api/feishu/status           — 查询状态
POST /api/feishu/send-message     — 发送消息
POST /api/feishu/import-document  — 手动导入文档
POST /api/feishu/export-to-bitable — 手动导出到多维表格
```

## 4. 配置项

```ini
# ===== 飞书集成 =====
FEISHU_APP_ID=               # 飞书自建应用 App ID
FEISHU_APP_SECRET=            # 飞书自建应用 App Secret
FEISHU_VERIFICATION_TOKEN=    # 事件订阅验证令牌
FEISHU_ENCRYPT_KEY=           # 事件订阅加密密钥
FEISHU_BITABLE_APP_TOKEN=     # 默认多维表格 App Token
FEISHU_BITABLE_TABLE_ID=      # 默认多维表格 Table ID
```

## 5. 实施步骤

### Step 1: 配置层 — 在 config.py 添加飞书配置项 ✅
- 添加 `feishu_*` 字段到 Settings
- 更新 `.env.example`
- **测试**：启动后端确认无 import 错误，配置项可读取

### Step 2: 适配器层 — 创建 adapters/feishu.py ✅
- 实现 FeishuClient 类骨架
- 安装 `lark-oapi` 依赖
- **测试**：导入模块无报错，FeishuClient 可实例化

### Step 3: 机器人引擎层 — 创建 rpa/feishu_bot.py ✅
- 实现 FeishuBotEngine 类骨架
- 注册表模式（按用户隔离）
- **测试**：引擎可创建、启动/停止状态切换正常

### Step 4: API 路由层 — 创建 api/routers/feishu_bot.py ✅
- 实现 RESTful 控制接口
- 实现 Webhook 回调端点
- 注册到 main.py
- **测试**：API 接口可访问，返回正确格式

### Step 5: lifespan 集成 + 端到端验证 ✅
- 在 main.py lifespan 中添加飞书初始化步骤（step 5.8）
- 后端启动成功，飞书路由在 OpenAPI 文档中可见
- Webhook challenge 验证正常
- 事件推送处理正常（processed=0 为预期，需先 /start 启动引擎）
- **测试**：后端启动无报错，所有 7 个飞书 API 端点正常响应

### Step 6: 真实飞书应用验证（待用户配置凭证后执行）
- 在 .env 中配置 FEISHU_APP_ID / FEISHU_APP_SECRET
- 在飞书开放平台创建自建应用，配置事件订阅 URL
- 验证消息发送、文档读取、表格写入
- **测试**：完整流程跑通

## 6. 可维护性设计

1. **适配器模式**：FeishuClient 与业务解耦，SDK 升级只改适配器
2. **注册表模式**：按用户 ID 隔离引擎实例，支持多用户并发
3. **事件驱动**：通过 EventBus 发布飞书事件，其他模块订阅处理
4. **配置外部化**：所有凭证走环境变量，不硬编码
5. **渐进式集成**：骨架先跑通，功能逐步填充，每步可测试