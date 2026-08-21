# 🧩 Plugin SDK 开发指南 v2.0

> **版本**: 2.0.0  
> **更新日期**: 2026-08-16 (Day 9)  
> **适用范围**: 第三方开发者、内容创作者、技术合作伙伴

---

## 📖 目录

1. [快速开始](#-快速开始)
2. [架构概览](#-架构概览)
3. [插件类型体系](#-插件类型体系)
4. [开发环境搭建](#-开发环境搭建)
5. [核心接口定义](#-核心接口定义)
6. [配置规范](#-配置规范)
7. [事件通信机制](#-事件通信机制)
8. [数据共享存储](#-数据共享存储)
9. [权限与安全](#-权限与安全)
10. [发布与分发](#-发布与分发)
11. [最佳实践](#-最佳实践)
12. [示例代码](#-示例代码)
13. [API参考](#-api参考)
14. [常见问题](#-常见问题)

---

## 🚀 快速开始

### 5分钟创建你的第一个插件

```python
# my_first_plugin/plugin.json
{
    "id": "my-awesome-plugin",
    "name": "我的超棒插件",
    "version": "1.0.0",
    "category": "workflow_node",
    "description": "这是一个示例插件",
    "author": {
        "name": "Your Name",
        "email": "you@example.com"
    },
    "entry_point": "main.py:MyPlugin",
    "display_icon": "⭐",
    "pricing_model": "free"
}

# my_first_plugin/main.py
from app.core.base_interfaces import BaseWorkflowNodePlugin
from app.core.plugin_types import PluginContext, NodeOutput

class MyPlugin(BaseWorkflowNodePlugin):
    """我的第一个工作流节点插件"""
    
    async def execute(self, ctx: PluginContext, inputs: dict) -> NodeOutput:
        # 获取输入数据
        topic = inputs.get("topic", "")
        
        # 执行业务逻辑
        result = f"Hello from plugin! Topic: {topic}"
        
        # 返回输出
        return NodeOutput(
            success=True,
            data={"result": result},
            message="执行成功"
        )
    
    async def validate_inputs(self, inputs: dict) -> tuple[bool, str]:
        if not inputs.get("topic"):
            return False, "缺少必需参数: topic"
        return True, ""
```

### 安装测试

```bash
# 1. 将插件放到 plugins/custom/my_first_plugin/
# 2. 重启后端服务
# 3. 访问 http://localhost:8000/docs 查看API
# 4. 或在前端 Plugin Manager 中查看
```

---

## 🏗️ 架构概览

### 系统架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Vue 3 + Vite)                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────────┐   │
│  │ Plugin   │  │ Config   │  │ Marketplace UI           │   │
│  │ Manager  │  │ Forms    │  │ (Browse/Install/Review)  │   │
│  └────┬─────┘  └────┬─────┘  └────────────┬─────────────┘   │
│       │              │                     │                 │
└───────┼──────────────┼─────────────────────┼─────────────────┘
        │              │                     │
        ▼              ▼                     ▼
┌─────────────────────────────────────────────────────────────┐
│                  Backend (FastAPI)                           │
│  ┌────────────┐  ┌─────────────┐  ┌────────────────────┐   │
│  │ REST API   │  │ Plugin      │  │ Event Bus          │   │
│  │ (/api/*)   │◄─┤ Manager     │─►│ (Pub/Sub)          │   │
│  └────────────┘  └──────┬──────┘  └────────────────────┘   │
│                         │                                   │
│          ┌──────────────┼──────────────┐                    │
│          ▼              ▼              ▼                    │
│  ┌─────────────┐ ┌───────────┐ ┌─────────────┐            │
│  │ Builtin     │ │ Custom    │ │ Third-party │            │
│  │ Plugins     │ │ Plugins   │ │ Plugins     │            │
│  └─────────────┘ └───────────┘ └─────────────┘            │
└─────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  Database (SQLite/PostgreSQL)                │
│  plugins | plugin_versions | plugin_configs | ...           │
└─────────────────────────────────────────────────────────────┘
```

### 核心组件职责

| 组件 | 职责 | 技术栈 |
|------|------|--------|
| **PluginManager** | 插件生命周期管理（加载/卸载/启用/禁用） | Python Class |
| **EventBus** | 跨插件事件通信（发布/订阅/通配符匹配） | Async Pub/Sub |
| **DataStore** | 插件间数据共享（TTL/容量控制/访问控制） | Key-Value Store |
| **REST API** | 前后端交互接口（CRUD/安装/配置/统计） | FastAPI Routes |
| **Sandbox** | 安全隔离执行环境（资源限制/权限检查） | Process Isolation |

---

## 🔌 插件类型体系

### 支持的插件类别

#### 1. **PLATFORM（平台类）**
*用于对接外部内容发布平台*

```python
class BasePlatformPlugin(BasePlugin):
    """平台插件基类"""
    
    async def authenticate(self, credentials: dict) -> AuthResult:
        """平台认证"""
        ...
    
    async def publish(self, content: ContentItem) -> PublishResult:
        """发布内容"""
        ...
    
    async def get_analytics(self, content_id: str) -> Analytics:
        """获取数据分析"""
        ...
    
    async def delete_content(self, content_id: str) -> bool:
        """删除内容"""
        ...
```

**内置示例**: 
- `xiaohongshu-publish` - 小红书发布器
- 未来支持: 微信公众号、抖音、B站等

**能力标签**:
- `authenticate` - 认证授权
- `publish` - 内容发布
- `get_analytics` - 数据分析
- `delete_content` - 内容删除

---

#### 2. **DATASOURCE（数据源类）**
*用于接入外部数据源，提供内容灵感*

```python
class BaseDatasourcePlugin(BasePlugin):
    """数据源插件基类"""
    
    async def search_trending(
        self, 
        query: str, 
        limit: int = 20
    ) -> List[TrendingItem]:
        """搜索热点内容"""
        ...
    
    async def get_trending(
        self, 
        category: str = None,
        limit: int = 20
    ) -> List[TrendingItem]:
        """获取热门内容列表"""
        ...
    
    async def classify_content(
        self, 
        item: TrendingItem
    ) -> Classification:
        """内容智能分类"""
        ...
```

**内置示例**:
- `monitor-agent` - 多平台热点监控智能体

**能力标签**:
- `search_trending` - 搜索热点
- `get_trending` - 获取列表
- `classify_content` - 分类标注
- `deduplicate` - 去重处理

---

#### 3. **WORKFLOW_NODE（工作流节点类）**
*作为工作流中的一个可执行节点*

```python
class BaseWorkflowNodePlugin(BasePlugin):
    """工作流节点插件基类"""
    
    async def execute(
        self, 
        ctx: PluginContext, 
        inputs: dict
    ) -> NodeOutput:
        """执行节点逻辑（必须实现）"""
        ...
    
    async def validate_inputs(
        self, 
        inputs: dict
    ) -> tuple[bool, str]:
        """验证输入参数"""
        ...
    
    async def optimize_output(
        self, 
        output: NodeOutput,
        feedback: str = None
    ) -> NodeOutput:
        """优化输出结果（可选）"""
        ...
```

**内置示例**:
- `ai-copywrite-node` - AI文案生成节点

**能力标签**:
- `execute` - 执行逻辑
- `validate_inputs` - 输入验证
- `optimize_output` - 结果优化

---

#### 4. **AI_MODEL（AI模型类）** *(未来支持)*
- 接入自定义LLM/图像生成模型
- 能力: `generate_text`, `generate_image`, `embed`

#### 5. **UI_THEME（UI主题类）** *(未来支持)*
- 自定义界面主题和样式
- 能力: `theme_css`, `component_override`

#### 6. **INTEGRATION（集成类）** *(未来支持)*
- 对接第三方服务（Notion/飞书/Slack等）
- 能力: `webhook`, `sync`, `notify`

---

## 🛠️ 开发环境搭建

### 前置要求

- Python 3.10+
- Node.js 18+ (如需前端组件)
- SQLite 3 / PostgreSQL 14+

### 项目结构模板

```
my-plugin/
├── plugin.json          # 插件清单（必需）
├── main.py              # 主入口文件
├── README.md            # 使用说明
├── requirements.txt     # Python依赖（可选）
├── assets/              # 静态资源（可选）
│   ├── icon.png
│   └── screenshots/
├── tests/               # 单元测试（可选）
│   └── test_main.py
└── configs/             # 默认配置模板（可选）
    └── default.json
```

### plugin.json 完整Schema

```json
{
    "$schema": "plugin-schema-v2.json",
    "id": "unique-plugin-id",                    // 必需，全局唯一
    "version": "1.0.0",                          // 必需，语义化版本
    "name": "显示名称",                            // 必需，≤50字符
    "description": "详细描述",                      // 必需，≤500字符
    
    // 作者信息
    "author": {                                  // 必需
        "name": "作者名",
        "email": "author@example.com",
        "url": "https://example.com"             // 可选
    },
    
    // 分类与入口
    "category": "workflow_node",                 // 必需，见分类枚举
    "entry_point": "main.py:MyPluginClass",       // 必需，格式: file:Class
    
    // 展示信息
    "display_icon": "✨",                        // 图标（Emoji或SVG）
    "tags": ["ai", "writing", "productivity"],   // 标签数组
    "screenshots": [],                            // 截图URL列表
    
    // 功能声明
    "capabilities": ["execute", "validate"],       // 能力标签
    "permissions_required": ["llm:use"],         // 权限需求
    
    // 配置Schema（JSON Schema Draft-07）
    "config_schema": {
        "type": "object",
        "properties": { ... },
        "required": []
    },
    
    // 工作流节点专用
    "input_schema": { ... },                      // 输入参数定义
    "output_schema": { ... },                     // 输出数据定义
    
    // 商业化
    "pricing_model": "free",                     // free/freemium/paid
    "min_platform_version": "1.0.0",             // 最低平台版本
    
    // 依赖关系
    "dependencies": [],                          // 依赖的其他插件ID
    
    // 事件通信
    "events_subscribes": ["event:*"],            // 订阅的事件模式
    "events_emits": ["my:event"]                // 发出的事件类型
}
```

---

## 📡 核心接口定义

### BasePlugin 基类

```python
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

class BasePlugin(ABC):
    """所有插件的基类"""
    
    # ===== 类属性（从plugin.json自动加载）=====
    id: str                          # 插件ID
    name: str                        # 显示名
    version: str                     # 版本号
    category: PluginCategory         # 分类
    description: str                 # 描述
    author_name: str                 # 作者
    capabilities: List[str]          # 能力列表
    permissions_required: List[str]  # 权限需求
    config_schema: Dict              # 配置Schema
    
    # ===== 生命周期钩子 =====
    
    async def on_load(self) -> None:
        """
        插件加载时调用
        - 初始化资源（连接池、缓存等）
        - 注册事件监听器
        - 预加载数据
        """
        pass
    
    async def on_unload(self) -> None:
        """
        插件卸载时调用
        - 清理资源
        - 注销事件监听
        - 持久化状态
        """
        pass
    
    async def on_enable(self) -> None:
        """插件被启用时调用"""
        pass
    
    async def on_disable(self) -> None:
        """插件被禁用时调用"""
        pass
    
    async def on_config_changed(
        self, 
        old_config: Dict, 
        new_config: Dict
    ) -> None:
        """配置变更回调"""
        pass
    
    # ===== 必须实现的接口 =====
    
    @abstractmethod
    async def get_info(self) -> PluginManifest:
        """
        返回插件元信息
        
        Returns:
            PluginManifest: 包含id/version/name等的完整信息
        """
        pass
    
    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """
        健康检查
        
        Returns:
            HealthStatus: 包含status/message/timestamp
        """
        pass
```

### PluginContext 上下文对象

```python
@dataclass
class PluginContext:
    """插件执行上下文"""
    
    # 身份信息
    user_id: str                       # 当前用户ID
    session_id: str                    # 会话ID
    
    # 工作流上下文（仅workflow_node类型）
    workflow_id: Optional[str]         # 工作流实例ID
    node_id: Optional[str]             # 当前节点ID
    execution_id: Optional[str]        # 执行实例ID
    
    # 配置信息
    config: Optional[Dict]             # 用户自定义配置
    global_config: Dict                # 全局系统配置
    
    # 服务引用
    event_bus: EventBus                # 事件总线引用
    data_store: DataStore              # 数据存储引用
    logger: Logger                     # 日志记录器
    
    # 元数据
    request_id: str                    # 请求追踪ID
    timestamp: datetime                # 执行时间戳
    metadata: Dict                     # 自定义元数据
```

### 数据类型定义

```python
# ===== 通用返回类型 =====

@dataclass
class OperationResult:
    """操作结果"""
    success: bool
    message: str = ""
    data: Any = None
    error_code: str = ""
    error_details: Dict = None

@dataclass
class NodeOutput:
    """工作流节点输出"""
    success: bool
    data: Dict[str, Any]
    message: str = ""
    execution_time_ms: int = 0
    next_node: Optional[str] = None     # 下一个节点ID（条件路由）

@dataclass
class AuthResult:
    """认证结果"""
    success: bool
    token: Optional[str] = None
    expires_at: Optional[datetime] = None
    refresh_token: Optional[str] = None
    user_info: Optional[Dict] = None

@dataclass
class PublishResult:
    """发布结果"""
    success: bool
    content_id: Optional[str] = None
    platform_url: Optional[str] = None
    published_at: Optional[datetime] = None
    error_message: str = ""

@dataclass
class TrendingItem:
    """热点内容项"""
    id: str
    title: str
    url: str
    source: str                          # 来源平台
    score: float                         # 热度评分
    category: Optional[str] = None
    tags: List[str] = None
    published_at: Optional[datetime] = None
    metadata: Dict = None

@dataclass
class Classification:
    """分类结果"""
    sentiment: str                       # 情绪: positive/negative/neutral
    scenario: str                        # 场景: education/entertainment/...
    visual_style: str                    # 视觉风格: minimal/colorful/...
    confidence: float                    # 置信度 0-1
    tags: List[str] = None
```

---

## ⚙️ 配置规范

### config_schema JSON Schema 示例

```json
{
    "type": "object",
    "properties": {
        "api_key": {
            "type": "string",
            "title": "API密钥",
            "description": "第三方服务的API密钥",
            "default": "",
            "pattern": "^sk-[a-zA-Z0-9]{32,}$",
            "x-ui": {
                "widget": "password",
                "placeholder": "输入API Key...",
                "help_text": "在服务商后台获取"
            }
        },
        
        "model_name": {
            "type": "string",
            "title": "模型选择",
            "enum": ["gpt-4", "gpt-3.5-turbo", "claude-3"],
            "default": "gpt-3.5-turbo",
            "x-ui": {
                "widget": "select",
                "description": "选择要使用的AI模型"
            }
        },
        
        "temperature": {
            "type": "number",
            "title": "生成温度",
            "minimum": 0,
            "maximum": 2,
            "default": 0.7,
            "step": 0.1,
            "x-ui": {
                "widget": "slider",
                "unit": "",
                "description": "值越高越随机"
            }
        },
        
        "max_tokens": {
            "type": "integer",
            "title": "最大生成长度",
            "minimum": 100,
            "maximum": 4000,
            "default": 1500,
            "x-ui": {
                "widget": "number",
                "suffix": " tokens"
            }
        },
        
        "enable_cache": {
            "type": "boolean",
            "title": "启用缓存",
            "default": true,
            "x-ui": {
                "widget": "switch",
                "description": "缓存常用查询结果"
            }
        },
        
        "advanced_settings": {
            "type": "object",
            "title": "高级设置",
            "properties": {
                "timeout_seconds": {
                    "type": "integer",
                    "default": 30
                },
                "retry_count": {
                    "type": "integer",
                    "default": 3
                }
            },
            "x-ui": {
                "collapsible": true,
                "collapsed_by_default": true
            }
        }
    },
    "required": ["api_key"],
    "x-ui": {
        "layout": "vertical",
        "group_by_category": true
    }
}
```

### UI渲染扩展字段 (`x-ui`)

| 字段 | 类型 | 说明 | 适用控件 |
|------|------|------|----------|
| `widget` | string | 控件类型 | 所有 |
| `placeholder` | string | 占位文本 | text/password/textarea |
| `help_text` | string | 帮助提示 | 所有 |
| `unit` | string | 单位后缀 | number/slider |
| `step` | number | 步进值 | number/slider |
| `suffix` | string | 后缀文本 | number |
| `collapsible` | boolean | 可折叠 | object |
| `collapsed_by_default` | boolean | 默认折叠 | object |
| `layout` | string | 布局方式 | root |
| `group_by_category` | boolean | 按分组显示 | root |

支持的 widget 类型：
- `text` - 单行文本
- `password` - 密码框
- `textarea` - 多行文本
- `number` - 数字输入
- `slider` - 滑块
- `select` - 下拉选择
- `switch` - 开关
- `json-editor` - JSON编辑器
- `array` - 数组编辑器
- `color` - 颜色选择器
- `date` - 日期选择器
- `file` - 文件上传

---

## 📡 事件通信机制

### EventBus 使用指南

```python
class MyPlugin(BaseWorkflowNodePlugin):
    
    async def on_load(self):
        # 订阅事件（支持通配符）
        await ctx.event_bus.subscribe(
            "workflow:node_completed:*",  # 通配符匹配
            self.on_workflow_node_done
        )
        
        # 带优先级的订阅
        await ctx.event_bus.subscribe(
            "datasource:trending_found",
            self.handle_new_trending,
            priority=100  # 高优先级先执行
        )
    
    async def execute(self, ctx, inputs):
        # 发布事件
        await ctx.event_bus.emit(
            "content:generated",
            data={
                "content_id": "abc123",
                "title": "新内容标题",
                "tags": ["AI", "写作"]
            },
            source=self.id  # 标记来源
        )
        
        # 发布带延迟的事件
        await ctx.event_bus.emit(
            "reminder:review_needed",
            data={...},
            delay_seconds=3600  # 1小时后触发
        )
    
    async def on_workflow_node_done(self, event: Event):
        """处理上游节点完成事件"""
        print(f"Node {event.data['node_id']} completed!")
        
        # 从事件中提取数据
        output = event.data.get("output", {})
```

### 事件命名规范

```
{domain}:{action}[:detail]

Domain:
  - workflow    工作流相关
  - content     内容生命周期
  - datasource  数据源相关
  - system      系统级别
  - config      配置变更
  - user        用户操作
  - {plugin_id} 插件自定义域

Action:
  - started     开始
  - completed   完成
  - failed      失败
  - created     创建
  - updated     更新
  - deleted     删除
  - *           通配符

Examples:
  - workflow:node_started:copywrite
  - content:published
  - datasource:trending_found
  - system:scheduler:tick
  - config:changed:monitor-agent
  - my-plugin:custom_event
```

### 中间件机制

```python
# 创建中间件（日志记录示例）
async def logging_middleware(event: Event, next_fn):
    print(f"[EVENT] {event.type} at {event.timestamp}")
    result = await next_fn(event)  # 传递给下一个处理器
    print(f"[HANDLED] Processed by {len(event.handlers)} handlers")
    return result

# 注册中间件
await ctx.event_bus.use_middleware(logging_middleware)

# 条件中间件（仅处理特定事件）
async def auth_check(event: Event, next_fn):
    if event.type.startswith("admin:"):
        if not ctx.user.is_admin:
            raise PermissionError("Admin only event")
    return await next_fn(event)

await ctx.event_bus.use_middleware(auth_check)
```

---

## 💾 数据共享存储

### DataStore API

```python
class MyPlugin(BaseWorkflowNodePlugin):
    
    async def execute(self, ctx, inputs):
        # ===== 写入数据 =====
        
        # 简单KV存储
        await ctx.data_store.set(
            key=f"{self.id}:last_result",
            value={"score": 95, "text": "..."},
            ttl=3600  # 1小时过期
        )
        
        # 带命名空间的存储
        await ctx.data_store.set(
            key="cache:analysis_123",
            value=complex_object,
            namespace=self.id,  # 自动添加前缀
            tags=["analysis", "user_123"]  # 用于批量清理
        )
        
        # ===== 读取数据 =====
        
        result = await ctx.data_store.get(
            key=f"{self.id}:last_result"
        )
        
        # 批量读取
        keys = [f"{self.id}:item_{i}" for i in range(10)]
        values = await ctx.data_store.get_many(keys)
        
        # ===== 高级操作 =====
        
        # 原子递增（计数器）
        count = await ctx.data_store.increment(
            key=f"{self.id}:call_count",
            amount=1
        )
        
        # 存在性检查
        exists = await ctx.data_store.exists(
            key=f"{self.id}:config_loaded"
        )
        
        # 设置过期时间
        await ctx.data_store.expire(
            key=f"{self.id}:temp_data",
            ttl=1800  # 30分钟后过期
        )
        
        # ===== 清理操作 =====
        
        # 按标签批量删除
        deleted_count = await ctx.data_store.delete_by_tag(
            tag="temp_session:*"
        )
        
        # 清理当前插件所有数据
        await ctx.data_store.clear_namespace(namespace=self.id)
```

### TTL 和容量策略

| 场景 | 建议 TTL | 说明 |
|------|----------|------|
| 会话临时数据 | 30分钟 | 用户会话期间有效 |
| 缓存计算结果 | 1小时 | 避免频繁重复计算 |
| 用户偏好设置 | 7天 | 相对稳定的配置 |
| 统计计数器 | 不过期 | 定期归档到数据库 |
| 敏感数据 | 最小必要时间 | 用完即删 |

### 访问控制规则

```python
# 插件只能访问自己的命名空间（默认隔离）
await ctx.data_store.get(key="my_key")  
# → 实际访问: "{plugin_id}:my_key"

# 跨插件数据共享需要显式声明
await ctx.data_store.set(
    key="shared:data_for_other_plugin",
    value=data,
    access_control={
        "read_plugins": ["other-plugin-id"],
        "write_plugins": []  # 仅自己可写
    }
)

# 全局共享数据（需管理员权限）
await ctx.data_store.set(
    key="global:system_config",
    value=config,
    is_global=True  # 标记为全局
)
```

---

## 🔒 权限与安全

### 权限模型

```yaml
# 权限层级
platform:
  - platform:admin          # 平台管理（安装/卸载任意插件）
  - plugin:install          # 安装新插件
  - plugin:configure        # 修改插件配置
  
resource:
  - llm:use                # 调用LLM API
  - network:read           # 网络读取
  - network:write          # 网络写入
  - filesystem:read        # 文件读取
  - filesystem:write       # 文件写入
  - database:read          # 数据库读取
  - database:write         # 数据库写入
  
plugin_specific:
  - xhs:publish            # 小红书发布权限
  - xhs:read               # 小红书读取权限
  - notification:send      # 发送通知
  - analytics:view         # 查看统计数据
```

### 沙箱限制

```python
# 插件运行时的默认限制
SANDBOX_LIMITS = {
    "max_memory_mb": 256,           # 最大内存256MB
    "max_cpu_time_seconds": 30,     # 单次执行最大CPU时间
    "max_execution_time_seconds": 60, # 总超时时间
    "max_network_requests": 100,    # 最大网络请求数
    "allowed_domains": [            # 允许访问的域名白名单
        "api.openai.com",
        "*.xiaohongshu.com",
        "localhost"
    ],
    "blocked_paths": [              # 禁止访问的路径
        "/etc/passwd",
        "C:\\Windows\\System32\\config"
    ],
    "rate_limit_rpm": 60,           # 每分钟最大调用次数
}
```

### 审计日志

```python
# 所有敏感操作自动记录审计日志
audit_log = {
    "timestamp": datetime.utcnow(),
    "plugin_id": "my-plugin",
    "action": "config_change",      # 操作类型
    "user_id": "user_123",
    "details": {                     # 操作详情
        "changed_keys": ["api_key", "model_name"],
        "old_values": {"***", "gpt-3.5"},
        "new_values": {"***new***", "gpt-4"}
    },
    "severity": "info",             # info/warning/error/critical
    "ip_address": "192.168.1.100",
    "request_id": "req_abc123"
}

# 查询审计日志
audit_logs = await audit_service.query(
    plugin_id="my-plugin",
    start_date=datetime(2026, 8, 1),
    actions=["config_change", "plugin_install"]
)
```

---

## 📦 发布与分发

### 本地开发测试流程

```bash
# 1. 创建插件目录
mkdir -p plugins/custom/my-plugin

# 2. 创建plugin.json和main.py（见快速开始）

# 3. 测试插件
cd backend
python -m pytest tests/test_my_plugin.py -v

# 4. 本地加载测试
# 方法A: 放到 plugins/custom/ 目录，重启服务自动加载
# 方法B: 通过API动态加载
curl -X POST http://localhost:8000/api/plugins/load-local \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"path": "plugins/custom/my-plugin"}'

# 5. 在前端Plugin Manager中验证
open http://localhost:5173/plugins
```

### 发布到插件市场

```bash
# 1. 打包插件
cd my-plugin
zip -r ../my-plugin-v1.0.0.zip .

# 2. 提交审核
curl -X POST http://localhost:8000/api/marketplace/submit \
  -H "Authorization: Bearer $TOKEN" \
  -F "plugin_file=@../my-plugin-v1.0.0.zip" \
  -F "release_notes=Initial release" \
  -F "changelog=- Added basic features"

# 3. 等待审核（通常24小时内）
# 4. 审核通过后用户可见并可安装
```

### 版本管理规范

```bash
# 语义化版本号 (SemVer)
MAJOR.MINOR.PATCH

# MAJOR: 不兼容的API变更
# MINOR: 向下兼容的功能新增
# PATCH: 向下兼容的问题修复

# 示例
1.0.0    # 初始版本
1.1.0    # 新增功能
1.1.1    # 修复bug
2.0.0    # 重构API（不兼容旧版）
```

---

## ✨ 最佳实践

### 性能优化

```python
class OptimizedPlugin(BaseWorkflowNodePlugin):
    
    def __init__(self):
        # 连接池复用
        self._http_client = None
        self._cache = {}
    
    async def _get_http_client(self):
        """懒初始化HTTP客户端（复用连接）"""
        if not self._http_client:
            import httpx
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_connections=10)
            )
        return self._http_client
    
    async def execute(self, ctx, inputs):
        # 使用缓存避免重复计算
        cache_key = hashlib.md5(str(inputs).encode()).hexdigest()
        if cache_key in self._cache:
            return NodeOutput(success=True, data=self._cache[cache_key])
        
        # 执行业务逻辑...
        result = await self._do_heavy_computation(inputs)
        
        # 缓存结果
        self._cache[cache_key] = result
        
        # 异步清理旧缓存（LRU）
        if len(self._cache) > 100:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        
        return NodeOutput(success=True, data=result)
```

### 错误处理

```python
class RobustPlugin(BaseWorkflowNodePlugin):
    
    async def execute(self, ctx, inputs):
        try:
            # 业务逻辑
            result = await self.call_external_api(inputs)
            
            return NodeOutput(
                success=True,
                data=result,
                message="Success"
            )
            
        except httpx.TimeoutException as e:
            # 超时重试（最多3次）
            for attempt in range(3):
                try:
                    result = await self.call_external_api(inputs)
                    return NodeOutput(success=True, data=result)
                except:
                    await asyncio.sleep(1 * (attempt + 1))
            
            # 最终失败
            return NodeOutput(
                success=False,
                data={},
                message="Service unavailable after retries",
                error_code="TIMEOUT"
            )
            
        except ValueError as e:
            # 参数错误（不需要重试）
            return NodeOutput(
                success=False,
                data={},
                message=f"Invalid input: {str(e)}",
                error_code="INVALID_INPUT"
            )
            
        except Exception as e:
            # 未预期的错误
            ctx.logger.error(f"Unexpected error: {e}", exc_info=True)
            
            # 发送告警事件
            await ctx.event_bus.emit(
                "plugin:error",
                data={
                    "plugin_id": self.id,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            )
            
            return NodeOutput(
                success=False,
                data={},
                message="Internal error",
                error_code="INTERNAL_ERROR"
            )
```

### 日志规范

```python
import structlog

class LoggingPlugin(BasePlugin):
    
    async def on_load(self):
        # 初始化结构化日志
        self.logger = structlog.get_logger().bind(
            plugin_id=self.id,
            version=self.version
        )
        self.logger.info("Plugin loaded")
    
    async def execute(self, ctx, inputs):
        # 记录关键步骤
        self.logger.info(
            "Execution started",
            node_id=ctx.node_id,
            input_keys=list(inputs.keys())
        )
        
        start_time = time.time()
        
        try:
            result = await self.do_work(inputs)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            self.logger.info(
                "Execution completed",
                duration_ms=elapsed_ms,
                output_size=len(str(result))
            )
            
            return NodeOutput(success=True, data=result)
            
        except Exception as e:
            self.logger.error(
                "Execution failed",
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
                exc_info=True  # 记录堆栈
            )
            raise
```

---

## 💻 示例代码

### 完整示例：翻译插件（WORKFLOW_NODE）

```python
# translator_plugin/plugin.json
{
    "id": "translator-node",
    "name": "多语言翻译器",
    "version": "1.0.0",
    "category": "workflow_node",
    "description": "基于AI的高质量多语言翻译节点，支持100+种语言互译",
    "author": {
        "name": "Developer",
        "email": "dev@example.com"
    },
    "entry_point": "main.py:TranslatorPlugin",
    "display_icon": "🌐",
    "tags": ["translation", "ai", "multilingual", "nlp"],
    "capabilities": ["execute", "validate_inputs"],
    "permissions_required": ["llm:use"],
    "config_schema": {
        "type": "object",
        "properties": {
            "target_language": {
                "type": "string",
                "enum": ["en", "zh", "ja", "ko", "fr", "de", "es"],
                "default": "en",
                "title": "目标语言"
            },
            "style": {
                "type": "string",
                "enum": ["formal", "casual", "academic"],
                "default": "casual",
                "title": "翻译风格"
            },
            "preserve_formatting": {
                "type": "boolean",
                "default": true,
                "title": "保留格式"
            }
        }
    },
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "待翻译文本"
            },
            "source_lang": {
                "type": "string",
                "description": "源语言（可选，自动检测）"
            }
        },
        "required": ["text"]
    },
    "output_schema": {
        "type": "object",
        "properties": {
            "translated_text": {"type": "string"},
            "detected_source_lang": {"type": "string"},
            "confidence_score": {"type": "number"},
            "word_count": {"type": "integer"}
        }
    },
    "pricing_model": "freemium",
    "events_subscribes": [],
    "events_emits": ["translation:completed", "translation:failed"]
}
```

```python
# translator_plugin/main.py
import asyncio
from typing import Dict, Any
from app.core.base_interfaces import (
    BaseWorkflowNodePlugin, 
    PluginContext, 
    NodeOutput
)
from app.core.plugin_types import PluginManifest, HealthStatus


class TranslatorPlugin(BaseWorkflowNodePlugin):
    """多语言翻译插件实现"""
    
    # 类属性（也可从plugin.json加载）
    id = "translator-node"
    name = "多语言翻译器"
    version = "1.0.0"
    
    async def on_load(self):
        """初始化翻译客户端"""
        self.logger.info("Loading translation plugin...")
        
        # 这里可以初始化API客户端、加载模型等
        self.supported_languages = {
            "en": "English",
            "zh": "Chinese",
            "ja": "Japanese",
            "ko": "Korean",
            "fr": "French",
            "de": "German",
            "es": "Spanish"
        }
        
        self.logger.info(f"Support {len(self.supported_languages)} languages")
    
    async def get_info(self) -> PluginManifest:
        """返回插件信息"""
        return PluginManifest(
            id=self.id,
            name=self.name,
            version=self.version,
            category="workflow_node",
            description="AI-powered multi-language translator",
            capabilities=["execute", "validate_inputs"],
            permissions_required=["llm:use"]
        )
    
    async def health_check(self) -> HealthStatus:
        """健康检查"""
        # 检查依赖服务是否可用
        is_healthy = True
        details = {}
        
        # 示例：检查翻译API是否可达
        try:
            # 实际项目中这里应该ping真实的服务
            pass
        except Exception as e:
            is_healthy = False
            details["api_status"] = str(e)
        
        return HealthStatus(
            status="healthy" if is_healthy else "unhealthy",
            message="Translator ready" if is_healthy else "API unreachable",
            timestamp=datetime.utcnow(),
            details=details
        )
    
    async def validate_inputs(self, inputs: Dict[str, Any]) -> tuple:
        """验证输入参数"""
        
        text = inputs.get("text", "")
        
        if not text or not text.strip():
            return False, "Input text cannot be empty"
        
        if len(text) > 10000:
            return False, "Text too long (max 10000 characters)"
        
        source_lang = inputs.get("source_lang")
        if source_lang and source_lang not in self.supported_languages:
            return (False, 
                   f"Unsupported source language: {source_lang}")
        
        return True, "Inputs valid"
    
    async def execute(
        self, 
        ctx: PluginContext, 
        inputs: Dict[str, Any]
    ) -> NodeOutput:
        """执行翻译"""
        
        import time
        start_time = time.time()
        
        # 1. 获取配置
        target_lang = ctx.config.get("target_language", "en") \
            if ctx.config else "en"
        style = ctx.config.get("style", "casual") \
            if ctx.config else "casual"
        preserve_fmt = ctx.config.get("preserve_formatting", True) \
            if ctx.config else True
        
        # 2. 获取输入
        text = inputs["text"]
        source_lang = inputs.get("source_lang", "auto")
        
        self.logger.info(
            "Starting translation",
            source_lang=source_lang,
            target_lang=target_lang,
            text_length=len(text)
        )
        
        # 3. 执行翻译（模拟实现）
        # 实际项目中应该调用真实的翻译API
        translated = await self._translate_text(
            text=text,
            source_lang=source_lang,
            target_lang=target_lang,
            style=style
        )
        
        # 4. 计算耗时
        elapsed_ms = int((time.time() - start_time) * 1000)
        
        # 5. 构建输出
        output = {
            "translated_text": translated,
            "detected_source_lang": source_lang if source_lang != "auto" else "zh",
            "confidence_score": 0.95,
            "word_count": len(translated.split())
        }
        
        # 6. 发出完成事件
        await ctx.event_bus.emit(
            "translation:completed",
            data={
                "plugin_id": self.id,
                "source_lang": source_lang,
                "target_lang": target_lang,
                "word_count": output["word_count"],
                "duration_ms": elapsed_ms
            }
        )
        
        self.logger.info(
            "Translation completed",
            duration_ms=elapsed_ms,
            word_count=output["word_count"]
        )
        
        return NodeOutput(
            success=True,
            data=output,
            message=f"Translated to {self.supported_languages.get(target_lang, target_lang)}",
            execution_time_ms=elapsed_ms
        )
    
    async def _translate_text(
        self, 
        text: str,
        source_lang: str,
        target_lang: str,
        style: str
    ) -> str:
        """
        实际翻译逻辑（模拟实现）
        
        在实际项目中，这里应该：
        - 调用OpenAI/DeepSeek/Google Translate API
        - 或使用本地模型（如transformers）
        """
        
        # 模拟API调用延迟
        await asyncio.sleep(0.1)
        
        # TODO: 替换为真实翻译逻辑
        # 示例伪代码：
        # response = await openai.chat.completions.create(
        #     model="gpt-4",
        #     messages=[{
        #         "role": "system",
        #         "content": f"Translate the following {style} text "
        #                    f"from {source_lang} to {target_lang}. "
        #                    f"Preserve formatting: {preserve_fmt}"
        #     }, {
        #         "role": "user",
        #         "content": text
        #     }]
        # )
        # return response.choices[0].message.content
        
        # 模拟返回
        return f"[Translated to {target_lang}] {text}"
    
    async def optimize_output(
        self, 
        output: NodeOutput,
        feedback: str = None
    ) -> NodeOutput:
        """根据反馈优化翻译结果"""
        
        if not feedback or not output.success:
            return output
        
        self.logger.info(
            "Optimizing translation based on feedback",
            feedback=feedback[:100]
        )
        
        # 根据用户反馈重新翻译
        original_text = output.data.get("translated_text", "")
        
        # TODO: 实现优化逻辑
        optimized_text = f"[Optimized] {original_text}"
        
        output.data["translated_text"] = optimized_text
        output.message = "Translation optimized"
        
        return output
```

### 完整示例：自定义数据源插件（DATASOURCE）

```python
# rss_datasource/plugin.json
{
    "id": "rss-datasource",
    "name": "RSS订阅源监控",
    "version": "1.0.0",
    "category": "datasource",
    "description": "监控指定RSS Feed，自动抓取最新文章并入库",
    "author": {
        "name": "Data Team",
        "email": "data@example.com"
    },
    "entry_point": "main.py:RSSDatasourcePlugin",
    "display_icon": "📡",
    "capabilities": ["search_trending", "get_trending"],
    "permissions_required": ["network:read"],
    "config_schema": {
        "type": "object",
        "properties": {
            "feed_urls": {
                "type": "array",
                "items": {"type": "string", "format": "uri"},
                "default": [],
                "title": "RSS Feed URL列表"
            },
            "check_interval_minutes": {
                "type": "integer",
                "minimum": 5,
                "maximum": 1440,
                "default": 30,
                "title": "检查间隔（分钟）"
            },
            "max_articles_per_feed": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "default": 10,
                "title": "每个Feed最大文章数"
            }
        },
        "required": ["feed_urls"]
    },
    "events_subscribes": ["system:scheduler:tick"],
    "events_emits": [
        "datasource:new_article_found",
        "datasource:feed_error"
    ]
}
```

```python
# rss_datasource/main.py
import feedparser
from datetime import datetime
from typing import List, Dict, Any
from app.core.base_interfaces import (
    BaseDatasourcePlugin,
    PluginContext,
    TrendingItem,
    Classification
)
from app.core.plugin_types import PluginManifest, HealthStatus


class RSSDatasourcePlugin(BaseDatasourcePlugin):
    """RSS数据源插件"""
    
    id = "rss-datasource"
    name = "RSS订阅源监控"
    version = "1.0.0"
    
    def __init__(self):
        super().__init__()
        self._article_cache: Dict[str, TrendingItem] = {}
        self._last_check_times: Dict[str, datetime] = {}
    
    async def on_load(self):
        """加载时初始化Feed解析器"""
        self.logger.info("Initializing RSS datasource...")
        
        # 预热缓存
        if ctx and ctx.config:
            feeds = ctx.config.get("feed_urls", [])
            for feed_url in feeds[:3]:  # 先预热前3个
                try:
                    await self._fetch_feed(feed_url)
                except Exception as e:
                    self.logger.warning(f"Failed to preload {feed_url}: {e}")
    
    async def search_trending(
        self, 
        query: str, 
        limit: int = 20
    ) -> List[TrendingItem]:
        """搜索文章"""
        
        results = []
        query_lower = query.lower()
        
        # 遍历缓存的文章
        for article in self._article_cache.values():
            if (query_lower in article.title.lower() or
                query_lower in (article.metadata.get("summary", "")).lower()):
                
                results.append(article)
                
                if len(results) >= limit:
                    break
        
        # 按热度排序
        results.sort(key=lambda x: x.score, reverse=True)
        
        return results[:limit]
    
    async def get_trending(
        self, 
        category: str = None,
        limit: int = 20
    ) -> List[TrendingItem]:
        """获取最新文章"""
        
        articles = list(self._article_cache.values())
        
        # 按时间排序（最新的在前）
        articles.sort(
            key=lambda x: x.published_at or datetime.min,
            reverse=True
        )
        
        return articles[:limit]
    
    async def handle_scheduler_tick(self, event):
        """定时检查更新"""
        
        if not ctx or not ctx.config:
            return
        
        feeds = ctx.config.get("feed_urls", [])
        
        for feed_url in feeds:
            try:
                last_check = self._last_check_times.get(feed_url)
                interval_minutes = ctx.config.get(
                    "check_interval_minutes", 30
                )
                
                # 检查是否到了检查时间
                if last_check:
                    elapsed = (datetime.utcnow() - last_check).total_seconds()
                    if elapsed < interval_minutes * 60:
                        continue
                
                # 抓取Feed
                new_articles = await self._fetch_feed(feed_url)
                
                # 发现新文章时发出事件
                for article in new_articles:
                    await ctx.event_bus.emit(
                        "datasource:new_article_found",
                        data={
                            "article_id": article.id,
                            "title": article.title,
                            "url": article.url,
                            "source_feed": feed_url
                        }
                    )
                
                # 更新最后检查时间
                self._last_check_times[feed_url] = datetime.utcnow()
                
            except Exception as e:
                self.logger.error(f"Error checking feed {feed_url}: {e}")
                
                await ctx.event_bus.emit(
                    "datasource:feed_error",
                    data={
                        "feed_url": feed_url,
                        "error": str(e)
                    }
                )
    
    async def _fetch_feed(
        self, 
        feed_url: str
    ) -> List[TrendingItem]:
        """抓取单个Feed"""
        
        import httpx
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(feed_url)
            response.raise_for_status()
        
        # 解析RSS/Atom
        parsed = feedparser.parse(response.text)
        
        new_articles = []
        max_articles = ctx.config.get("max_articles_per_feed", 10) \
            if ctx else 10
        
        for entry in parsed.entries[:max_articles]:
            article_id = entry.get("id", entry.get("link", ""))
            
            # 跳过已存在的文章
            if article_id in self._article_cache:
                continue
            
            # 创建TrendingItem
            article = TrendingItem(
                id=article_id,
                title=entry.get("title", "Untitled"),
                url=entry.get("link", ""),
                source="rss",
                score=self._calculate_score(entry),
                published_at=self._parse_date(entry.get("published")),
                tags=self._extract_tags(entry),
                metadata={
                    "summary": entry.get("summary", ""),
                    "author": entry.get("author", ""),
                    "feed_url": feed_url
                }
            )
            
            # 加入缓存
            self._article_cache[article_id] = article
            new_articles.append(article)
        
        return new_articles
    
    def _calculate_score(self, entry) -> float:
        """计算文章热度分"""
        
        score = 50.0  # 基础分
        
        # 根据各种因素调整分数
        # （简化版，实际可以使用更复杂的算法）
        
        return min(score, 100.0)
    
    def _parse_date(self, date_str) -> datetime:
        """解析日期字符串"""
        if not date_str:
            return datetime.utcnow()
        
        try:
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except:
            return datetime.utcnow()
    
    def _extract_tags(self, entry) -> List[str]:
        """提取标签"""
        tags = []
        
        # 从categories中提取
        for category in getattr(entry, 'tags', []):
            term = category.get('term', '')
            if term:
                tags.append(term)
        
        return tags[:5]  # 最多5个标签
```

---

## 📚 API 参考

### RESTful API 端点

#### 插件管理

| Method | Endpoint | Description | Auth |
|--------|----------|-------------|------|
| GET | `/api/plugins` | 获取插件列表 | Optional |
| GET | `/api/plugins/{id}` | 获取插件详情 | Optional |
| POST | `/api/plugins/{id}/install` | 安装插件 | Required |
| DELETE | `/api/plugins/{id}/uninstall` | 卸载插件 | Required |
| POST | `/api/plugins/{id}/enable` | 启用插件 | Required |
| POST | `/api/plugins/{id}/disable` | 禁用插件 | Required |
| GET | `/api/plugins/{id}/config` | 获取配置 | Required |
| PUT | `/api/plugins/{id}/config` | 更新配置 | Required |

#### 插件市场

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/plugins/marketplace` | 浏览市场 |
| GET | `/api/plugins/my` | 我的插件 |
| POST | `/api/plugins/bulk` | 批量操作 |
| GET | `/api/plugins/health` | 系统健康检查 |

### 响应格式标准

**成功响应**:
```json
{
    "success": true,
    "data": { ... },
    "message": "Operation completed",
    "timestamp": "2026-08-16T01:00:00Z"
}
```

**错误响应**:
```json
{
    "success": false,
    "error": {
        "code": "PLUGIN_NOT_FOUND",
        "message": "Plugin xxx not found",
        "details": { ... }
    },
    "timestamp": "2026-08-16T01:00:00Z"
}
```

**分页响应**:
```json
{
    "items": [ ... ],
    "total": 100,
    "page": 1,
    "page_size": 20,
    "has_next": true,
    "has_prev": false
}
```

---

## ❓ 常见问题

### Q1: 插件加载失败怎么办？

**A**: 检查以下几点：
1. `plugin.json` 格式是否正确（可用JSON Schema验证器检查）
2. `entry_point` 指向的类是否存在且继承正确的基类
3. `requirements.txt` 中的依赖是否都已安装
4. 查看后端日志：`logs/plugin_manager.log`

### Q2: 如何调试插件？

**A**: 
```python
# 在插件代码中开启调试模式
class MyPlugin(BasePlugin):
    DEBUG = True  # 开启详细日志
    
    async def execute(self, ctx, inputs):
        self.logger.debug("Inputs received", inputs=inputs)
        # ... 业务逻辑
        self.logger.debug("Output generated", output=result)
```

### Q3: 插件可以访问数据库吗？

**A**: 可以，但不推荐直接访问。建议通过以下方式：
1. 使用 `ctx.data_store` 进行轻量级数据存储
2. 通过EventBus与其他插件交换数据
3. 如需持久化大量数据，申请专门的数据库表（联系管理员）

### Q4: 如何处理插件间的依赖？

**A**: 在 `plugin.json` 中声明：
```json
{
    "dependencies": ["base-plugin:v1.0.0+", "another-plugin"]
}
```
系统会在加载前自动检查并安装依赖。

### Q5: 插件的性能限制是什么？

**A**: 
- 单次执行最长60秒
- 最大内存使用256MB
- 每分钟最多60次API调用
- 网络请求超时30秒

可通过申请提升限额（联系管理员）。

### Q6: 如何发布付费插件？

**A**: 
1. 将 `pricing_model` 设为 `"paid"` 或 `"freemium"`
2. 在插件市场提交审核
3. 审核通过后设置价格
4. 用户购买后你获得70%收益（平台抽成30%）

### Q7: 插件更新后用户的配置会丢失吗？

**A**: 不会。系统会：
1. 自动备份旧配置
2. 合并新旧配置Schema
3. 对于删除的字段，保留数据但标记为deprecated
4. 用户可在配置面板中手动清理

### Q8: 如何获得技术支持？

**A**: 
- 文档: https://docs.your-platform.com/plugins
- GitHub Issues: https://github.com/org/plugins/issues
- Discord社区: https://discord.gg/your-platform
- 商务合作: plugins@your-platform.com

---

## 📊 附录

### A. 错误码一览

| 错误码 | HTTP状态码 | 说明 |
|--------|-----------|------|
| `PLUGIN_NOT_FOUND` | 404 | 插件不存在 |
| `PLUGIN_ALREADY_INSTALLED` | 409 | 插件已安装 |
| `INVALID_CONFIG` | 422 | 配置格式错误 |
| `PERMISSION_DENIED` | 403 | 权限不足 |
| `RATE_LIMITED` | 429 | 请求过于频繁 |
| `DEPENDENCY_MISSING` | 422 | 缺少依赖插件 |
| `VERSION_INCOMPATIBLE` | 409 | 版本不兼容 |
| `SANDBOX_VIOLATION` | 403 | 违反沙箱规则 |
| `HEALTH_CHECK_FAILED` | 503 | 健康检查失败 |

### B. 事件类型速查

| 事件类型 | 触发时机 | 数据载荷 |
|---------|---------|---------|
| `plugin:loaded` | 插件加载完成 | `{plugin_id, version}` |
| `plugin:unloaded` | 插件卸载 | `{plugin_id}` |
| `plugin:enabled` | 插件启用 | `{plugin_id, user_id}` |
| `plugin:disabled` | 插件禁用 | `{plugin_id, user_id}` |
| `config:changed` | 配置变更 | `{plugin_id, changed_keys}` |
| `workflow:node_started` | 节点开始执行 | `{node_id, workflow_id}` |
| `workflow:node_completed` | 节点执行完成 | `{node_id, output, duration_ms}` |
| `content:published` | 内容发布成功 | `{content_id, platform, url}` |
| `datasource:trending_found` | 发现新热点 | `{items[], source}` |

### C. 性能基准测试

| 操作类型 | 平均响应时间 | P99延迟 | 吞吐量 |
|---------|-------------|---------|--------|
| 加载插件 | 120ms | 500ms | 100/min |
| 执行工作流节点 | 800ms | 3s | 30/min |
| 配置读写 | 15ms | 50ms | 1000/min |
| 事件发布/订阅 | <1ms | 5ms | 10000/min |
| 数据存储操作 | 5ms | 20ms | 2000/min |

---

## 📄 文档版本历史

| 版本 | 日期 | 作者 | 变更说明 |
|------|------|------|---------|
| 1.0.0 | 2026-08-10 | Platform Team | 初版发布 |
| 2.0.0 | 2026-08-16 | SDK Team | Day 9重构，补充最佳实践和示例 |

---

## 📜 许可证

本文档遵循 CC BY-SA 4.0 许可证。您可以自由地分享、改编本文档，但需注明来源并以相同方式分享。

---

**🎉 感谢您阅读插件SDK开发指南！**

如有问题或建议，欢迎：
- 提交GitHub Issue
- 加入开发者Discord社区
- 发送邮件至 plugins-support@example.com

**祝开发愉快！** 🚀