# 多智能体小红书发布平台 — 插件 SDK 速查卡

> 将此文档完整粘贴给 AI 模型，模型即可按规范生成可导入的插件。

---

## 一、插件包结构

```
my-plugin.zip
├── plugin.json       ← 必须存在（插件身份证）
├── __init__.py       ← 可选
└── my_plugin.py      ← 后端入口代码
```

---

## 二、plugin.json 完整规范

```json
{
  "id": "my-plugin",
  "name": "我的插件",
  "version": "1.0.0",
  "description": "插件功能描述",
  "category": "workflow_node",

  "author": { "name": "开发者", "email": "dev@example.com" },
  "entry_point": "my_plugin.py:MyPluginClass",
  "display_icon": "🎯",
  "display_color": "#3B82F6",
  "pricing_model": "free",

  "tags": ["tag1", "tag2"],
  "capabilities": ["execute"],
  "permissions_required": ["network:http"],

  "config_schema": {
    "type": "object",
    "properties": {
      "param1": { "type": "string", "description": "参数说明" },
      "param2": { "type": "integer", "default": 3, "minimum": 1, "maximum": 10 }
    },
    "required": ["param1"]
  },

  "dependencies": [],
  "min_platform_version": "1.0.0",
  "is_builtin": false,
  "is_enabled_by_default": false,

  "events_subscribes": ["workflow:node_completed:*"],
  "events_emits": ["my-plugin:done"],

  "screenshots": []
}
```

**必填字段**：`id`、`name`、`version`、`category`

**字段规则**：
- `id`：小写字母开头，仅 `a-z 0-9 - _`，如 `my-cool-plugin`
- `category`：必须是以下之一 ↓

| category 值 | 含义 | 对应基类 |
|-------------|------|----------|
| `platform` | 平台发布器 | `BasePlatformPlugin` |
| `datasource` | 数据源 | `BaseDatasourcePlugin` |
| `workflow_node` | 工作流节点 | `BaseWorkflowNodePlugin` |
| `ui_theme` | UI主题/交互 | `BasePlugin`（或简单类） |
| `analytics` | 数据分析 | `BasePlugin` |
| `utility` | 工具类 | `BasePlugin` |

- `entry_point`：格式 `文件名:类名`，如 `my_plugin.py:MyPlugin`
- `config_schema`：JSON Schema 格式，前端据此渲染配置表单
- `screenshots`：图片URL数组，显示在插件详情页

---

## 三、Python 基类接口（完整签名）

### 3.1 BasePlugin（所有插件的根基类）

```python
from app.core.base_interfaces import BasePlugin, PluginContext

class BasePlugin:
    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """插件唯一标识符，匹配 ^[a-z][a-z0-9_-]*$"""

    @property
    @abstractmethod
    def plugin_name(self) -> str:
        """插件显示名称"""

    async def setup(self, ctx: PluginContext) -> None:
        """初始化时调用，ctx 包含 config/logger/user_id/api"""

    async def teardown(self) -> None:
        """卸载时调用，释放资源"""

    async def health_check(self) -> tuple[bool, str]:
        """健康检查，返回 (is_healthy, message)"""
```

### 3.2 BasePlatformPlugin（平台发布器）

```python
from app.core.base_interfaces import BasePlatformPlugin, PluginContext
from app.core.plugin_types import PublishResult

class BasePlatformPlugin(BasePlugin):
    @abstractmethod
    async def authenticate(self, credentials: Dict[str, Any], ctx: PluginContext) -> bool:
        """平台认证，credentials 为 cookie/token 等"""

    @abstractmethod
    async def publish(self, content: Dict[str, Any], config: Dict[str, Any], ctx: PluginContext) -> PublishResult:
        """发布内容，content 含 title/content/images 等，返回 PublishResult"""

    async def get_analytics(self, content_id: str, ctx: PluginContext) -> Dict[str, Any]:
        """可选：获取内容数据分析"""

    async def delete_content(self, content_id: str, ctx: PluginContext) -> bool:
        """可选：删除已发布内容"""
```

### 3.3 BaseDatasourcePlugin（数据源）

```python
from app.core.base_interfaces import BaseDatasourcePlugin, PluginContext
from app.core.plugin_types import TrendingContent

class BaseDatasourcePlugin(BasePlugin):
    @abstractmethod
    async def search_trending(self, keyword: str, limit: int = 20, ctx: Optional[PluginContext] = None) -> List[TrendingContent]:
        """搜索趋势内容"""

    @abstractmethod
    async def get_trending(self, limit: int = 20, ctx: Optional[PluginContext] = None) -> List[TrendingContent]:
        """获取当前热门/推荐内容"""
```

### 3.4 BaseWorkflowNodePlugin（工作流节点）

```python
from app.core.base_interfaces import BaseWorkflowNodePlugin, PluginContext

class BaseWorkflowNodePlugin(BasePlugin):
    @property
    @abstractmethod
    def node_type(self) -> str:
        """节点类型标识符（唯一）"""

    @property
    @abstractmethod
    def display_name(self) -> str:
        """节点显示名称"""

    @property
    def description(self) -> str: return ""

    @property
    def icon(self) -> str: return "📦"

    @property
    def input_schema(self) -> Dict[str, Any]:
        """输入参数 JSON Schema，前端据此渲染输入表单"""
        return {"type": "object", "properties": {}, "required": []}

    @property
    def output_schema(self) -> Dict[str, Any]:
        """输出参数 JSON Schema，下游节点据此验证"""
        return {"type": "object", "properties": {}, "required": []}

    @abstractmethod
    async def execute(self, inputs: Dict[str, Any], node_config: Dict[str, Any], ctx: PluginContext) -> Dict[str, Any]:
        """执行节点逻辑，inputs 为上游输出，node_config 为本节点配置，返回输出数据"""

    async def before_execute(self, inputs, node_config) -> None: pass
    async def after_execute(self, result, execution_time_ms) -> None: pass
```

---

## 四、核心数据类型

```python
@dataclass
class PluginContext:
    plugin_id: str
    plugin_dir: str
    config: Dict[str, Any]
    logger: logging.Logger
    user_id: Optional[str] = None
    api: Any = None  # API客户端
    def get_config(self, key: str, default: Any = None) -> Any: ...

@dataclass
class PublishResult:
    success: bool
    platform_url: str = ""
    content_id: str = ""
    error: Optional[str] = None
    @classmethod
    def ok(cls, platform_url="", content_id="") -> "PublishResult": ...
    @classmethod
    def fail(cls, error: str) -> "PublishResult": ...

@dataclass
class TrendingContent:
    platform: str
    content_id: str
    title: str
    summary: str
    author: str = ""
    url: str = ""
    likes: int = 0
    comments: int = 0
    shares: int = 0
    raw: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ExecutionResult:
    success: bool
    data: Any = None
    error: Optional[str] = None
    execution_time_ms: int = 0
```

---

## 五、权限声明枚举

```python
class PluginPermission(str, Enum):
    NETWORK_HTTP = "network:http"
    NETWORK_HTTPS = "network:https"
    FILESYSTEM_READ = "filesystem:read"
    FILESYSTEM_WRITE = "filesystem:write"
    SUBPROCESS_SPAWN = "subprocess:spawn"
    ENV_READ = "env:read"
    ENV_WRITE = "env:write"
```

常用权限简写（在 permissions_required 中使用）：
- `"network:http"` — HTTP 请求
- `"network:https"` — HTTPS 请求
- `"llm:use"` — 调用 LLM
- `"xhs:publish"` — 小红书发布
- `"xhs:read"` — 小红书读取
- `"filesystem:read"` — 读文件
- `"filesystem:write"` — 写文件

---

## 六、完整示例

### 示例 A：工作流节点插件（最常用）

**plugin.json：**
```json
{
  "id": "text-transformer",
  "name": "文本转换器",
  "version": "1.0.0",
  "description": "对文本执行各种转换操作（大小写、反转、去重等）",
  "category": "workflow_node",
  "author": {"name": "AI Generated"},
  "entry_point": "text_transformer.py:TextTransformerPlugin",
  "display_icon": "🔄",
  "capabilities": ["execute", "validate_inputs"],
  "permissions_required": [],
  "config_schema": {
    "type": "object",
    "properties": {
      "mode": {
        "type": "string",
        "enum": ["uppercase", "lowercase", "reverse", "deduplicate"],
        "default": "uppercase",
        "description": "转换模式"
      }
    }
  },
  "is_builtin": false,
  "is_enabled_by_default": false
}
```

**text_transformer.py：**
```python
from app.core.base_interfaces import BaseWorkflowNodePlugin, PluginContext
from typing import Any, Dict

class TextTransformerPlugin(BaseWorkflowNodePlugin):

    @property
    def plugin_id(self) -> str:
        return "text-transformer"

    @property
    def plugin_name(self) -> str:
        return "文本转换器"

    @property
    def node_type(self) -> str:
        return "text_transform"

    @property
    def display_name(self) -> str:
        return "文本转换"

    @property
    def input_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "输入文本"}
            },
            "required": ["text"]
        }

    @property
    def output_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "result": {"type": "string", "description": "转换结果"}
            }
        }

    async def execute(
        self,
        inputs: Dict[str, Any],
        node_config: Dict[str, Any],
        ctx: PluginContext
    ) -> Dict[str, Any]:
        text = inputs.get("text", "")
        mode = node_config.get("mode", "uppercase")

        if mode == "uppercase":
            result = text.upper()
        elif mode == "lowercase":
            result = text.lower()
        elif mode == "reverse":
            result = text[::-1]
        elif mode == "deduplicate":
            result = "".join(dict.fromkeys(text))
        else:
            result = text

        return {"result": result}
```

### 示例 B：平台发布插件

**plugin.json：**
```json
{
  "id": "weibo-publish",
  "name": "微博发布器",
  "version": "1.0.0",
  "description": "向微博平台发布内容",
  "category": "platform",
  "entry_point": "weibo_publish.py:WeiboPublishPlugin",
  "display_icon": "📝",
  "capabilities": ["authenticate", "publish"],
  "permissions_required": ["network:https"],
  "config_schema": {
    "type": "object",
    "properties": {
      "cookie": {"type": "string", "description": "微博Cookie"}
    },
    "required": ["cookie"]
  },
  "is_builtin": false,
  "is_enabled_by_default": false
}
```

**weibo_publish.py：**
```python
from app.core.base_interfaces import BasePlatformPlugin, PluginContext
from app.core.plugin_types import PublishResult
from typing import Any, Dict

class WeiboPublishPlugin(BasePlatformPlugin):

    @property
    def plugin_id(self) -> str:
        return "weibo-publish"

    @property
    def plugin_name(self) -> str:
        return "微博发布器"

    async def authenticate(self, credentials: Dict[str, Any], ctx: PluginContext) -> bool:
        cookie = credentials.get("cookie", "")
        return bool(cookie)

    async def publish(self, content: Dict[str, Any], config: Dict[str, Any], ctx: PluginContext) -> PublishResult:
        title = content.get("title", "")
        body = content.get("content", "")
        # 实际发布逻辑...
        return PublishResult.ok(platform_url="https://weibo.com/xxx", content_id="123")
```

### 示例 C：UI 主题插件（简单模式）

**plugin.json：**
```json
{
  "id": "dark-cat-theme",
  "name": "暗夜猫咪主题",
  "version": "1.0.0",
  "description": "暗色主题，带猫咪装饰元素",
  "category": "ui_theme",
  "entry_point": "dark_cat.py:DarkCatPlugin",
  "display_icon": "🌙",
  "capabilities": ["ui_overlay"],
  "permissions_required": [],
  "config_schema": {
    "type": "object",
    "properties": {
      "accent_color": {"type": "string", "default": "#6366f1", "description": "强调色"}
    }
  },
  "is_builtin": false,
  "is_enabled_by_default": false
}
```

**dark_cat.py：**
```python
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class DarkCatPlugin:
    """UI 主题插件 — 后端仅管配置，前端自行实现"""

    PLUGIN_ID = "dark-cat-theme"

    def __init__(self):
        self.config = {"accent_color": "#6366f1"}
        logger.info(f"[{self.PLUGIN_ID}] loaded")

    def get_config(self) -> Dict[str, Any]:
        return self.config.copy()

    def update_config(self, new_config: Dict[str, Any]) -> None:
        self.config.update(new_config)

    def on_enable(self) -> None:
        logger.info(f"[{self.PLUGIN_ID}] enabled")

    def on_disable(self) -> None:
        logger.info(f"[{self.PLUGIN_ID}] disabled")
```

---

## 七、导入流程

1. 将 `plugin.json` + `.py` 文件打包成 `.zip`
2. 在平台 **设置 → 插件管理 → 上传按钮** 选择 zip 文件
3. 系统自动：验证 → 解压 → 同步数据库 → 安装
4. 在插件列表点击 **启动** 即可使用

---

## 八、注意事项

- `id` 不能与内置插件冲突（crab-companion、ai-copywrite-node、xiaohongshu-publish、monitor-agent）
- zip 包最大 50MB
- zip 内文件路径不能包含 `..`（安全限制）
- 第三方插件卸载时会删除文件，内置插件不可卸载
- UI 类插件的前端 Vue 组件需要额外手动集成到前端代码
- 工作流节点插件会自动出现在工作流编辑器的节点面板中