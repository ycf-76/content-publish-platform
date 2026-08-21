# 微信机器人集成实施文档

> 基于 **weixin-agent-sdk** 的微信聊天机器人集成方案  
> **版本**: v1.0 (重新创建)  
> **日期**: 2026-01-19  
> **状态**: 待实施

## 📌 项目背景

### 需求描述
在「多智能体小红书发布平台」中集成微信聊天机器人功能，实现：
- 开关按钮控制机器人启停
- 扫码登录（二维码显示）
- 双向消息通信（接收用户消息 + 发送内容）
- 小红书内容推送功能

### 技术选型
- **SDK**: weixin-agent-sdk v0.2.1
- **协议**: ACP (Agent Client Protocol)
- **架构**: 纯Python集成（FastAPI + SDK）

---

## 🏗️ 架构设计

### 整体架构图

```
┌─────────────────────────────────────────────┐
│           前端 (Vue 3 + Vite)                │
│                                             │
│  SettingsView.vue                           │
│  └── WechatBotToggle.vue                    │
│      ├── 开关按钮                            │
│      └── QRCodeModal.vue (二维码弹窗)        │
│                                             │
└─────────────────┬───────────────────────────┘
                  │ HTTP / WebSocket
                  ▼
┌─────────────────────────────────────────────┐
│         后端 (FastAPI + Python)              │
│                                             │
│  main.py                                    │
│  └── api/routers/wechat_bot.py              │
│      ├── POST /api/wechat/start             │
│      ├── GET  /api/wechat/status            │
│      ├── GET  /api/wechat/qrcode            │
│      ├── POST /api/wechat/stop              │
│      ├── POST /api/wechat/send              │
│      ├── POST /api/wechat/push-xhs          │
│      ├── GET  /api/wechat/messages          │
│      └── WS   /api/wechat/ws                │
│                                             │
│  rpa/                                        │
│  ├── wechat_bot_engine.py   (核心引擎)       │
│  └── wechat_agent.py        (Agent实现)     │
│                                             │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│        weixin-agent-sdk                      │
│                                             │
│  WeChatBot(agent=XHSPlatformAgent)          │
│       ↓                                     │
│  iLink Bot API (腾讯 OpenClaw)               │
│       ↓                                     │
│  微信客户端                                  │
└─────────────────────────────────────────────┘
```

### 设计原则

1. **混合模式**:
   - Agent 处理接收的消息（自动触发）
   - Engine 手动发送消息（主动调用）

2. **单例引擎**:
   - 全局唯一的 WeChatBotEngine 实例
   - 统一管理生命周期和状态

3. **事件驱动**:
   - 消息回调、状态变化、二维码更新
   - 支持 WebSocket 实时通知

---

## 📁 文件结构

### 新建文件清单

```
backend/
├── app/
│   ├── rpa/
│   │   ├── wechat_bot_engine.py      # 核心引擎模块
│   │   ├── wechat_agent.py           # Agent 实现
│   │   └── test_backend_integration.py  # 集成测试脚本
│   │
│   └── api/routers/
│       └── wechat_bot.py             # API 路由定义
│
frontend/
├── src/components/settings/
│   ├── WechatBotToggle.vue           # 设置页面主组件
│   └── QRCodeModal.vue               # 二维码弹窗组件
│
├── public/
│   └── test-wechat-api.html          # API 测试页面 (已创建✅)
│
docs/
└── WECHAT_BOT_IMPLEMENTATION.md      # 本文档
```

### 修改文件清单

```
backend/app/main.py                   # 添加路由注册
frontend/src/views/SettingsView.vue   # 添加选项卡
```

---

## 🎯 实施步骤

### 第1步：环境准备 ✅ 已完成
- [x] 安装 weixin-agent-sdk: `pip install wechat-agent-sdk`
- [x] 创建基础测试脚本 `test_weixin_sdk.py`
- [x] 验证 SDK 可用性 (6/6 测试通过)

### 第2步：后端核心开发 ⬜ 进行中
- [ ] 创建 `wechat_bot_engine.py` 核心引擎
- [ ] 创建 `wechat_agent.py` Agent 实现
- [ ] 创建 `wechat_bot.py` API 路由
- [ ] 修改 `main.py` 注册路由
- [ ] 运行集成测试验证

### 第3步：前端界面开发 ⬜ 待开始
- [ ] 创建 `WechatBotToggle.vue`
- [ ] 创建 `QRCodeModal.vue`
- [ ] 修改 `SettingsView.vue`

### 第4步：AI 对话集成 ⬜ 待开始
- [ ] 对接 DeepSeek LLM 服务
- [ ] 多轮对话上下文管理
- [ ] 指令处理系统

### 第5步：工作流集成 ⬜ 待开始
- [ ] 发布节点添加推送逻辑
- [ ] 内容格式化和打包
- [ ] 推送到微信文件传输助手

### 第6步：测试优化 ⬜ 待开始
- [ ] 端到端功能测试
- [ ] 错误处理完善
- [ ] UI/UX 优化

---

## 🔑 技术细节

### WeChatBotEngine 核心类

```python
class WeChatBotEngine:
    """微信机器人核心引擎"""
    
    async def start(self) -> bool:
        """启动服务"""
        
    async def stop(self) -> bool:
        """停止服务"""
        
    async def get_status(self) -> Dict:
        """查询状态"""
        
    async def get_qrcode(self) -> Optional[Dict]:
        """获取二维码"""
        
    async def send_message(self, to_wxid, content) -> bool:
        """发送消息"""
        
    async def push_xhs_content(self, title, content, images_count=0) -> bool:
        """推送小红书内容"""
```

### XHSPlatformAgent Agent 类

```python
class XHSPlatformAgent(Agent):
    """小红书平台 AI 助手"""
    
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """处理收到的消息"""
        # 1. 判断是否指令 (/help, /task 等)
        # 2. 否则走 AI 对话
        # 3. 返回 ChatResponse
```

### API 接口规范

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| POST | `/api/wechat/start` | 启动服务 | 需要 |
| GET | `/api/wechat/status` | 查询状态 | 需要 |
| GET | `/api/wechat/qrcode` | 获取二维码 | 需要 |
| POST | `/api/wechat/stop` | 停止服务 | 需要 |
| POST | `/api/wechat/send` | 发送消息 | 需要 |
| POST | `/api/wechat/push-xhs` | 推送内容 | 需要 |
| GET | `/api/wechat/messages` | 消息历史 | 需要 |
| WS | `/api/wechat/ws` | 实时通信 | 需要 |
| GET | `/api/wechat/health` | 健康检查 | 不需要 |

---

## ⚠️ 注意事项

### 依赖要求
```bash
pip install wechat-agent-sdk>=0.2.1
pip install fastapi>=0.100.0
```

### 配置项
- 无需额外配置文件
- 使用项目现有的 DeepSeek API Key
- 二维码有效期通常 60 秒

### 安全考虑
- 所有接口需要认证（除 health 外）
- WebSocket 需要携带 token
- 不存储敏感信息在日志中

---

## 📊 进度跟踪

| 时间 | 操作 | 状态 | 备注 |
|------|------|------|------|
| 2026-01-19 01:00 | 清理旧代码 | ✅ 完成 | 删除9个旧文件 |
| 2026-01-19 01:15 | 创建文档 v1.0 | ✅ 完成 | 本次重新创建 |
| 2026-01-19 01:20 | 创建后端代码 | ❌ 失败 | Write操作未生效，需重做 |
| 2026-01-19 01:25 | 运行测试 | ❌ 无效 | 基于不存在的代码 |
| 2026-01-19 01:30 | 重新开始 | 🔄 进行中 | 正确执行每一步 |

---

## 🚀 下一步行动

**立即执行**:
1. 创建 `wechat_bot_engine.py` 并验证文件存在
2. 创建 `wechat_agent.py` 并验证文件存在
3. 创建 `wechat_bot.py` 并验证文件存在
4. 修改 `main.py` 并验证改动生效
5. 运行真实的集成测试

**验收标准**:
- 所有文件必须通过 `os.path.exists()` 检查
- 导入测试必须通过 (`import` 不报错)
- API 接口必须在 `/docs` 中可见
- 集成测试全部通过

---

**文档版本历史**:
- v1.0 (2026-01-19 01:35): 重新创建，修正之前的错误