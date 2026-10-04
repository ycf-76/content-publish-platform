# 数据模型真相源

> 从 `db/models.py` 代码直接提取。每张表的字段、关系、约束与代码一一对应。

| 版本 | v1.0 |
|------|------|
| 生效 | 2026-09-18 |
| 关联 | 01-ARCHITECTURE.md |

---

## 一、ER 关系概览

```
User ──1:1──→ UserProfile
  ├──1:N──→ Workflow
  ├──1:1──→ FeishuOAuthConnection
  └──1:N──→ AgentMemory

Workflow ──1:N──→ WorkflowNode
  ├──1:N──→ WorkflowCheckpoint
  ├──1:N──→ PendingReview
  ├──1:N──→ PendingSuggestion
  └──N:1──→ WorkflowDefinition (可选, Phase 2)

WorkflowNode ──1:N──→ AgentTrace

TopicPoolItem (独立, 按 user_id 软关联)
EstherBrandConfig ──1:1──→ User (按 user_id)
EstherTemplate ──N:1──→ User (按 user_id)
```

---

## 二、核心表

### users
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(26) | PK | ULID |
| email | String(255) | UQ, nullable | 邮箱 |
| password_hash | String(255) | nullable | 密码哈希 |
| nickname | String(128) | | 昵称 |
| created_at | DateTime(tz) | server_default | |
| updated_at | DateTime(tz) | server_default+onupdate | |

### user_profiles (D18 创作者画像)
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(26) | PK | ULID |
| user_id | String(26) | FK→users.id, UQ | 1:1 |
| primary_domain | Enum(PrimaryDomain) | **NOT NULL** | 必填: tech/beauty/food/travel/education/parenting/fitness/finance/other |
| sub_domain | String(50) | nullable | 子领域 |
| tone | Enum(CreatorTone) | default=professional | professional/friendly/lively/serious/humorous |
| visual_style | Enum(VisualStyle) | default=warm | warm/cool/minimal/rich |
| taboo_topics | JSONB | default=[] | 禁忌话题 |
| taboo_words | JSONB | default=[] | 禁忌词 |
| created_at / updated_at | | | |

**红线**：primary_domain 必填；画像缺失时拒绝启动工作流；只存创作偏好，不存敏感个人信息。

### workflows
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(26) | PK | ULID |
| user_id | String(26) | FK→users.id | |
| account_id | String(26) | nullable | |
| definition_id | String(36) | FK→workflow_definitions.id, nullable | Phase 2 动态 DAG，NULL=默认流程 |
| topic | String(500) | | 主题 |
| status | Enum(WorkflowStatus) | default=pending | pending/running/paused/terminated/cancelled/completed/suspended/failed |
| current_node_id | String(26) | nullable | |
| suspended_until | DateTime(tz) | nullable | D15 30分钟挂起 |
| suspension_reason | Text | nullable | |
| execution_mode | String(20) | default="sequential" | sequential / dynamic |
| source | String(20) | default="gui" | gui / chat_agent |
| created_at / updated_at / completed_at | | | |

### workflow_nodes
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(26) | PK | ULID |
| workflow_id | String(26) | FK→workflows.id | |
| node_type | Enum(NodeType) | | search/analyze/copywrite/image_plan/image_gen/image_review/audit/final_review/publish/card_gen/wechat_push/feishu_push |
| node_key | String(64) | | |
| node_status (DB列名: status) | Enum(NodeStatus) | default=pending | pending/running/awaiting_review/passed/rejected/error/suspended/completed/terminated |
| input_data | JSONB | nullable | |
| output_data | JSONB | nullable | D11: 不含原图 base64 |
| error_message | Text | nullable | |
| crash_reason | String(100) | nullable | |
| recovery_attempts | Integer | default=0 | |
| started_at / completed_at | DateTime(tz) | nullable | |
| duration_ms | Integer | nullable | |
| token_usage | Integer | nullable | |
| model_used | String(100) | nullable | |
| created_at / updated_at | | | |

---

## 三、审核与监督表

### pending_reviews
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(26) | PK | |
| workflow_id | String(26) | FK→workflows.id | |
| node_id | String(26) | FK→workflow_nodes.id, nullable | |
| review_type | Enum(ReviewType) | | image_review / final_review / structural_recovery |
| payload | JSONB | nullable | |
| status | Enum(ReviewStatus) | default=pending | pending/approved/rejected/timeout |
| user_decision | JSONB | nullable | |
| decided_at | DateTime(tz) | nullable | |
| expires_at | DateTime(tz) | nullable | |
| created_at | | | |

### pending_suggestions
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(26) | PK | |
| workflow_id | String(26) | FK→workflows.id | |
| node_id | String(26) | FK→workflow_nodes.id, nullable | |
| severity | Enum(SuggestionSeverity) | | info / warning / error |
| suggestion_type | Enum(SuggestionType) | | technical / structural |
| message | Text | | |
| trace | JSONB | nullable | |
| proposed_action | JSONB | nullable | |
| status | Enum(SuggestionStatus) | default=pending | pending/auto_executed/user_confirmed/user_rejected/timeout |
| created_at / resolved_at | | | |

---

## 四、Trace 与 Checkpoint 表

### workflow_checkpoints
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(26) | PK | |
| workflow_id | String(26) | FK→workflows.id | |
| node_id | String(26) | FK→workflow_nodes.id, nullable | |
| langgraph_thread_id | String(100) | | |
| langgraph_checkpoint_id | String(100) | | |
| snapshot_summary | Text | nullable | 人类可读摘要 |
| created_at | | | |

D6: 业务层 checkpoint 索引表（时光机 UI 用）。LangGraph 自身 checkpoint 由 AsyncSqliteSaver 管理。

### agent_traces
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(26) | PK | |
| node_id | String(26) | FK→workflow_nodes.id | |
| event_type | Enum(TraceEventType) | | tool_call_start/tool_call_end/progress_update/model_switched/agent_thinking/decision_made |
| event_payload | JSONB | nullable | |
| raw_data | JSONB | nullable | L3 原始数据 |
| created_at | | | |

---

## 五、选题池表

### topic_pool_items
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(26) | PK | |
| platform | String(32) | | 来源平台 |
| content_id | String(128) | nullable | |
| title | String(500) | | |
| summary | Text | nullable | 原始摘要 |
| content | Text | nullable | 完整内容 |
| url | String(1024) | nullable | |
| author | String(255) | nullable | |
| likes / comments / collects / shares | Integer | default=0 | 互动数据 |
| fans_count | Integer | default=0 | |
| cover_img | String(1024) | nullable | |
| images | JSONB | nullable | |
| source_keyword | String(500) | nullable | |
| is_favorited | Boolean | default=False | |
| raw | JSONB | nullable | 原始抓取数据 |
| auto_source | String(20) | default="manual" | manual / monitor |
| simhash_fingerprint | String(64) | nullable | 去重指纹 |
| heat_score | Float | default=0.0 | 热度评分 |
| heat_status | String(20) | default="活跃" | |
| dimensions | JSONB | nullable | 热度维度 |
| published_at | DateTime(tz) | nullable | |
| tags | JSONB | nullable | AI 提取标签 |
| ai_summary | Text | nullable | AI 深度摘要 |
| view_count | Integer | default=0 | |
| ai_summary_generated_at | DateTime(tz) | nullable | |
| created_at | | | |

---

## 六、智能体记忆表

### agent_memories
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(26) | PK | |
| user_id | String(26) | FK→users.id | |
| memory_type | Enum(MemoryType) | | preferences / topic_history / copywrite_history / publish_history / my_works_summary / my_attribution / avoid_patterns |
| memory_key | String(64) | | 细分键 |
| memory_value | JSONB | | 具体内容 |
| source | String(32) | default="workflow_inferred" | user_explicit / workflow_inferred / publish_feedback |
| workflow_id | String(26) | nullable | 来源工作流 |
| importance | Float | default=0.5 | |
| created_at / updated_at | | | |

同一 (user_id, memory_type, memory_key) 唯一，upsert 更新。

---

## 七、飞书 OAuth 表

### feishu_oauth_connections
| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(26) | PK | |
| user_id | String(26) | FK→users.id, UQ | |
| open_id | String(128) | nullable | |
| user_name | String(255) | nullable | |
| access_token_encrypted | Text | | AES-GCM 密文 |
| refresh_token_encrypted | Text | nullable | |
| access_token_expires_at / refresh_token_expires_at | DateTime(tz) | nullable | |
| scopes | Text | nullable | |
| created_at / updated_at | | | |

### feishu_oauth_states
短期 OAuth state/PKCE 状态，防回调伪造。

---

## 八、Esther Factory 表

### esther_brand_configs
每用户一行，品牌配置（品牌名/性别/主色/强调色/点缀色/头像 base64）。

### esther_templates
每用户每模板一行，卡片模板（schema_json + template_html + meta_json + scene）。

---

## 九、枚举汇总

| 枚举 | 值 | 用途 |
|------|---|------|
| WorkflowStatus | pending / running / paused / terminated / cancelled / completed / suspended / failed | 工作流状态 |
| NodeState | search / analyze / image_gen / image_review / copywrite / audit / final_review / publish / end | 节点类型(旧) |
| NodeType | search / analyze / copywrite / image_plan / image_gen / image_review / audit / final_review / publish / image_workshop / card_gen / wechat_push / feishu_push | 节点类型(新) |
| NodeStatus | pending / running / awaiting_review / passed / rejected / error / suspended / completed / terminated | 节点状态(9种) |
| PrimaryDomain | tech / beauty / food / travel / education / parenting / fitness / finance / other | 创作者主领域 |
| CreatorTone | professional / friendly / lively / serious / humorous | 内容调性 |
| VisualStyle | warm / cool / minimal / rich | 视觉风格 |
| ReviewType | image_review / final_review / structural_recovery | 审核类型 |
| ReviewStatus | pending / approved / rejected / timeout | 审核状态 |
| SuggestionSeverity | info / warning / error | 建议严重级别 |
| SuggestionType | technical / structural | 建议类型 |
| SuggestionStatus | pending / auto_executed / user_confirmed / user_rejected / timeout | 建议状态 |
| TraceEventType | tool_call_start / tool_call_end / progress_update / model_switched / agent_thinking / decision_made | Trace 事件类型 |
| MemoryType | preferences / topic_history / copywrite_history / publish_history / my_works_summary / my_attribution / avoid_patterns | 记忆类型 |

---

## 十、数据库策略

| 环境 | 引擎 | 连接串示例 |
|------|------|-----------|
| dev | SQLite + aiosqlite | `sqlite+aiosqlite:///./data/xhs_agent.db` |
| prod | MySQL + aiomysql | `mysql+aiomysql://user:pass@host/db` |
| 可选 | PostgreSQL + asyncpg | `postgresql+asyncpg://user:pass@host/db` |

- JSONB：PostgreSQL 用原生 JSONB；SQLite/MySQL 降级为 JSON
- Checkpointer：LangGraph 用 AsyncSqliteSaver (`data/langgraph_checkpoints.sqlite`)，WAL 模式
- 连接池：pool_size=20, max_overflow=40
- ID 生成：全部 ULID (26字符, 时间有序)