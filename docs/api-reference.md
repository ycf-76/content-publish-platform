# API 参考文档

> **Creator Platform SDK 完整API文档**

## 目录

- [核心类型](#核心类型)
  - [PluginContext](#plugincontext)
  - [NodeOutput](#nodeoutput)
  - [PublishResult](#publishresult)
  - [TrendingContent](#trendingcontent)
  - [DataSourceItem](#datasourceitem)

- [插件基类](#插件基类)
  - [BasePlugin](#baseplugin)
  - [BaseWorkflowNodePlugin](#baseworkflownodeplugin)
  - [BaseDatasourcePlugin](#basedatasourceplugin)
  - [BasePlatformPlugin](#baseplatformplugin)
  - [BaseIntegrationPlugin](#baseintegrationplugin)

- [事件系统](#事件系统)
  - [EventBus](#eventbus)
  - [Event](#event)
  - [Subscription](#subscription)

- [工具函数](#工具函数)
- [枚举类型](#枚举类型)

---

## 核心类型

### PluginContext

**执行上下文对象，包含插件运行时所需的所有信息**

```python
@dataclass
class PluginContext:
    user_id: str = "anonymous"
    config: Optional[Dict[str, Any]] = None
    logger: Optional[logging.Logger] = None
    event_bus: Optional[EventBus] = None
    storage: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
```

#### 属性说明

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_id` | `str` | `"anonymous"` | 当前用户ID |
| `config` | `dict` | `{}` | 插件配置（来自plugin.json的config_schema） |
| `logger` | `Logger` | `None` | 日志记录器（setup后自动设置） |
| `event_bus` | `EventBus` | `None` | 事件总线实例 |
| `storage` | `dict` | `{}` | 临时存储（跨节点传递数据） |
| `metadata` | `dict` | `{}` | 元数据（如工作流ID等） |

#### 使用示例

```python
async def execute(self, ctx: PluginContext, inputs: dict) -> NodeOutput:
    # 获取配置
    api_key = ctx.config.get("api_key")

    # 记录日志
    if ctx.logger:
        ctx.logger.info("Processing request...")

    # 发送事件
    if ctx.event_bus:
        await ctx.event_bus.emit("my:event", {"data": "value"})

    # 使用存储
    ctx.storage["temp_data"] = some_value

    return NodeOutput(success=True, data={})
```

---

### NodeOutput

**标准化的节点执行结果**

```python
@dataclass
class NodeOutput:
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    execution_time_ms: int = 0
    error: Optional[str] = None
```

#### 属性说明

| 属性 | 类型 | 必填 | 说明 |
|------|------|:----:|------|
| `success` | `bool` | ✅ | 是否成功执行 |
| `data` | `dict` | ❌ | 输出数据（传递给下游节点） |
| `message` | `str` | ❌ | 执行消息（显示在日志中） |
| `execution_time_ms` | `int` | ❌ | 执行耗时（毫秒） |
| `error` | `str` | ❌ | 错误信息（失败时填写） |

#### 方法

##### `to_dict() -> dict`
转换为字典格式：

```python
output = NodeOutput(success=True, data={"key": "value"})
d = output.to_dict()
# {'success': True, 'data': {'key': 'value'}, 'message': '', ...}
```

#### 工厂函数

```python
from creator_platform_sdk import create_success_output, create_error_output

# 创建成功结果
output = create_success_output({"result": 42}, "Done!")

# 创建错误结果
output = create_error_output("Something went wrong")
```

---

### PublishResult

**平台发布结果（用于BasePlatformPlugin）**

```python
@dataclass
class PublishResult:
    success: bool
    post_id: Optional[str] = None
    post_url: Optional[str] = None
    platform: Optional[str] = None
    published_at: Optional[datetime] = None
    stats: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
```

#### 属性说明

| 属性 | 类型 | 说明 |
|------|------|------|
| `success` | `bool` | 是否发布成功 |
| `post_id` | `str` | 发布后的内容ID |
| `post_url` | `str` | 内容链接 |
| `platform` | `str` | 平台名称 |
| `published_at` | `datetime` | 发布时间 |
| `stats` | `dict` | 统计信息（浏览量、点赞等） |
| `error_message` | `str` | 失败原因 |

#### 使用示例

```python
async def publish(self, ctx, content, credentials):
    # ... 发布逻辑 ...

    return PublishResult(
        success=True,
        post_id="post_12345",
        post_url="https://platform.com/post/12345",
        platform="xiaohongshu",
        published_at=datetime.utcnow(),
        stats={"views": 0, "likes": 0}
    )
```

---

### TrendingContent

**热门内容项（用于BaseDatasourcePlugin）**

```python
@dataclass
class TrendingContent:
    content_id: str
    title: str
    description: str = ""
    url: Optional[str] = None
    image_url: Optional[str] = None
    author: Optional[str] = None
    published_at: Optional[datetime] = None
    metrics: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    raw_data: Optional[Dict[str, Any]] = None
```

---

### DataSourceItem

**数据源条目（用于BaseDatasourcePlugin）**

```python
@dataclass
class DataSourceItem:
    item_id: str
    item_type: str  # article, video, image, etc.
    title: str
    content: str
    source: Optional[str] = None
    url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    fetched_at: Optional[datetime] = None
```

---

## 插件基类

### BasePlugin

**所有插件的基类，提供通用的生命周期管理**

```python
class BasePlugin(ABC):
    # 抽象属性（必须实现）
    @property
    @abstractmethod
    def plugin_id(self) -> str: ...

    @property
    @abstractmethod
    def plugin_name(self) -> str: ...

    # 可选属性
    version: str = "0.1.0"
    description: str = ""
```

#### 生命周期方法

##### `async setup(ctx: PluginContext) -> None`
初始化插件（在execute前调用一次）

```python
async def setup(self, ctx: PluginContext) -> None:
    self._ctx = ctx
    self._logger = ctx.logger
    
    # 加载配置
    self.api_key = ctx.config.get("api_key")
    
    # 建立连接
    self.client = aiohttp.ClientSession()
```

##### `async teardown() -> None`
清理资源（在插件卸载时调用）

```python
async def teardown(self) -> None:
    if hasattr(self, 'client'):
        await self.client.close()
```

##### `async execute(ctx: PluginContext, inputs: dict) -> NodeOutput`
**核心方法：执行插件逻辑**

```python
async def execute(
    self,
    ctx: PluginContext,
    inputs: Dict[str, Any]
) -> NodeOutput:
    # 你的逻辑
    return NodeOutput(success=True, data={})
```

##### `async validate_inputs(inputs: dict) -> Tuple[bool, str]`
验证输入参数（在execute前自动调用）

```python
async def validate_inputs(self, inputs: dict) -> tuple[bool, str]:
    if "required_field" not in inputs:
        return False, "Missing required field: required_field"
    
    return True, "OK"
```

##### `async health_check() -> Tuple[bool, str]`
健康检查

```python
async def health_check(self) -> tuple[bool, str]:
    is_ok = check_connection()
    return (is_ok, "Connected" if is_ok else "Disconnected")
```

##### `get_manifest() -> Dict[str, Any]`
获取插件清单信息

```python
def get_manifest(self) -> dict:
    return {
        "id": self.plugin_id,
        "name": self.plugin_name,
        "version": self.version,
        ...
    }
```

---

### BaseWorkflowNodePlugin

**工作流节点插件基类**

```python
class BaseWorkflowNodePlugin(BasePlugin):
    category: str = "workflow_node"
```

#### 额外方法

##### `async on_node_start(node_id: str)`
节点开始时回调

##### `async on_node_complete(node_id: str, result: NodeOutput)`
节点完成时回调

#### 适用场景

- AI文案生成
- 文本翻译
- 情感分析
- 数据转换
- 自定义业务逻辑

---

### BaseDatasourcePlugin

**数据源插件基类**

```python
class BaseDatasourcePlugin(BasePlugin):
    category: str = "datasource"
```

#### 核心方法

##### `async fetch_data(ctx: PluginContext, config: DataSourceConfig) -> List[DataSourceItem]`
获取数据列表

```python
async def fetch_data(
    self,
    ctx: PluginContext,
    config: DataSourceConfig
) -> List[DataSourceItem]:
    # 解析RSS/API/数据库...
    items = []
    for entry in entries:
        items.append(DataSourceItem(
            item_id=entry.id,
            item_type="article",
            title=entry.title,
            content=entry.content,
            source=config.endpoint
        ))
    return items
```

##### `async fetch_trending(ctx, category=None, limit=20) -> List[TrendingContent]`
获取热门内容

##### `async test_connection(ctx, config) -> Tuple[bool, str]`
测试连接

#### 适用场景

- RSS订阅监控
- 社交媒体抓取
- API数据获取
- 数据库查询
- 文件监听

---

### BasePlatformPlugin

**平台发布器插件基类**

```python
class BasePlatformPlugin(BasePlugin):
    category: str = "platform"
```

#### 核心方法

##### `async publish(ctx, content, credentials) -> PublishResult`
发布内容

```python
async def publish(
    self,
    ctx: PluginContext,
    content: Dict[str, Any],
    credentials: Dict[str, Any]
) -> PublishResult:
    # 调用平台API...
    return PublishResult(
        success=True,
        post_id=post_id,
        post_url=url,
        platform=self.plugin_id
    )
```

##### `async authenticate(ctx, credentials) -> Tuple[bool, str]`
认证用户

##### `async get_publish_history(ctx, limit=20, offset=0) -> List[PublishResult]`
获取发布历史

##### `async delete_post(ctx, post_id, credentials) -> bool`
删除内容

#### 适用场景

- 小红书发布
- 微博/抖音/B站
- WordPress博客
- 邮件发送
- 其他第三方平台

---

### BaseIntegrationPlugin

**集成工具插件基类**

```python
class BaseIntegrationPlugin(BasePlugin):
    category: str = "integration"
```

#### 核心方法

##### `async send_notification(ctx, notification) -> NodeOutput`
发送通知（示例方法）

##### `async integrate(ctx, action, params) -> NodeOutput`
通用集成方法

#### 适用场景

- 多渠道通知推送（邮件/微信/钉钉/Slack）
- 云存储集成（OSS/S3）
- CI/CD工具对接
- 第三方服务API封装

---

## 事件系统

### EventBus

**事件总线，用于插件间解耦通信**

```python
bus = EventBus()
```

#### 核心方法

##### `async subscribe(event_pattern, handler, **kwargs) -> str`
订阅事件

**参数：**
- `event_pattern`: 事件模式（支持通配符 `*`）
- `handler`: 处理函数（async或sync）
- `subscriber_id`: 订阅者ID（可选）
- `priority`: 优先级（数字越大越先执行）
- `once`: 是否只触发一次（默认False）
- `filter_func`: 过滤函数（可选）

**返回值：** subscription_id（用于取消订阅）

**示例：**

```python
# 基础订阅
await bus.subscribe("notification:sent", my_handler)

# 通配符订阅
await bus.subscribe("notification:*", handler_all_notifications)

# 带过滤器
def only_high_priority(event):
    return event.data.get("priority") == "urgent"

await bus.subscribe("alert:*", urgent_handler, filter_func=only_high_priority)

# 一次性订阅
await bus.subscribe("one-time-event", handler, once=True)
```

##### `async emit(event_type, data, **kwargs) -> int`
发布事件

**参数：**
- `event_type`: 事件类型
- `data`: 事件数据（字典）
- `source`: 来源插件ID
- `priority`: 优先级(1-5)

**返回值：** 处理此事件的处理器数量

**示例：**

```python
count = await bus.emit(
    "notification:sent",
    {
        "title": "Hello!",
        "channel": "email"
    },
    source="email-plugin",
    priority=4
)
print(f"Emitted to {count} handlers")
```

##### `get_event_history(event_type=None, limit=50) -> List[Event]`
获取事件历史

##### `add_middleware(middleware)`
添加中间件

```python
def logging_middleware(event):
    print(f"[Middleware] {event.event_type}")
    return True  # 返回False可阻止事件分发

bus.add_middleware(logging_middleware)
```

##### `enable()` / `disable()`
启用/禁用事件总线

##### `clear_all()`
清除所有订阅和历史（测试用）

#### 属性

| 属性 | 类型 | 说明 |
|------|------|------|
| `is_enabled` | `bool` | 是否启用 |
| `total_subscriptions` | `int` | 总订阅数 |
| `total_events_emitted` | `int` | 已发出事件总数 |

---

### Event

**事件对象**

```python
@dataclass
class Event:
    event_type: str           # 事件类型
    data: Dict[str, Any]      # 事件数据
    source: Optional[str]     # 来源
    timestamp: datetime       # 时间戳
    event_id: str             # 唯一标识符
    priority: int             # 优先级 (1-5)
    metadata: Dict            # 元数据
```

---

## 工具函数

### create_success_output(data, message="")
创建成功结果

```python
from creator_platform_sdk import create_success_output

output = create_success_output({"value": 42}, "Success!")
```

### create_error_output(error, data=None)
创建错误结果

```python
from creator_platform_sdk import create_error_output

output = create_error_output("File not found")
```

### create_plugin_context(user_id, **kwargs)
创建测试用上下文

```python
from creator_platform_sdk import create_plugin_context

ctx = create_plugin_context(user_id="test", config={"key": "value"})
```

---

## 枚举类型

### PluginCategory

```python
class PluginCategory(Enum):
    WORKFLOW_NODE = "workflow_node"      # 工作流节点
    DATASOURCE = "datasource"            # 数据源
    PLATFORM = "platform"                # 发布平台
    INTEGRATION = "integration"          # 集成工具
    UI_COMPONENT = "ui_component"        # UI组件
```

### Priority

```python
class Priority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4
```

### NotificationLevel

```python
class NotificationLevel(Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
```

---

## 最佳实践

### 1. 错误处理

```python
async def execute(self, ctx, inputs):
    try:
        result = await risky_operation()
        return create_success_output(result)
    except SpecificError as e:
        return create_error_output(f"Specific error: {e}")
    except Exception as e:
        ctx.logger.exception("Unexpected error")
        return create_error_output("Internal error")
```

### 2. 日志规范

```python
async def execute(self, ctx, inputs):
    ctx.logger.debug(f"Starting with inputs: {inputs}")
    # ... 逻辑 ...
    ctx.logger.info(f"Completed successfully in {elapsed}ms")
```

### 3. 配置使用

```python
async def setup(self, ctx):
    # 从config读取配置
    self.timeout = ctx.config.get("timeout", 30)
    self.retry_count = ctx.config.get("retries", 3)
    
    # 验证必要配置
    if not ctx.config.get("api_key"):
        raise ValueError("Missing required config: api_key")
```

### 4. 事件命名规范

```
{plugin_id}:{action}:{status}

例如：
- notification:sent
- notification:failed
- xiaohongshu:publish:success
- rss-monitor:new-items-found
```

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-08-16 | 初始版本 |

---

**如有问题或建议，欢迎提交Issue！** 🚀

*最后更新: 2026-08-16*