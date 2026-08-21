# 微信机器人多用户并发重构文档

## 1. 问题

当前 WeChatBotEngine 是单例模式，全局只有 1 个引擎实例、1 份凭证、1 条消息流。
平台用户 A 登录微信后，用户 B 看到的也是 A 的状态，两人无法各自独立使用机器人。

## 2. 目标

```
平台用户A ──→ Engine-A ──→ A的微信账号（独立凭证、独立消息流）
平台用户B ──→ Engine-B ──→ B的微信账号（独立凭证、独立消息流）
```

每个平台用户拥有独立的微信机器人引擎实例，互不干扰。

## 3. 现有用户体系

- 后端: `get_current_user` (app/api/deps.py) 从 JWT 解析 user_id (ULID格式)
- 前端: axios 拦截器自动给请求加 `Authorization: Bearer <token>`
- 微信机器人 API 当前未使用 JWT，直接 fetch 调用

## 4. 改动清单

### Step 1: 引擎层 — 单例 → 注册表 ✅

**文件**: `backend/app/rpa/wechat_bot_engine.py`

改动:
- 移除 `_instance` 单例模式和 `get_instance()` 类方法
- 新增 `WeChatBotRegistry` 类，维护 `{platform_user_id: WeChatBotEngine}` 字典
- `WeChatBotEngine.__init__` 接收 `platform_user_id` 参数
- 凭证文件路径改为 `.wechat_credentials_{platform_user_id}.json`
- 全局函数 `get_wechat_engine(platform_user_id)` 从注册表获取/创建引擎
- 新增 `get_wechat_registry()` 获取全局注册表

验证结果:
- ✅ 语法检查通过
- ✅ 两个不同 user_id 创建两个独立引擎实例
- ✅ 同一 user_id 返回同一实例
- ✅ 凭证文件路径按用户隔离

### Step 2: API 层 — 所有接口加用户身份 ✅

**文件**: `backend/app/api/routers/wechat_bot.py`

改动:
- 所有路由函数添加 `user_id: str = Depends(get_current_user)` 参数
- `get_wechat_engine()` 调用改为 `get_wechat_engine(user_id)`
- `/status`、`/start`、`/stop`、`/qrcode`、`/send`、`/messages`、`/push`、`/health` 全部按 user_id 隔离
- WebSocket 接口通过 query 参数 `?token=<jwt>` 识别用户
- import `get_current_user` from `app.api.deps`

验证结果:
- ✅ 语法检查通过
- ✅ 所有接口都依赖 JWT 认证

### Step 3: 前端层 — API 调用加 JWT ✅

**文件**: `frontend/src/components/settings/WeChatBotSettings.vue`

改动:
- `apiFetch` 函数从 localStorage 读取 token，加到 `Authorization: Bearer` header
- 401 响应时抛出友好错误提示

**文件**: `frontend/src/components/workbench/FinalReviewCard.vue`

改动:
- 新增 `wechatAuthHeaders()` 辅助函数
- `pushToWechat` 中所有 fetch 调用加 Authorization header
- 图片数据优先从 `reviewImages` ref 取（已加载的图片），再从 props 取

验证结果:
- ✅ 前端代码修改完成
- ✅ 图片数据来源修复

### Step 4: 凭证层 — 按用户隔离 ✅

**文件**: `backend/app/rpa/wechat_bot_engine.py`

改动:
- `_CREDENTIALS_FILE` 从全局常量改为实例属性 `_credentials_file`
- 路径包含 platform_user_id: `.wechat_credentials_{platform_user_id}.json`
- `_save_credentials` / `_load_credentials` / `_clear_credentials` 使用实例的凭证路径

验证结果:
- ✅ user_a 和 user_b 的凭证文件路径不同
- ✅ 凭证文件名: `.wechat_credentials_user_a.json` / `.wechat_credentials_user_b.json`

### Step 5: 图片发送修复 ✅

**文件**: `backend/app/rpa/wechat_ilink_client.py`

改动:
- 完全重写 `send_image` 方法，按 iLink 2.x CDN 协议正确实现
- `getuploadurl` 参数修正: `filekey`/`media_type`/`rawsize`/`rawfilemd5`/`filesize`/`aeskey`/`no_need_thumb`
- `aes_key` 格式修正: `base64(hex_string)` 而非 `base64(raw_bytes)`
- CDN 上传方法修正: POST 而非 PUT
- `encrypt_query_param` 来源修正: 从 CDN 响应 header `x-encrypted-param` 获取
- `image_item` 结构修正: `{media: {encrypt_query_param, aes_key, encrypt_type:1}, mid_size}`
- CDN URL 构建: 优先 `upload_full_url`，否则用 `upload_param` 构建

**文件**: `frontend/src/components/workbench/FinalReviewCard.vue`

改动:
- 图片数据优先从 `reviewImages` ref 取（已加载的图片），再从 props 取

验证结果:
- ✅ 文本+图片都能成功推送到微信
- ✅ 后端日志打印完整 getuploadurl 响应和 CDN header

### Step 6: 端到端验证 ✅

场景:
1. ✅ 用户 A 开关 → 扫码 → 已连接 → 发消息 → 收到回复
2. ✅ 用户 B 开关 → 扫码 → 已连接 → 发消息 → 收到回复（独立隔离）
3. ✅ A 和 B 的消息互不串扰
4. ✅ A 关闭开关，B 不受影响
5. ✅ A 重新打开开关，凭证复用，免扫码
6. ✅ 工作流推送文案+图片到微信成功

## 5. 不改动的部分

- `wechat_ilink_client.py` 底层协议调用不变（仅修复了 send_image 参数格式）
- 前端 UI 组件结构不变，只是数据来源按用户隔离
- 工作流推送逻辑不变，只是 fetch 加 header

## 6. 架构变化总结

| 模块 | 改前 | 改后 |
|------|------|------|
| Engine | 单例 `get_instance()` | 注册表 `get_wechat_engine(user_id)` |
| 凭证文件 | `.wechat_credentials.json` | `.wechat_credentials_{user_id}.json` |
| API 认证 | 无 | JWT `Depends(get_current_user)` |
| 前端 fetch | 无 header | `Authorization: Bearer <token>` |
| 并发能力 | 1 用户 | N 用户（各自独立） |
| 图片发送 | 参数格式错误 | iLink 2.x CDN 协议正确实现 |
| 图片数据源 | props（可能为空） | reviewImages ref → props fallback |