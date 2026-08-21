# 微信机器人实现总结 & 与克隆项目对比

## 一、项目架构

### 我们的实现

```
backend/
├── app/rpa/
│   ├── wechat_ilink_client.py   # iLink 协议底层客户端（HTTP 调用）
│   └── wechat_bot_engine.py     # 机器人引擎（生命周期管理 + 多用户注册表）
├── app/api/routers/
│   └── wechat_bot.py            # FastAPI 路由（9 个接口 + WebSocket）
frontend/
├── src/components/settings/
│   └── WeChatBotSettings.vue    # 设置页微信机器人面板（开关+二维码+聊天）
└── src/components/workbench/
    └── FinalReviewCard.vue      # 终审卡片（推送文案+图片到微信）
```

### 克隆项目 (SiverKing/weixin-ClawBot-API)

```
weixin-ClawBot-API/
├── bot.py        # 单文件实现（登录+收消息+AI回复+重连）
├── bot.js        # Node.js 版本
├── dusapi.py     # AI 接口封装（Anthropic 格式）
├── deepseek.py   # DeepSeek 接口封装
└── config.json   # 运行时配置
```

**架构差异**：克隆项目是单文件 CLI 脚本，我们是分层架构（Client → Engine → API → 前端）。

---

## 二、功能对比

| 功能 | 克隆项目 | 我们的实现 | 状态 |
|------|---------|-----------|------|
| **扫码登录** | ✅ 终端渲染二维码 | ✅ 前端内嵌二维码弹窗 | ✅ 更优 |
| **长轮询收消息** | ✅ getupdates 35s hold | ✅ 同样实现 | ✅ 一致 |
| **文本消息发送** | ✅ sendmessage type=1 | ✅ 同样实现 | ✅ 一致 |
| **"正在输入"状态** | ✅ sendtyping | ✅ 同样实现 | ✅ 一致 |
| **context_token 缓存** | ✅ 按用户缓存 | ✅ UserSession 缓存 | ✅ 一致 |
| **typing_ticket 缓存** | ✅ 按用户缓存 | ✅ UserSession 缓存 | ✅ 一致 |
| **AI 自动回复** | ✅ DusAPI/DeepSeek | ❌ 未实现 | ⏳ 待开发 |
| **图片消息发送** | ❌ 未实现（README 明确说仅文本） | ✅ AES-128-ECB + CDN + sendmessage | ✅ **我们更完整** |
| **凭证持久化** | ❌ 无（重启需重新扫码） | ✅ .wechat_credentials_{uid}.json | ✅ **我们更完整** |
| **凭证复用** | ❌ 无 | ✅ 启动时验证已保存凭证，免扫码 | ✅ **我们更完整** |
| **多用户并发** | ❌ 单进程单用户 | ✅ 注册表模式，按用户隔离引擎/凭证/消息流 | ✅ **我们更完整** |
| **JWT 认证** | ❌ 无（CLI 直接调用） | ✅ 所有接口 JWT 鉴权 | ✅ **我们更完整** |
| **24h 自动重连** | ✅ 定时器+用户确认+无缝切换 | ❌ 未实现 | ⏳ 待开发 |
| **Bot 指令系统** | ✅ /help /time /重新连接 | ❌ 未实现 | ⏳ 待开发 |
| **前端 UI** | ❌ 纯终端 | ✅ 设置页面板+二维码+聊天窗口 | ✅ **我们更完整** |
| **工作流推送** | ❌ 无 | ✅ 文案+图片一键推送到微信 | ✅ **我们更完整** |
| **WebSocket 实时状态** | ❌ 无 | ✅ ws/status 推送状态变化 | ✅ **我们更完整** |
| **API 接口** | ❌ 无（CLI 直接调用） | ✅ 9 个 REST + 1 个 WebSocket | ✅ **我们更完整** |
| **配置管理** | ✅ config.json 分 provider | ✅ 前端设置页 | ✅ 不同方式 |

---

## 三、协议实现对比

### 3.1 登录流程

| 步骤 | 克隆项目 | 我们的实现 |
|------|---------|-----------|
| 获取二维码 | `POST get_bot_qrcode?bot_type=3` 带 `local_token_list` | 同样实现，支持 POST 和 GET 两种方式 |
| 轮询扫码状态 | `GET get_qrcode_status?qrcode=xxx` | 同样实现 |
| 处理 scaned 状态 | ✅ | ✅ |
| 处理 confirmed 状态 | ✅ 提取 bot_token + baseurl | ✅ 同样 |
| 处理 binded_redirect | ✅ 沿用当前 token | ✅ 同样 + 优先复用已保存凭证 |
| 处理 need_verifycode | ✅ 终端提示输入 | ✅ 日志提示 |
| 处理 expired | ✅ 重新生成二维码 | ✅ 同样 + 尝试凭证复用 |

### 3.2 消息收发

| 步骤 | 克隆项目 | 我们的实现 |
|------|---------|-----------|
| 长轮询 | `POST getupdates` 带 `get_updates_buf` | ✅ 同样实现，支持断点续传 |
| 消息解析 | `message_type=1` 过滤文本 | ✅ 同样 |
| getconfig | 每用户首次调用，缓存 typing_ticket | ✅ 同样 |
| sendtyping | 发送前 status=1，发送后 status=2 | ✅ 同样 |
| sendmessage | `message_type=2, message_state=2, item_list=[{type:1, text_item}]` | ✅ 同样 |
| client_id | `openclaw-weixin-{random}` | `pulse-studio-{random}` |

### 3.3 图片发送（我们独有）

克隆项目 README 明确说：**"本项目仅支持文本消息，图片/语音/文件等媒体消息需额外实现 CDN 加密上传流程"**。

我们的完整实现：

```
1. 生成随机 AES-128 key (16 bytes)
2. aes_key_hex = key.hex()                    # 32字符十六进制
3. aes_key_b64 = base64(aes_key_hex)          # base64(hex_string)，不是 base64(raw_bytes)
4. AES-128-ECB 加密图片 (PKCS7 padding)
5. 计算 rawfilemd5 = md5(明文).hex()
6. 生成 filekey = random(8).hex()
7. getuploadurl: {filekey, media_type:1, to_user_id, rawsize, rawfilemd5, filesize, no_need_thumb:true, aeskey:aes_key_hex}
8. 从响应取 upload_full_url（或用 upload_param 构建 CDN URL）
9. POST 加密文件到 CDN
10. 从 CDN 响应 header 取 x-encrypted-param → download_param
11. sendmessage: item_list=[{type:2, image_item:{media:{encrypt_query_param, aes_key, encrypt_type:1}, mid_size}}]
```

关键踩坑点（对比多个开源项目后确认）：
- `aes_key` 格式：`base64(hex_string_bytes)`，不是 `base64(raw_key_bytes)`
- `encrypt_query_param`：从 CDN 上传响应 header `x-encrypted-param` 获取，不是从 getuploadurl 响应获取
- CDN 上传方法：POST，不是 PUT
- `image_item` 结构：嵌套 `media` 对象，不是扁平的 `cdn_file_key/cdn_token`

---

## 四、多用户并发（我们独有）

克隆项目是单进程 CLI，天然单用户。我们的平台需要多用户并发：

### 架构

```
WeChatBotRegistry (全局注册表)
  ├── user_id_A → WeChatBotEngine(platform_user_id="A")
  │     ├── WeChatILinkClient (独立连接)
  │     ├── .wechat_credentials_A.json (独立凭证)
  │     └── UserSession[] (独立消息流)
  └── user_id_B → WeChatBotEngine(platform_user_id="B")
        ├── WeChatILinkClient (独立连接)
        ├── .wechat_credentials_B.json (独立凭证)
        └── UserSession[] (独立消息流)
```

### 改动清单

| 层 | 文件 | 改动 |
|----|------|------|
| 引擎层 | wechat_bot_engine.py | 单例 → 注册表，`__init__` 接收 platform_user_id，凭证文件按用户隔离 |
| API 层 | wechat_bot.py | 所有接口加 `Depends(get_current_user)`，WebSocket 用 JWT token 鉴权 |
| 前端层 | WeChatBotSettings.vue | apiFetch 自动加 Authorization header |
| 前端层 | FinalReviewCard.vue | pushToWechat 加 wechatAuthHeaders() |

---

## 五、凭证持久化（我们独有）

| 场景 | 克隆项目 | 我们的实现 |
|------|---------|-----------|
| 重启后端 | 需重新扫码 | ✅ 自动加载已保存凭证，验证通过后免扫码 |
| 二维码过期 | 需重新扫码 | ✅ 优先尝试凭证复用，失败才生成新二维码 |
| 凭证验证 | 无 | ✅ 调用 getconfig 验证凭证有效性 |
| 凭证清理 | 无 | ✅ 验证失败自动清除无效凭证 |

凭证文件格式：`.wechat_credentials_{platform_user_id}.json`

```json
{
  "bot_token": "...",
  "base_url": "https://ilinkai.weixin.qq.com",
  "ilink_bot_id": "...",
  "ilink_user_id": "...",
  "saved_at": "2026-08-19T10:30:00"
}
```

---

## 六、API 接口一览

| 方法 | 路径 | 功能 | 认证 |
|------|------|------|------|
| POST | /api/wechat/start | 启动机器人 | JWT |
| POST | /api/wechat/stop | 停止机器人 | JWT |
| GET | /api/wechat/status | 查询状态 | JWT |
| GET | /api/wechat/qrcode | 获取二维码 | JWT |
| POST | /api/wechat/send | 发送文本消息 | JWT |
| GET | /api/wechat/messages | 获取消息列表 | JWT |
| POST | /api/wechat/push | 推送工作流内容(文案+图片) | JWT |
| WS | /api/wechat/ws/status | 实时状态推送 | JWT (query param) |
| GET | /api/wechat/health | 健康检查 | 无 |

---

## 七、待开发功能

| 功能 | 优先级 | 说明 |
|------|--------|------|
| AI 自动回复 | 高 | 接入 AI 模型，收到消息自动生成回复 |
| 24h 自动重连 | 中 | 定时检测连接状态，到期前预警+无缝切换 |
| Bot 指令系统 | 中 | /help /time /重新连接 等指令 |
| 语音消息 | 低 | silk 编码 + CDN 上传 |
| 视频消息 | 低 | CDN 上传 |
| 文件消息 | 低 | CDN 上传 |

---

## 八、总结

### 我们超越克隆项目的地方

1. **图片消息发送** — 克隆项目明确说仅文本，我们实现了完整的 AES-128-ECB + CDN + sendmessage 图片发送流程
2. **凭证持久化** — 克隆项目重启需重新扫码，我们实现了凭证保存+验证+复用
3. **多用户并发** — 克隆项目单进程单用户，我们实现了注册表模式+JWT 隔离
4. **前端 UI** — 克隆项目纯终端，我们有完整的设置页面+二维码+聊天窗口
5. **工作流推送** — 克隆项目无，我们实现了一键推送文案+图片到微信
6. **WebSocket 实时状态** — 克隆项目无，我们实现了状态变化实时推送
7. **REST API** — 克隆项目无，我们有 9 个接口

### 克隆项目比我们好的地方

1. **AI 自动回复** — 支持 DusAPI/DeepSeek，内置梯度重试
2. **24h 自动重连** — 定时器+用户确认+无缝切换，不断线
3. **Bot 指令系统** — /help /time /重新连接
4. **终端二维码渲染** — 黑白块渲染，无需浏览器

### 协议实现一致性

核心协议（登录+文本收发）与克隆项目完全一致，都严格遵循 iLink 2.x 规范：
- 请求头：AuthorizationType + X-WECHAT-UIN + iLink-App-Id + iLink-App-ClientVersion + Bearer token
- base_info：channel_version 2.4.3 + bot_agent
- 消息流：getupdates → getconfig → sendtyping(1) → sendmessage → sendtyping(2)
- context_token：必须从 inbound 消息原样带回