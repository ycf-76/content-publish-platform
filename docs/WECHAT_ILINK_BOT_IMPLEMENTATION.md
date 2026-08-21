# 微信 iLink Bot 集成方案

> 基于 SiverKing/weixin-ClawBot-API 官方项目核心思路实现
> 
> **版本**: v1.0 (2026-08-19)
> **状态**: 待实施
> **参考项目**: https://github.com/SiverKing/weixin-ClawBot-API

---

## 📌 一、项目背景与目标

### 1.1 为什么选择 iLink Bot 协议？

| 对比项 | itchat (旧) | weixin-agent-sdk (失败) | **iLink Bot (本方案)** |
|--------|------------|----------------------|---------------------|
| 官方性 | ❌ 第三方逆向 | ❌ 第三方SDK | ✅ **腾讯官方API** |
| 封号风险 | ⚠️ 高 | ⚠️ 不确定 | ✅ **无风险** |
| 代码复杂度 | 中等 | 高(踩坑多) | ✅ **极简(300行核心)** |
| 文档质量 | 一般 | 几乎没有 | ✅ **完善+有参考实现** |
| 功能完备性 | 基础 | 不稳定 | ✅ **完整(文本/图片/文件)** |

### 1.2 核心目标

✅ **基础功能**（Phase 1）
- 二维码扫码登录
- 消息接收（长轮询模式）
- 消息发送（手动控制）

✅ **高级功能**（Phase 2-3）
- AI对话（对接DeepSeek/Claude）
- 内容推送（打包卡片/文章→微信）
- 任务交互（微信指令触发发布流程）

### 1.3 技术架构

```
┌──────────────────────────────────────────────────────────────┐
│                    完整数据流架构                              │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  微信用户                                                     │
│    ↓ 发送"你好"                                               │
│                                                              │
│  腾讯 iLink 服务器 (https://ilinkai.weixin.qq.com)            │
│    ↓ POST /ilink/bot/getupdates (长轮询35秒)                 │
│                                                              │
│  WeChatILinkClient (Python HTTP客户端)                        │
│    ↓ 解析消息 → 提取 text/from_user_id/context_token         │
│                                                              │
│  ════════════════════════════════════════                   │
│  ⭐ Pulse Studio 业务逻辑层                                  │
│  ════════════════════════════════════════                   │
│                                                              │
│  后端 API (/api/wechat/receive)                               │
│    ↓ 处理业务逻辑 + AI对话                                   │
│    ↓ 返回: { reply: "回复内容" }                             │
│                                                              │
│  WeChatILinkClient                                            │
│    ↓ POST /ilink/bot/sendmessage (带context_token)           │
│                                                              │
│  腾讯 iLink 服务器                                            │
│    ↓ 投递消息                                                │
│                                                              │
│  微信用户 ← 收到回复                                          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔧 二、核心技术要点（从官方项目学习）

### 2.1 iLink Bot 协议 - 6个核心API

#### **认证相关**
```python
BASE_URL = "https://ilinkai.weixin.qq.com"

# 必须的请求头（每次请求都要带！）
def make_headers(token=None):
    uin = str(random.randint(0, 0xFFFFFFFF))
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",                    # 固定值！
        "X-WECHAT-UIN": base64.b64encode(uin.encode()).decode(),   # 每次必须不同！
        "iLink-App-Id": ILINK_APP_ID,                              # 应用ID
        "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION,       # 客户端版本
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"               # 登录后必带！
    return headers
```

#### **API接口清单**
| 接口 | 方法 | 用途 | 关键参数 |
|------|------|------|----------|
| `/ilink/bot/get_bot_qrcode` | GET | 获取登录二维码 | `bot_type=3` |
| `/ilink/bot/get_qrcode_status` | GET | 轮询扫码状态 | `qrcode=xxx` |
| `/ilink/bot/getupdates` | POST | ⭐ 长轮询接收消息 | `get_updates_buf`, `base_info` |
| `/ilink/bot/sendmessage` | POST | ⭐ 发送消息 | `msg`(含context_token) |
| `/ilink/bot/sendtyping` | POST | 显示"正在输入..." | `typing_ticket`, `status` |
| `/ilink/bot/getconfig` | POST | 获取配置 | `ilink_user_id` |

### 2.2 登录流程（3步）

```python
async def login_with_qrcode(session, base_url=BASE_URL):
    """
    Step 1: 获取二维码
    """
    data = await api_get(session, "ilink/bot/get_bot_qrcode?bot_type=3")
    qrcode = data["qrcode"]
    qrcode_img_content = data.get("qrcode_img_content", "")  # Base64图片
    
    """
    Step 2: 轮询等待扫码确认
    """
    while True:
        status = await api_get(session, f"ilink/bot/get_qrcode_status?qrcode={qrcode}")
        
        if status.get("status") == "confirmed":
            return {
                "bot_token": status["bot_token"],          # ← 关键！后续所有请求用这个
                "baseurl": status.get("baseurl", base_url), # ← 可能会变！要用返回值
                "ilink_bot_id": status.get("ilink_bot_id"),
                "ilink_user_id": status.get("ilink_user_id"),
            }
        elif status.get("status") == "scaned":
            print("已扫码，等待手机确认...")
        elif status.get("status") == "expired":
            raise Exception("二维码过期，请重新获取")
            
        await asyncio.sleep(1)

"""
Step 3: 保存token，用于后续所有API调用
"""
```

### 2.3 消息收发机制

#### **接收消息（长轮询）**
```python
get_updates_buf = ""  # 断点续传缓冲区

while True:
    result = await api_post(
        session,
        "ilink/bot/getupdates",
        {
            "get_updates_buf": get_updates_buf,  # 用于断点续传，防止丢消息
            "base_info": {
                "channel_version": "1.0",
                "bot_agent": "pulse-studio-bot"
            }
        },
        bot_token  # Authorization: Bearer {token}
    )
    
    # 更新缓冲区
    get_updates_buf = result.get("get_updates_buf", get_updates_buf)
    
    # 解析消息列表
    for msg in result.get("msgs", []):
        if msg.get("message_type") != 1:  # 只处理文本消息
            continue
            
        text = msg["item_list"][0]["text_item"]["text"]
        from_user_id = msg["from_user_id"]
        context_token = msg["context_token"]  # ← 回复时必须带回！关键字段！
        
        print(f"[收到] {from_user_id}: {text}")
```

#### **发送消息**
```python
async def send_message(session, to_user_id, context_token, text, bot_token):
    client_id = f"pulse-studio-{random.randint(0, 0xFFFFFFFF):08x}"
    
    result = await api_post(
        session,
        "ilink/bot/sendmessage",
        {
            "msg": {
                "from_user_id": "",              # 发送者留空
                "to_user_id": to_user_id,        # 目标用户ID
                "client_id": client_id,          # 客户端唯一标识
                "message_type": 2,               # 2=文本消息
                "message_state": 2,              # 2=正常发送
                "context_token": context_token,   # ← 从接收的消息中获取！必须带回！
                "item_list": [{
                    "type": 1,                   # 1=文本类型
                    "text_item": {"text": text}
                }]
            },
            "base_info": {
                "channel_version": "1.0",
                "bot_agent": "pulse-studio-bot"
            }
        },
        bot_token
    )
    
    return result
```

### 2.4 关键技术细节

#### **为什么需要 context_token？**
- `context_token` 是每次会话的唯一标识
- **回复消息时必须带上**，否则发送失败
- 从接收到的消息中提取：`msg["context_token"]`
- **缓存策略**：按 `from_user_id` 缓存最新的 `context_token`

#### **X-WECHAT-UIN 的作用？**
- 随机生成的 uint32 数，转 base64
- **每次请求都必须不同**，用于防重放攻击
- 服务端会校验，相同值会被拒绝

#### **get_updates_buf 的作用？**
- 断点续传缓冲区
- 每次请求带上上次返回的值
- **作用**：确保不漏消息，即使网络中断也能恢复

#### **"正在输入..."效果如何实现？**
```python
# Step 1: 获取 typing_ticket（每个用户只需获取一次）
config_result = await api_post(session, "ilink/bot/getconfig", {
    "ilink_user_id": from_user_id,
    "context_token": context_token,
    "base_info": {...}
}, token)
typing_ticket = config_result.get("typing_ticket", "")

# Step 2: 显示"对方正在输入..."
await api_post(session, "ilink/bot/sendtyping", {
    "ilink_user_id": from_user_id,
    "typing_ticket": typing_ticket,
    "status": 1  # 1=显示, 2=取消
}, token)

# ... 处理AI回复 ...

# Step 3: 取消"正在输入..."
await api_post(session, "ilink/bot/sendtyping", {
    "status": 2
}, token)
```

---

## 📁 三、文件结构与模块设计

### 3.1 新建文件清单

```
backend/
├── app/
│   ├── rpa/
│   │   ├── wechat_ilink_client.py      # [新建] iLink协议HTTP客户端（核心）
│   │   └── wechat_bot_engine.py        # [新建] 机器人引擎（生命周期管理）
│   ├── api/
│   │   └── routers/
│   │       └── wechat_bot.py           # [新建] API路由接口
│   └── services/
│       └── wechat_message_handler.py   # [新建] 消息处理器（业务逻辑）
frontend/
├── src/
│   └── components/
│       └── WeChatBotToggle.vue         # [新建] 微信开关组件
└── public/
    └── test-wechat-ilink.html          # [新建] 测试页面
```

### 3.2 模块职责划分

#### **① `wechat_ilink_client.py` (核心客户端)**
```python
class WeChatILinkClient:
    """微信 iLink Bot HTTP客户端
    
    职责：
    - 封装所有 iLink API 调用
    - 管理登录流程（二维码、Token）
    - 消息收发底层实现
    - 会话管理（context_token缓存）
    
    设计原则：
    - 纯HTTP调用，无外部SDK依赖
    - 异步设计（asyncio + aiohttp）
    - 自动重连和错误恢复
    """
    
    async def get_qrcode(self) -> dict:
        """获取登录二维码"""
        pass
    
    async def login(self, qrcode: str) -> dict:
        """等待扫码确认，返回token"""
        pass
    
    async def poll_messages(self, callback):
        """持续监听消息（长轮询）"""
        pass
    
    async def send_text(self, to_user_id, context_token, text):
        """发送文本消息"""
        pass
    
    async def send_typing(self, to_user_id, typing_ticket, show=True):
        """显示/隐藏'正在输入...'"""
        pass
```

#### **② `wechat_bot_engine.py` (引擎管理)**
```python
class WeChatBotEngine:
    """微信机器人引擎
    
    职责：
    - 机器人生命周期管理（启动/停止/重启）
    - 状态维护（STOPPED/LOGGED_IN/ERROR等）
    - 单例模式，全局唯一实例
    - 对接后端业务逻辑
    - 前端WebSocket实时推送状态
    
    核心方法：
    - start()     : 启动服务，进入等待扫码状态
    - stop()      : 停止服务，清理资源
    - get_status(): 查询当前状态
    - send_message(): 主动发送消息（手动模式）
    """
    
    _instance = None  # 单例实例
    
    @classmethod
    def get_instance(cls):
        """获取单例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    async def start(self):
        """启动服务"""
        # 1. 创建 aiohttp session
        # 2. 调用 client.get_qrcode()
        # 3. 保存二维码到 state
        # 4. 启动后台任务监听扫码
        # 5. 更新状态为 WAITING_QR
    
    async def stop(self):
        """停止服务"""
        # 1. 设置停止标志
        # 2. 关闭session
        # 3. 清理状态
```

#### **③ `wechat_bot.py` (API接口)**
```python
router = APIRouter(prefix="/api/wechat", tags=["WeChat Bot"])

@router.post("/start")
async def start_service():
    """启动微信机器人服务"""
    engine = WeChatBotEngine.get_instance()
    await engine.start()
    return {"success": True}

@router.post("/stop")
async def stop_service():
    """停止服务"""
    engine = WeChatBotEngine.get_instance()
    await engine.stop()
    return {"success": True}

@router.get("/status")
async def get_status():
    """查询状态"""
    engine = WeChatBotEngine.get_instance()
    return {
        "success": True,
        "data": {
            "status": engine.state.status.value,
            "wxid": engine.state.wxid,
            "is_running": engine.is_running,
            "has_qrcode": bool(engine.state.qr_code_base64),
            "qrcode": engine.state.qr_code_base64  # Base64图片
        }
    }

@router.get("/qrcode")
async def get_qrcode():
    """获取二维码图片"""
    engine = WeChatBotEngine.get_instance()
    if engine.state.status != BotStatus.WAITING_QR:
        return {"success": False, "message": "暂无二维码"}
    
    return {
        "success": True,
        "data": {
            "qrcode": f"data:image/png;base64,{engine.state.qr_code_base64}",
            "expires_in": 120  # 有效期120秒
        }
    }

@router.post("/send")
async def send_message(request: SendMessageRequest):
    """主动发送消息"""
    engine = WeChatBotEngine.get_instance()
    if not engine.is_logged_in:
        raise HTTPException(500, "机器人未登录")
    
    result = await engine.send_message(request.to_wxid, request.content)
    return {"success": True, "data": result}

@router.websocket("/ws/status")
async def websocket_status(websocket: WebSocket):
    """WebSocket实时推送状态变化"""
    await websocket.accept()
    async for state in engine.state_stream():
        await websocket.send_json(state)
```

#### **④ `wechat_message_handler.py` (业务处理)**
```python
class WeChatMessageHandler:
    """消息处理器
    
    职责：
    - 接收微信消息并转发给业务层
    - 调用AI模型生成回复
    - 支持指令解析（/help /time等）
    - 内容打包和推送
    """
    
    async def handle_message(self, from_user_id, text, context_token):
        """处理收到的消息
        
        Args:
            from_user_id: 发送者ID
            text: 消息内容
            context_token: 会话令牌（回复时需要）
        
        Returns:
            str: 回复内容
        """
        # 1. 检查是否为指令
        if text.startswith("/"):
            return await self.handle_command(text)
        
        # 2. AI对话（调用DeepSeek）
        reply = await self.call_ai_model(from_user_id, text)
        
        # 3. 记录日志
        logger.info(f"[消息处理] {from_user_id}: {text} -> {reply[:50]}")
        
        return reply
    
    async def handle_command(self, command):
        """处理指令"""
        commands = {
            "/help": self.cmd_help,
            "/time": self.cmd_time,
            "/publish": self.cmd_publish,
            "/content": self.cmd_push_content
        }
        handler = commands.get(command)
        if handler:
            return await handler()
        return "未知指令，输入 /help 查看帮助"
```

---

## 🎯 四、分阶段实施计划

### **Phase 1: 基础功能验证（预计0.5天）**

#### **目标**
✅ 能成功登录、能收发 echo 消息

#### **任务清单**
- [ ] **Task 1.1**: 安装依赖 (`aiohttp`, `qrcode`)
- [ ] **Task 1.2**: 实现 `WeChatILinkClient` 基础类
  - [ ] `make_headers()` - 请求头构造
  - [ ] `api_get()` / `api_post()` - HTTP封装
  - [ ] `get_qrcode()` - 获取二维码
  - [ ] `login_with_qrcode()` - 登录流程
- [ ] **Task 1.3**: 实现消息收发
  - [ ] `poll_messages()` - 长轮询监听
  - [ ] `send_text()` - 发送消息
- [ ] **Task 1.4**: 编写测试脚本 `test_ilink_basic.py`
  - [ ] 测试登录流程
  - [ ] 测试echo消息（收到什么回复什么）
- [ ] **Task 1.5**: 本地验证通过

#### **验收标准**
```bash
# 运行测试脚本
python test_ilink_basic.py

# 预期输出：
# ✅ 获取二维码成功
# ✅ 扫码登录成功 (bot_token=xxx...)
# ✅ 开始监听消息...
# [收到] filehelper: 测试消息
# [已回复] filehelper: Echo: 测试消息
```

---

### **Phase 2: 引擎与API集成（预计1天）**

#### **目标**
✅ 通过REST API控制机器人，前端可操作

#### **任务清单**
- [ ] **Task 2.1**: 实现 `WeChatBotEngine` 引擎类
  - [ ] 单例模式
  - [ ] 状态管理（BotStatus枚举）
  - [ ] 生命周期（start/stop）
  - [ ] 二维码管理和Base64转换
- [ ] **Task 2.2**: 实现 API 路由
  - [ ] `POST /api/wechat/start` - 启动服务
  - [ ] `POST /api/wechat/stop` - 停止服务
  - [ ] `GET /api/wechat/status` - 查询状态
  - [ ] `GET /api/wechat/qrcode` - 获取二维码
  - [ ] `POST /api/wechat/send` - 发送消息
- [ ] **Task 2.3**: 注册路由到 main.py
- [ ] **Task 2.4**: 创建前端测试页面 `test-wechat-ilink.html`
  - [ ] 启动/停止按钮
  - [ ] 二维码显示区域
  - [ ] 状态监控面板
  - [ ] 消息发送表单
- [ ] **Task 2.5**: 端到端测试
  - [ ] 前端启动服务
  - [ ] 扫码登录
  - [ ] 发送消息验证

#### **验收标准**
```bash
# 1. 启动后端
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

# 2. 打开前端测试页面
# http://localhost:3001/test-wechat-ilink.html

# 3. 操作步骤
# 点击「启动」→ 显示二维码 → 扫码 → 状态变为「已登录」
# 输入消息 → 点击发送 → 微信收到消息

# 4. API测试
curl http://127.0.0.1:8000/api/wechat/status
# 返回: {"success": true, "data": {"status": "logged_in", ...}}
```

---

### **Phase 3: 业务逻辑对接（预计1天）**

#### **目标**
✅ 收到的消息转发给Pulse Studio后端处理

#### **任务清单**
- [ ] **Task 3.1**: 实现 `WeChatMessageHandler`
  - [ ] 消息分发器
  - [ ] 指令解析器
  - [ ] AI对话接口（对接DeepSeek）
- [ ] **Task 3.2**: 创建 `/api/wechat/receive` 内部接口
  - [ ] 接收来自微信的消息
  - [ ] 调用MessageHandler处理
  - [ ] 返回回复内容
- [ ] **Task 3.3**: 引擎对接Handler
  - [ ] poll_messages 收到消息后调用 Handler
  - [ ] Handler 返回结果后调用 send_text 回复
- [ ] **Task 3.4**: AI模型配置
  - [ ] DeepSeek API Key 配置
  - [ ] Prompt模板设计
  - [ ] 对话上下文管理
- [ ] **Task 3.5**: 测试完整链路
  - [ ] 微信发送"你好" → AI回复
  - [ ] 微信发送"/help" → 返回帮助信息

#### **验收标准**
```
# 微信对话测试
用户: 你好
Bot: 你好！我是Pulse Studio助手，有什么可以帮您？

用户: /help
Bot: 可用指令：
# /help - 查看帮助
# /time - 查看时间
# /publish - 发布内容
# /content - 推送内容
```

---

### **Phase 4: 前端UI集成（预计1天）**

#### **目标**
✅ 在设置页面添加微信机器人开关

#### **任务清单**
- [ ] **Task 4.1**: 开发 `WeChatBotToggle.vue` 组件
  - [ ] 开关按钮（Switch样式）
  - [ ] 二维码弹窗（Modal）
  - [ ] 状态指示灯（绿/红/黄）
  - [ ] 连接时间显示
- [ ] **Task 4.2**: 集成到 SettingsView.vue
  - [ ] 在适当位置插入组件
  - [ ] 状态持久化（localStorage）
- [ ] **Task 4.3**: WebSocket实时更新
  - [ ] 连接 `/ws/status`
  - [ ] 状态变化自动刷新UI
- [ ] **Task 4.4**: UI优化
  - [ ] 加载动画
  - [ ] 错误提示
  - [ ] 移动端适配
- [ ] **Task 4.5**: 用户体验测试

#### **验收标准**
```
# UI交互流程
1. 进入设置页面
2. 看到「微信机器人」开关（默认关闭）
3. 点击开关 → 弹出二维码弹窗
4. 用微信扫码 → 弹窗关闭 → 开关变绿
5. 显示「已连接 | 在线时长: 00:15:30」
6. 再次点击开关 → 断开连接 → 开关变灰
```

---

### **Phase 5: 高级功能（预计2-3天）**

#### **目标**
✅ AI对话、内容推送、任务交互

#### **任务清单**
- [ ] **Task 5.1**: AI对话增强
  - [ ] 多轮对话上下文
  - [ ] 流式输出（可选）
  - [ ] 敏感词过滤
- [ ] **Task 5.2**: 内容推送功能
  - [ ] 打包卡片内容（标题+封面+摘要）
  - [ ] 推送到指定联系人
  - [ ] 推送记录查询
- [ ] **Task 5.3**: 任务交互
  - [ ] `/publish` 触发发布流程
  - [ ] 进度反馈（正在生成文案...）
  - [ ] 结果通知（发布成功/失败）
- [ ] **Task 5.4**: 文件传输支持
  - [ ] 图片发送
  - [ ] 文件发送
  - [ ] 缩略图生成
- [ ] **Task 5.5**: 稳定性保障
  - [ ] 自动重连机制
  - [ ] Token过期检测
  - [ ] 错误日志记录
  - [ ] 监控告警（可选）

#### **验收标准**
```
# 高级功能测试

## AI对话
用户: 帮我写一篇关于夏天的文案
Bot: [生成一篇优美的夏天主题小红书文案...]

## 内容推送
用户: /content latest
Bot: [推送最新发布的卡片内容，包含图片]

## 任务交互
用户: /publish
Bot: 正在准备发布任务...
    请选择要发布的选题：
    1. 夏日穿搭指南
    2. 美食探店分享
用户: 1
Bot: 已选择选题1，开始生成内容...
    ✅ 发布成功！链接: https://...
```

---

## ⚙️ 五、技术细节与注意事项

### 5.1 依赖安装

```bash
# requirements.txt 新增
aiohttp>=3.9.0      # HTTP客户端
qrcode>=7.4.2       # 二维码生成
Pillow>=10.0.0      # 图片处理（二维码渲染）
```

### 5.2 配置项

```python
# config.py 新增
class WeChatConfig:
    BASE_URL = "https://ilinkai.weixin.qq.com"
    APP_ID = "your_app_id"  # 从OpenClaw获取
    CLIENT_VERSION = "1.0.0"
    BOT_TYPE = 3  # 个人号
    
    # DeepSeek AI配置
    DEEPSEEK_API_KEY = ""
    DEEPSEEK_BASE_URL = "https://api.deepseek.com"
    DEEPSEEK_MODEL = "deepseek-chat"
```

### 5.3 错误处理

```python
# 常见错误及解决方案
ERROR_CODES = {
    -1: "系统错误",
    -3: "参数错误（检查context_token是否正确）",
    -14: "Session过期，需重新登录",
    -100: "频率限制，稍后重试",
}

# 重试策略
MAX_RETRIES = 3
RETRY_DELAY = 1  # 秒
```

### 5.4 安全考虑

- ✅ Token存储在内存中，不落盘（或加密存储）
- ✅ 日志中脱敏（不打印完整Token）
- ✅ API接口加权限校验（JWT Token）
- ✅ 限制消息频率（防刷）

### 5.5 性能优化

- **连接池复用**: 使用单个 `aiohttp.ClientSession`
- **消息队列**: 收到的消息先入队，异步处理
- **Context缓存**: 按 `user_id` 缓存 `context_token`
- **心跳保活**: 定期发送空请求保持连接

---

## 🧪 六、测试策略

### 6.1 单元测试
```python
# tests/test_wechat_ilink_client.py
class TestWeChatILinkClient:
    async def test_make_headers():
        headers = client.make_headers(token="test")
        assert headers["AuthorizationType"] == "ilink_bot_token"
        assert headers["Authorization"] == "Bearer test"
    
    async def test_login_flow():
        with patch('api_get') as mock_api:
            mock_api.return_value = {"qrcode": "test123"}
            qrcode = await client.get_qrcode()
            assert qrcode == "test123"
```

### 6.2 集成测试
```python
# tests/test_wechat_engine.py
class TestWeChatBotEngine:
    async def test_lifecycle():
        engine = WeChatBotEngine()
        assert engine.state.status == BotStatus.STOPPED
        
        await engine.start()
        assert engine.state.status == BotStatus.WAITING_QR
        
        await engine.stop()
        assert not engine.is_running
```

### 6.3 E2E测试
```bash
# 手动测试清单
- [ ] 扫码登录成功
- [ ] 发送消息到filehelper成功
- [ ] 收到消息并自动回复
- [ ] 断线后自动重连
- [ ] Token过期重新登录
- [ ] 并发消息不丢失
```

---

## 📊 七、监控与运维

### 7.1 关键指标
| 指标 | 说明 | 告警阈值 |
|------|------|----------|
| 在线状态 | 机器人是否在线 | 离线>5分钟 |
| 消息延迟 | 收到→回复的时间 | >10秒 |
| 错误率 | API调用失败比例 | >5% |
| 重连次数 | 自动重连频率 | >3次/小时 |

### 7.2 日志规范
```python
logger.info("[WeChatBot] 用户登录成功 wxid=%s", wxid)
logger.warning("[WeChatBot] 消息发送失败 to=%s error=%s", to_wxid, error)
logger.error("[WeChatBot] Token过期，需要重新登录")
```

### 7.3 健康检查
```python
@router.get("/health")
async def health_check():
    engine = WeChatBotEngine.get_instance()
    return {
        "status": "healthy" if engine.is_logged_in else "degraded",
        "uptime": engine.uptime_seconds,
        "last_message_time": engine.last_message_time
    }
```

---

## 🚀 八、快速开始指南

### 8.1 开发环境搭建
```bash
# 1. 克隆参考项目（已完成）
cd D:\My_Project\weixin-ClawBot-API

# 2. 安装依赖
pip install aiohttp qrcode Pillow

# 3. 运行参考项目的bot.py（理解流程）
python bot.py
# 选择AI提供商 → 扫码登录 → 测试对话

# 4. 开始开发Pulse Studio集成
cd D:\My_Project\多智能体小红书发布平台\backend
```

### 8.2 最小可行产品（MVP）
```python
# mvp_test.py - 最简测试脚本（50行搞定）
import asyncio
import aiohttp
from wechat_ilink_client import WeChatILinkClient

async def main():
    client = WeChatILinkClient()
    
    # 登录
    qrcode = await client.get_qrcode()
    print(f"请扫描二维码: {qrcode}")
    
    creds = await client.login(qrcode['qrcode'])
    print(f"登录成功! Token: {creds['bot_token'][:20]}...")
    
    # 监听消息
    async for msg in client.poll_messages():
        print(f"收到: {msg.text} (来自: {msg.from_user_id})")
        
        # Echo回复
        await client.send_text(msg.from_user_id, msg.context_token, f"Echo: {msg.text}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 📝 九、常见问题FAQ

### Q1: 为什么不用现成的SDK？
**A**: 
- 现有SDK（如 wechat-agent-sdk）不稳定，API经常变动
- 直接调用HTTP API更可控，调试方便
- 参考项目（SiverKing/weixin-ClawBot-API）就是纯HTTP实现，证明可行

### Q2: 封号风险如何？
**A**: 
- iLink Bot 是腾讯**官方开放**的API协议
- 通过 OpenClaw 平台正规接入
- **比 itchat/wxpy 安全得多**（那些是逆向协议）

### Q3: 如何获取 App ID？
**A**: 
- 需要先部署 OpenClaw 平台
- 或使用参考项目中硬编码的默认值
- 具体查看 `weixin-ClawBot-API/bot.py` 中的常量定义

### Q4: 消息丢失怎么办？
**A**: 
- 使用 `get_updates_buf` 断点续传
- 本地消息队列缓冲
- 重要消息可做持久化（Redis/数据库）

### Q5: 如何支持多用户同时使用？
**A**: 
- iLink Bot 天然支持多用户
- 每个 `from_user_id` 独立会话
- `context_token` 按用户隔离缓存

### Q6: 性能如何？能支撑多少并发？
**A**: 
- 长轮询模式，单连接可处理多用户
- 官方未公开限制，但个人号足够使用
- 如需大规模，考虑部署多个Bot实例

---

## 🎯 十、总结与下一步行动

### ✅ 已完成
- [x] 旧代码清理（weixin-agent-sdk 方案）
- [x] 参考项目克隆和学习
- [x] 技术调研和可行性分析
- [x] 详细实施方案编写

### 🔄 进行中
- [ ] Phase 1: 基础功能实现
- [ ] Phase 2: 引擎与API集成
- [ ] Phase 3: 业务逻辑对接
- [ ] Phase 4: 前端UI集成
- [ ] Phase 5: 高级功能

### 📌 核心优势总结

1. **简单** - 核心代码300行，无复杂依赖
2. **稳定** - 基于腾讯官方协议，不会突然失效
3. **可控** - 纯HTTP调用，易于调试和维护
4. **完整** - 支持登录、收发、多媒体、状态管理等全套功能
5. **有参考** - 有成熟的开源项目可以借鉴

### 🚀 立即开始执行

**按照以下顺序严格执行：**

1. ✅ **阅读本文档**（确保理解每个细节）
2. ✅ **运行参考项目** `python D:\My_Project\weixin-ClawBot-API\bot.py`
3. ✅ **开始 Phase 1** - 先实现基础功能并通过测试
4. ✅ **逐步推进** - 每个Phase完成后验收再进入下一阶段
5. ✅ **遇到问题** - 先查本文档FAQ，再看参考项目代码

---

## 📚 参考资料

- **主参考项目**: https://github.com/SiverKing/weixin-ClawBot-API
- **iLink协议文档**: https://www.wechatbot.dev/zh/protocol
- **PyPI SDK**: https://pypi.org/project/wechatbot-sdk/
- **掘金教程**: https://juejin.cn/post/7622936804133847076
- **网易逆向分析**: https://www.163.com/dy/article/KOQHIPT80531DVR.html

---

**文档版本**: v1.0  
**最后更新**: 2026-08-19  
**作者**: Pulse Studio Team  
**审核状态**: ✅ 待用户确认后执行