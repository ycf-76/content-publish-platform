# 前后端 API 契约

> 从 `api/routers/` + `api/schemas/` 代码直接提取。前后端对齐的唯一真相源。

| 版本 | v1.0 |
|------|------|
| 生效 | 2026-09-18 |
| 关联 | 01-ARCHITECTURE.md |

---

## 契约原则

1. 后端先定义 schema，前端按 schema 实现
2. 接口变更 = 先改此文档 → 前后端同步 → 再改代码
3. 破坏性变更新开版本 (`/v2/xxx`)，旧接口保留至少 1 个版本

---

## 一、Workflow 工作流

### POST /api/workflows
启动新工作流

```python
# Request (StartWorkflowRequest)
{
  "topic": str,                    # 必填，工作流主题
  "search_keyword": str | None,   # 搜索关键词，未传时用 topic
  "creative_brief": str,          # 创作要求，优先级高于热点推荐
  "account_id": str,              # 必填，账号 ID
  "model_settings": {             # 可选，用户右侧工作区配置
    "text_model": str,            #   "deepseek-chat" / "deepseek-reasoner"
    "image_model": str,           #   "wanx-v1" (预留)
    "temperature": float,         #   0.0-1.0
    "writing_style": str,         #   "活泼少女"/"知性优雅"/"专业干货"/"慵懒随性"
    "image_style": str,           #   "清新自然"/"日系胶片"/"暖阳滤镜"/"复古胶片"
    "skill_name": str,            #   Skill 路由名
    "enable_card_gen": bool,      #   启用卡片生成
    "enable_wechat_push": bool,   #   启用微信推送
    "enable_feishu_push": bool    #   启用飞书推送
  },
  "reference": dict,              # 选题池参考素材
  "source": str                   # "gui" | "chat_agent"
}

# Response (WorkflowResponse)
{
  "workflow_id": str,
  "user_id": str,
  "account_id": str,
  "topic": str,
  "status": str,                  # "pending" | "running" | ...
  "current_node": str,
  "created_at": str
}
```

### GET /api/workflows
列表（分页）

### GET /api/workflows/{id}
详情

### POST /api/workflows/{id}/pause
暂停

```python
# Request (PauseRequest)
{ "reason": str }
```

### POST /api/workflows/{id}/resume
恢复

```python
# Request (ResumeWorkflowRequest)
{ "action": str, "feedback": str | None }
```

### POST /api/workflows/{id}/rollback
回退到指定节点

```python
# Request (RollbackRequest)
{ "target_node": str }           # "copywrite" / "analyze" / ...
```

### POST /api/workflows/{id}/review
提交人工审核结果

```python
# Request (ReviewActionRequest)
{
  "action": str,                  # "pass" | "reject"
  "feedback": str | None,
  "selected_candidate": dict | None
}
```

### GET /api/workflows/{id}/review/pending
获取待审核信息

### POST /api/workflows/{id}/inject-card-images
卡片编辑器注入图片

```python
# Request (InjectCardImagesRequest)
{
  "images_base64": list[str],
  "image_details": list[dict] | None,
  "style": str,
  "plan_context": dict | None
}
```

### POST /api/workflows/{id}/save-draft
保存草稿

### PATCH /api/workflows/{id}/node-output
更新节点输出（前端编辑后回写）

---

## 二、SSE 事件流

### GET /api/sse/workflow/{workflow_id}
订阅工作流 SSE 事件

```
Headers:
  Authorization: Bearer <jwt>
  Accept: text/event-stream
  Last-Event-ID: <event_id>     # 可选，断线续传

Response: text/event-stream
  event: <event_type>
  data: <json payload>
  id: <event_id>
```

### 事件类型清单

| event_type | payload 关键字段 | 终态? |
|-----------|-----------------|-------|
| node_started | `{node, status}` | 否 |
| node_completed | `{node, output, duration_ms}` | 否 |
| node_error | `{node, error}` | 否 |
| review_required | `{node, data, options}` | 否 |
| supervisor_suggestion | `{severity, message, proposed_action}` | 否 |
| workflow_completed | `{workflow_id}` | **是** |
| workflow_error | `{error}` | **是** |
| workflow_failed | `{error}` | **是** |
| workflow_suspended | `{suspended_until, reason}` | **是** |
| workflow_cancelled | `{}` | **是** |
| workflow_terminated | `{}` | **是** |
| shortcut_completed | `{}` | **是** |
| intent_parsed | `{intent, params}` | 否 |
| draft_patch | `{patch}` | 否 |
| card_draft_ready | `{draft}` | 否 |
| agent_chat_error | `{error}` | 否 |

终态事件后 300s 延迟清理订阅。

---

## 三、Chat Agent 对话

### POST /api/v1/chat/sessions
创建对话会话

### GET /api/v1/chat/sessions
列表

### POST /api/v1/chat/sessions/{session_id}/messages
发送消息（触发 ReAct Loop）

```python
# Request
{
  "content": str,                 # 用户消息
  "images_base64": list[str]     # 可选，附带图片
}

# Response: SSE stream
# 事件: intent_parsed → draft_patch → card_draft_ready → node_completed
```

### GET /api/v1/chat/sessions/{session_id}/messages
历史消息

### DELETE /api/v1/chat/sessions/{session_id}
删除会话

---

## 四、Auth 认证

### POST /api/auth/register
注册

### POST /api/auth/login
登录 → JWT

### GET /api/auth/me
当前用户

---

## 五、Profile 画像

### GET /api/profile
获取创作者画像

### PUT /api/profile
更新画像

```python
# 画像字段
{
  "primary_domain": str,          # 必填: tech/beauty/food/travel/education/parenting/fitness/finance/other
  "sub_domain": str | None,
  "tone": str,                    # professional/friendly/lively/serious/humorous
  "visual_style": str,            # warm/cool/minimal/rich
  "taboo_topics": list[str],
  "taboo_words": list[str]
}
```

红线：primary_domain 必填；画像缺失时拒绝启动工作流。

---

## 六、Topic Pool 选题池

### GET /api/topic-pool
列表（分页 + 筛选）

### POST /api/topic-pool
手动添加

### POST /api/topic-pool/search
搜索选题

### PATCH /api/topic-pool/{id}/favorite
收藏/取消收藏

### POST /api/topic-pool/{id}/start-workflow
从选题池发起新工作流

---

## 七、Plugins 插件

### GET /api/plugins
已安装插件列表

### POST /api/plugins/install
安装插件（GitHub URL）

### DELETE /api/plugins/{id}
卸载插件

---

## 八、Assets 资产

### POST /api/assets/upload
上传图片资产

### GET /api/assets
资产列表

---

## 九、其他路由

| 路由前缀 | 文件 | 用途 |
|---------|------|------|
| /api/agents | `agents.py` | Agent 列表/详情 |
| /api/skills | `skills.py` | Skill 列表/详情 |
| /api/config | `config.py` | 前端配置获取 |
| /api/search | `search.py` | 搜索 |
| /api/browser | `browser.py` | 浏览器操作 |
| /api/my-works | `my_works.py` | 我的作品 |
| /api/workspace | `workspace.py` | 工作空间 |
| /api/creative-artifact | `creative_artifact.py` | 创作上下文 |
| /api/quality-gate | `quality_gate.py` | 质量门禁 |
| /api/governance | `governance.py` | 治理信息 |
| /api/memory | `memory.py` | 智能体记忆 |
| /api/proxy | `proxy.py` | 代理 |
| /api/codex | `codex.py` | Codex |
| /api/task-plan | `task_plan.py` | 任务计划 |
| /api/chat | `chat.py` | 旧版对话 (兼容) |
| /api/chat-file | `chat_file.py` | 对话文件 |
| /api/chat-session | `chat_session.py` | 对话会话管理 |
| /api/feishu-oauth | `feishu_oauth.py` | 飞书 OAuth |
| /api/feishu-bot | `feishu_bot.py` | 飞书 Bot |
| /api/wechat-bot | `wechat_bot.py` | 微信 Bot |
| /api/workflow-definitions | `workflow_definitions.py` | 工作流定义 (Phase 2 动态 DAG) |

---

## 十、通用响应格式

```python
# StandardResponse[T]
{
  "success": bool,
  "data": T | None,
  "error": str | None,
  "message": str | None
}
```

鉴权：除 SSE 外均用 `Authorization: Bearer <jwt>`；SSE 用 fetch + Bearer (非 EventSource)。