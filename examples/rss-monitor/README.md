# 📡 RSS Monitor Plugin

> **复杂度**: ⭐⭐⭐ | **类型**: datasource | **预计学习时间**: 2-3小时

RSS订阅源监控插件 - 展示**数据源类型插件**的完整实现，包括外部数据获取、内容过滤、去重和事件通知。

---

## 📖 目录

- [功能特性](#功能特性)
- [适用场景](#适用场景)
- [架构设计](#架构设计)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [API参考](#api参考)
- [核心实现解析](#核心实现解析)
- [最佳实践](#最佳实践)
- [扩展建议](#扩展建议)

---

## ✨ 功能特性

### 核心能力

| 功能 | 描述 | 实现方式 |
|------|------|---------|
| **RSS/Atom解析** | 支持标准RSS 2.0和Atom格式 | feedparser库 |
| **多Feed管理** | 同时监控多个订阅源 | 配置列表 + 轮询 |
| **智能过滤** | 基于关键词的包含/排除过滤 | 正则匹配 |
| **自动去重** | 防止重复处理相同内容 | MD5哈希 |
| **事件通知** | 新内容实时推送 | EventBus |
| **统计监控** | Feed健康状态追踪 | 内置计数器 |

### 数据流

```
[配置Feed URLs]
      ↓
[定时轮询触发]
      ↓
[HTTP请求 → RSS XML]
      ↓
[feedparser解析]
      ↓
[内容过滤（include/exclude）]
      ↓
[去重检查（MD5 hash）]
      ↓
[新项目 → EventBus通知]
      ↓
[结果聚合 → 返回NodeOutput]
```

---

## 🎯 适用场景

### 1. 新闻媒体监控
```python
config = {
    "feed_urls": [
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Technology.xml"
    ],
    "filter_keywords": {
        "include": ["AI", "machine learning", "blockchain"],
        "exclude": ["advertisement"]
    }
}
```

### 2. 技术博客追踪
```python
config = {
    "feed_urls": [
        "https://github.blog/feed/",
        "https://medium.com/feed/@techblog"
    ],
    "poll_interval_minutes": 60,
    "max_items_per_feed": 10
}
```

### 3. 竞品动态监测
```python
config = {
    "feed_urls": [
        "https://competitor.com/blog/rss",
        "https://competitor.com/releases.atom"
    ],
    "notify_on_new_items": True
}
```

---

## 🏗️ 架构设计

### 类结构

```
RSSMonitorPlugin (主类)
├── __init__()              # 初始化状态
├── Lifecycle Methods       # 生命周期
│   ├── on_load()          # 加载插件
│   ├── on_unload()        # 卸载插件
│   └── health_check()     # 健康检查
├── Validation             # 验证方法
│   ├── validate_inputs()  # 输入验证
│   └── validate_config()  # 配置验证
├── Core Operations        # 核心操作
│   ├── execute()          # 主入口（分发操作）
│   ├── _execute_poll()    # 执行轮询
│   ├── _list_feeds()      # 列出Feeds
│   ├── _get_stats()       # 获取统计
│   └── _clear_cache()     # 清除缓存
├── Data Processing        # 数据处理
│   ├── _fetch_and_parse_feed()  # 获取+解析
│   ├── _apply_filters()         # 内容过滤
│   └── _update_feed_stats()     # 更新统计
└── Internal State         # 内部状态
    ├── _seen_hashes: Set[str]           # 已见hash集合
    ├── _feed_stats: Dict[str, FeedStats] # Feed统计
    └── _stats: Dict                       # 全局统计
```

### 数据模型

```python
@dataclass
class FeedItem:
    title: str                    # 文章标题
    url: str                      # 文章链接
    summary: str = ""            # 摘要
    published_at: datetime = None # 发布时间
    author: str = ""             # 作者
    feed_url: str = ""           # 来源Feed
    categories: List[str] = []   # 分类标签
    content_hash: str = ""       # 去重哈希（自动生成）

@dataclass
class FeedStats:
    url: str                          # Feed URL
    total_items: int = 0              # 总项目数
    new_items: int = 0                # 新项目数
    last_poll_time: datetime = None   # 上次轮询时间
    last_error: Optional[str] = None  # 最后错误
    consecutive_errors: int = 0       # 连续错误次数
```

---

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install feedparser httpx
```

### 2. 基本使用

```python
from main import RSSMonitorPlugin
import asyncio

async def main():
    plugin = RSSMonitorPlugin()

    ctx = plugin.PluginContext()
    ctx.config = {
        "feed_urls": ["https://feeds.bbci.co.uk/news/rss.xml"],
        "poll_interval_minutes": 30
    }

    result = await plugin.execute(ctx, {"action": "poll_now"})

    if result.success:
        for item in result.data["items"]:
            print(f"[{item['published_at']}] {item['title']}")
            print(f"  {item['url']}")
    else:
        print(f"Error: {result.message}")

asyncio.run(main())
```

### 3. 运行本地测试

```bash
cd rss-monitor
python main.py
```

### 4. 运行单元测试

```bash
cd rss-monitor
python -m pytest tests/test_main.py -v
```

---

## ⚙️ 配置说明

### 必填参数

| 参数 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `feed_urls` | array | RSS/Atom feed URL列表 | `["https://example.com/rss.xml"]` |

### 可选参数

#### 轮询控制

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `poll_interval_minutes` | integer | `30` | 轮询间隔（5-1440分钟）|
| `max_items_per_feed` | integer | `20` | 每个feed最大获取数 |
| `timeout_seconds` | integer | `30` | HTTP请求超时时间 |

#### 内容过滤

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_content_filter` | boolean | `true` | 是否启用过滤 |
| `filter_keywords.include` | array | `[]` | 包含关键词（任一匹配）|
| `filter_keywords.exclude` | array | `[]` | 排除关键词（任一排除）|

#### 去重设置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `dedup_enabled` | boolean | `true` | 是否启用去重 |
| `dedup_window_hours` | integer | `168` | 去重时间窗口（7天）|

#### 通知设置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `notify_on_new_items` | boolean | `true` | 发现新内容时发送事件 |

### 配置示例

```json
{
  "feed_urls": [
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "https://techcrunch.com/feed/",
    "https://github.blog/feed/"
  ],
  "poll_interval_minutes": 15,
  "max_items_per_feed": 25,
  "enable_content_filter": true,
  "filter_keywords": {
    "include": ["AI", "ML", "GPT", "LLM"],
    "exclude": ["advertisement", "sponsored", "clickbait"]
  },
  "dedup_enabled": true,
  "dedup_window_hours": 72,
  "notify_on_new_items": true
}
```

---

## 📡 API参考

### execute() 操作列表

#### 1. poll_now - 立即轮询

**输入**
```python
{
    "action": "poll_now",
    "feed_url": "https://optional-specific-feed.com/rss.xml",  # 可选
    "since_timestamp": "2024-01-01T00:00:00Z"  # 可选，只获取此后的内容
}
```

**输出**
```python
{
    "success": true,
    "data": {
        "items": [
            {
                "title": "Article Title",
                "url": "https://...",
                "summary": "...",
                "published_at": "2024-01-15T10:30:00Z",
                "author": "Author Name",
                "feed_url": "https://...",
                "categories": ["tech", "AI"]
            }
        ],
        "summary": {
            "total_feeds_polled": 3,
            "total_items": 45,
            "new_items": 12,
            "errors_count": 0
        }
    },
    "message": "Polled 45 items (12 new) from 3 feeds"
}
```

#### 2. list_feeds - 列出Feeds

**输出示例**
```python
{
    "feeds": [
        {
            "url": "https://example.com/rss.xml",
            "status": "active",
            "total_items": 150,
            "new_items_last_poll": 5,
            "last_poll": "2024-01-15T10:30:00Z",
            "last_error": null
        }
    ]
}
```

#### 3. get_stats - 获取统计

**输出示例**
```python
{
    "global_stats": {
        "total_polls": 100,
        "total_items_found": 2500,
        "total_new_items": 800,
        "total_errors": 5
    },
    "feed_stats": {...},
    "cache_size": 2400
}
```

#### 4. clear_cache - 清除缓存

**输出示例**
```python
{
    "cleared_items": 1500
}
```

### 事件列表

| 事件名 | 触发条件 | 数据载荷 |
|--------|---------|---------|
| `rss:new_item_found` | 发现新内容 | `{title, url, feed_url, published_at}` |
| `rss:poll_completed` | 轮询完成 | `{items_found, new_items, feeds_polled}` |
| `rss:error_occurred` | 发生错误 | `{feed_url, error}` |

---

## 🔍 核心实现解析

### 1. 轮询机制

```python
async def _execute_poll(self, ctx, config, inputs):
    urls_to_poll = self._determine_feeds_to_poll(config, inputs)

    for feed_url in urls_to_poll:
        try:
            items, new_count = await self._fetch_and_parse_feed(
                feed_url, config, max_items, since_timestamp, ctx
            )
            all_items.extend(items)
            total_new += new_count
            self._update_feed_stats(feed_url, len(items), new_count, None)
        except Exception as e:
            errors.append({"url": feed_url, "error": str(e)})
            self._update_feed_stats(feed_url, 0, 0, str(e))
```

**关键点**：
- 逐个feed处理，避免单个失败影响整体
- 统计每个feed的成功/失败情况
- 错误信息收集后统一返回

### 2. 内容过滤

```python
def _apply_filters(self, items, config):
    if not config.get("enable_content_filter"):
        return items

    filter_config = config.get("filter_keywords", {})
    include_kw = filter_config.get("include", [])
    exclude_kw = filter_config.get("exclude", [])

    filtered = []
    for item in items:
        text = f"{item.title} {item.summary}".lower()

        # 先排除
        if any(kw.lower() in text for kw in exclude_kw):
            continue

        # 再包含（如果配置了）
        if include_kw and not any(kw.lower() in text for kw in include_kw):
            continue

        filtered.append(item)

    return filtered
```

**关键点**：
- 排除优先于包含
- 大小写不敏感匹配
- 标题+摘要联合搜索

### 3. 去重机制

```python
def __post_init__(self):
    if not self.content_hash and self.title:
        # 使用标题+URL生成唯一标识
        self.content_hash = hashlib.md5(
            f"{self.title}:{self.url}".encode()
        ).hexdigest()[:16]

# 在轮询时检查
if item.content_hash not in self._seen_hashes:
    new_items.append(item)
    self._seen_hashes.add(item.content_hash)
```

**优势**：
- 自动生成，无需手动管理
- 16位短哈希，节省内存
- 基于标题+URL，稳定可靠

### 4. 统计追踪

```python
def _update_feed_stats(self, feed_url, total_items, new_items, error):
    if feed_url not in self._feed_stats:
        self._feed_stats[feed_url] = FeedStats(url=feed_url)

    stats = self._feed_stats[feed_url]
    stats.total_items += total_items
    stats.new_items += new_items
    stats.last_poll_time = datetime.utcnow()

    if error:
        stats.last_error = error
        stats.consecutive_errors += 1  # 累加错误
    else:
        stats.consecutive_errors = 0   # 成功则重置
```

**用途**：
- 检测异常Feed（连续错误）
- 监控各Feed活跃度
- 支持健康检查决策

---

## 💡 最佳实践

### ✅ 推荐做法

1. **合理设置轮询间隔**
   ```python
   # 新闻源：15-30分钟
   "poll_interval_minutes": 15

   # 博客：1-6小时
   "poll_interval_minutes": 60

   # 官方公告：每天1-2次
   "poll_interval_minutes": 720
   ```

2. **使用精确的关键词过滤**
   ```python
   "filter_keywords": {
       "include": ["machine learning", "deep learning"],  # 具体术语
       "exclude": ["clickbait", "you won't believe"]      # 排除垃圾
   }
   ```

3. **监控Feed健康状况**
   ```python
   health = await plugin.health_check()
   if health.details["active_feeds"] < health.details["feeds_count"]:
       # 有Feed可能有问题，需要关注
       pass
   ```

4. **定期清缓存防止内存膨胀**
   ```python
   # 每周清理一次
   await plugin.execute(ctx, {"action": "clear_cache"})
   ```

### ❌ 应避免

1. **不要过于频繁轮询**
   - 对服务器造成压力
   - 可能被IP封禁
   - 建议：最少5分钟间隔

2. **不要忽略错误累积**
   - 连续错误通常意味着Feed失效
   - 应该有告警机制

3. **不要在过滤中使用太通用的词**
   ```python
   # 差：会匹配太多内容
   "include": ["the", "a", "is"]

   # 好：使用领域特定词汇
   "include": ["GPT-4", "transformer", "BERT"]
   ```

---

## 🔧 扩展建议

### 1. 添加持久化存储

```python
import json
from pathlib import Path

class PersistentRSSMonitor(RSSMonitorPlugin):
    def __init__(self, storage_path: str = "./rss_data"):
        super().__init__()
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)

    async def save_state(self):
        state_file = self.storage_path / "state.json"
        with open(state_file, 'w') as f:
            json.dump({
                "seen_hashes": list(self._seen_hashes),
                "feed_stats": {k: asdict(v) for k, v in self._feed_stats.items()},
                "stats": self._stats
            }, f)

    async def load_state(self):
        state_file = self.storage_path / "state.json"
        if state_file.exists():
            with open(state_file) as f:
                state = json.load(f)
                self._seen_hashes = set(state["seen_hashes"])
                # ...恢复其他状态
```

### 2. 添加全文抓取

```python
import httpx
from bs4 import BeautifulSoup

async def fetch_full_content(self, url: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        # 提取主要内容（需要根据网站结构调整）
        content = soup.find('article') or soup.find('main')
        return content.get_text() if content else ""
```

### 3. 添加智能摘要

```python
async def generate_summary(self, text: str, max_length: int = 200) -> str:
    """使用LLM生成文章摘要"""
    prompt = f"请用{max_length}字以内总结以下内容：\n\n{text}"
    
    # 调用LLM API...
    summary = await llm_client.complete(prompt)
    return summary
```

### 4. 添加多语言支持

```python
from langdetect import detect

def detect_language(self, text: str) -> str:
    try:
        return detect(text)
    except:
        return "unknown"

# 在FeedItem中添加language字段
item.language = self.detect_language(item.title + " " + item.summary)
```

---

## 🧪 测试覆盖

运行测试套件：

```bash
pytest tests/test_main.py -v
```

### 测试类别

| 测试类 | 数量 | 覆盖范围 |
|--------|------|---------|
| TestPluginInitialization | 3 | 插件初始化、状态、清单 |
| TestInputValidation | 8 | 输入参数验证 |
| TestConfigValidation | 6 | 配置参数验证 |
| TestHealthCheck | 2 | 健康检查逻辑 |
| TestExecutePollNow | 6 | 轮询操作主流程 |
| TestListFeeds | 3 | Feed列表示例 |
| TestGetStats | 3 | 统计信息查询 |
| TestClearCache | 2 | 缓存清除功能 |
| TestContentFiltering | 2 | 过滤器效果 |
| TestDeduplication | 2 | 去重机制 |
| TestErrorHandling | 2 | 错误处理 |
| TestLifecycleMethods | 2 | 生命周期方法 |
| TestDataModels | 3 | 数据模型正确性 |
| **总计** | **44** | - |

---

## 📊 性能指标

基于模拟数据的性能表现：

| 指标 | 数值 | 说明 |
|------|------|------|
| 单次轮询耗时 | < 100ms | 3个Feed，每Feed 10条目 |
| 内存占用 | < 5MB | 缓存1000条目 |
| 去重准确率 | 100% | MD5碰撞概率极低 |
| 过滤速度 | < 1ms | 100条目，10个关键词 |

---

## ❓ 常见问题

### Q: 如何处理认证保护的Feed？

A: 在配置中添加认证信息：
```python
ctx.config["auth_credentials"] = {
    "type": "basic",  # 或 "oauth2", "api_key"
    "username": "user",
    "password": "pass"
}
```

### Q: 如何处理编码问题？

A: feedparser会自动检测编码，如遇问题可手动指定：
```python
response.encoding = 'utf-8'  # 或 'gb2312', 'shift_jis'
```

### Q: Feed更新频率不一致怎么办？

A: 使用`last_poll_time`跟踪，结合`since_timestamp`参数：
```python
inputs = {
    "action": "poll_now",
    "since_timestamp": last_successful_poll.isoformat()
}
```

### Q: 如何限制内存使用？

A: 定期清理旧hash，或使用LRU策略：
```python
MAX_CACHE_SIZE = 10000
if len(self._seen_hashes) > MAX_CACHE_SIZE:
    # 保留最近的，删除旧的
    self._seen_hashes = set(list(self._seen_hashes)[-MAX_CACHE_SIZE:])
```

---

## 📝 更新日志

### v1.0.0 (2024-01-15)
- ✅ 初始版本发布
- ✅ 支持RSS/Atom解析
- ✅ 内容过滤与去重
- ✅ 事件通知系统
- ✅ 完整测试套件（44个测试）

---

## 🤝 贡献指南

欢迎提交Issue和PR！主要方向：

- 支持更多Feed格式（JSON Feed等）
- 添加分布式爬取支持
- 集成更多LLM服务
- 性能优化（异步并发）

---

## 📄 许可证

MIT License - 自由使用和修改

---

**作者**: Platform Team
**邮箱**: dev@your-platform.com
**版本**: 1.0.0
**最后更新**: 2024-01-15