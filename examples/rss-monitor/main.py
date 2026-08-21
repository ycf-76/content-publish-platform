"""
RSS Monitor Plugin - 数据源插件示例

功能特性:
- RSS/Atom feed解析与监控
- 智能内容过滤（关键词包含/排除）
- 基于标题/URL的去重机制
- 轮询统计与错误追踪
- 新内容事件通知

适用场景: 新闻监控、博客更新追踪、技术动态跟踪等
"""

import asyncio
import hashlib
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple, Set
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


# ===== 基础数据模型 =====

@dataclass
class FeedItem:
    """RSS条目"""
    title: str
    url: str
    summary: str = ""
    published_at: Optional[datetime] = None
    author: str = ""
    feed_url: str = ""
    categories: List[str] = field(default_factory=list)
    content_hash: str = ""  # 用于去重
    
    def __post_init__(self):
        if not self.content_hash and self.title:
            self.content_hash = hashlib.md5(f"{self.title}:{self.url}".encode()).hexdigest()[:16]


@dataclass
class FeedStats:
    """Feed统计信息"""
    url: str
    total_items: int = 0
    new_items: int = 0
    last_poll_time: Optional[datetime] = None
    last_error: Optional[str] = None
    consecutive_errors: int = 0


@dataclass
class PollResult:
    """轮询结果"""
    items: List[FeedItem]
    summary: Dict[str, Any]
    success: bool = True
    error_message: str = ""
    execution_time_ms: int = 0


# ===== 插件主类 =====

class RSSMonitorPlugin:
    """
    RSS订阅源监控插件
    
    展示datasource类型插件的完整实现，包括:
    - 外部数据源集成
    - 定时轮询模式
    - 内容过滤与去重
    - 统计与监控
    """
    
    # ===== 内部数据结构 =====
    
    @dataclass
    class HealthStatus:
        def __init__(self, status: str, message: str, timestamp: datetime = None, details: dict = None):
            self.status = status
            self.message = message
            self.timestamp = timestamp or datetime.utcnow()
            self.details = details or {}
    
    @dataclass
    class PluginManifest:
        id: str
        name: str
        version: str
        description: str
        author: str
        capabilities: list
        permissions_required: list
    
    @dataclass
    class PluginContext:
        def __init__(self):
            self.user_id = "anonymous"
            self.config = {}
            self.event_bus = MockEventBus()
            self.storage = {}
    
    # ===== 初始化 =====
    
    def __init__(self):
        self.id = "rss-monitor"
        self.name = "RSS Monitor"
        self.version = "1.0.0"
        
        # 内部状态
        self._seen_hashes: Set[str] = set()  # 已见过的内容hash
        self._feed_stats: Dict[str, FeedStats] = {}  # 各feed的统计信息
        self._last_poll_times: Dict[str, datetime] = {}  # 上次轮询时间
        
        # 统计计数器
        self._stats = {
            "total_polls": 0,
            "total_items_found": 0,
            "total_new_items": 0,
            "total_errors": 0,
            "cache_hits": 0
        }
    
    # ===== 生命周期方法 =====
    
    async def on_load(self):
        """插件加载时调用"""
        print("[rss-monitor] Plugin loaded successfully")
        return True
    
    async def on_unload(self):
        """插件卸载时调用"""
        print("[rss-monitor] Plugin unloaded. Stats:", self._stats)
        return True
    
    async def health_check(self) -> 'HealthStatus':
        """健康检查"""
        active_feeds = len([s for s in self._feed_stats.values() if s.consecutive_errors < 3])

        return self.HealthStatus(
            status="healthy" if active_feeds > 0 else "degraded",
            message=f"Monitoring {len(self._feed_stats)} feeds ({active_feeds} active)",
            details={
                "feeds_count": len(self._feed_stats),
                "active_feeds": active_feeds,
                "total_items_seen": len(self._seen_hashes),
                "stats": self._stats.copy()
            }
        )
    
    def get_manifest(self) -> 'PluginManifest':
        """返回插件清单"""
        return self.PluginManifest(
            id=self.id,
            name=self.name,
            version=self.version,
            description="RSS subscription monitor with filtering and deduplication",
            author="Platform Team <dev@your-platform.com>",
            capabilities=["execute", "poll", "validate_config"],
            permissions_required=["network:read", "storage:read_write"]
        )
    
    # ===== 核心方法 =====
    
    async def validate_inputs(self, inputs: Dict[str, Any]) -> Tuple[bool, str]:
        """验证输入参数"""
        action = inputs.get("action", "poll_now")
        
        valid_actions = ["poll_now", "list_feeds", "get_stats", "clear_cache"]
        if action not in valid_actions:
            return False, f"Invalid action '{action}'. Must be one of: {valid_actions}"
        
        if action == "poll_now":
            feed_url = inputs.get("feed_url")
            if feed_url:
                parsed = urlparse(feed_url)
                if not all([parsed.scheme, parsed.netloc]):
                    return False, f"Invalid feed URL format: {feed_url}"
        
        return True, "Inputs validated"
    
    async def validate_config(self, config: Dict[str, Any]) -> Tuple[bool, str]:
        """验证配置"""
        if "feed_urls" not in config or not config["feed_urls"]:
            return False, "At least one feed URL is required"
        
        for url in config["feed_urls"]:
            parsed = urlparse(url)
            if not all([parsed.scheme in ['http', 'https'], parsed.netloc]):
                return False, f"Invalid feed URL: {url}"
        
        poll_interval = config.get("poll_interval_minutes", 30)
        if not (5 <= poll_interval <= 1440):
            return False, "Poll interval must be between 5 and 1440 minutes"
        
        return True, "Configuration validated"
    
    async def execute(
        self,
        ctx: 'PluginContext',
        inputs: Dict[str, Any]
    ) -> 'NodeOutput':
        """
        执行主要操作
        
        支持的操作:
        - poll_now: 立即轮询所有或指定feed
        - list_feeds: 列出所有配置的feed及其状态
        - get_stats: 获取详细统计信息
        - clear_cache: 清除去重缓存
        """
        start_time = asyncio.get_event_loop().time()
        
        try:
            is_valid, error_msg = await self.validate_inputs(inputs)
            if not is_valid:
                return NodeOutput(success=False, data={}, message=error_msg, execution_time_ms=0)
            
            config = ctx.config or {}
            action = inputs.get("action", "poll_now")
            
            if action == "poll_now":
                result = await self._execute_poll(ctx, config, inputs)
            elif action == "list_feeds":
                result = await self._list_feeds(config)
            elif action == "get_stats":
                result = await self._get_stats()
            elif action == "clear_cache":
                result = await self._clear_cache()
            else:
                result = NodeOutput(success=False, data={}, message=f"Unknown action: {action}", execution_time_ms=0)
            
            elapsed_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
            result.execution_time_ms = elapsed_ms
            
            return result
        
        except Exception as e:
            elapsed_ms = int((asyncio.get_event_loop().time() - start_time) * 1000)
            return NodeOutput(
                success=False,
                data={},
                message=f"Execution failed: {str(e)}",
                execution_time_ms=elapsed_ms
            )
    
    # ===== 操作实现 =====
    
    async def _execute_poll(
        self,
        ctx: 'PluginContext',
        config: Dict[str, Any],
        inputs: Dict[str, Any]
    ) -> 'NodeOutput':
        """执行轮询操作"""
        feed_urls = config.get("feed_urls", [])
        target_feed = inputs.get("feed_url")
        
        if target_feed:
            if target_feed not in feed_urls:
                return NodeOutput(success=False, data={}, message=f"Feed not configured: {target_feed}")
            urls_to_poll = [target_feed]
        else:
            urls_to_poll = feed_urls
        
        max_items = config.get("max_items_per_feed", 20)
        since_timestamp = inputs.get("since_timestamp")
        
        all_items = []
        errors = []
        total_new = 0
        
        for feed_url in urls_to_poll:
            try:
                items, new_count = await self._fetch_and_parse_feed(
                    feed_url=feed_url,
                    config=config,
                    max_items=max_items,
                    since_timestamp=since_timestamp,
                    ctx=ctx
                )
                
                all_items.extend(items)
                total_new += new_count
                
                # 更新统计
                self._update_feed_stats(feed_url, len(items), new_count, None)
                
            except Exception as e:
                error_msg = f"Failed to fetch {feed_url}: {str(e)}"
                errors.append({"url": feed_url, "error": error_msg})
                self._update_feed_stats(feed_url, 0, 0, error_msg)
                self._stats["total_errors"] += 1
                
                if ctx.event_bus:
                    await ctx.event_bus.emit("rss:error_occurred", {
                        "plugin_id": self.id,
                        "feed_url": feed_url,
                        "error": error_msg
                    })
        
        self._stats["total_polls"] += 1
        self._stats["total_items_found"] += len(all_items)
        self._stats["total_new_items"] += total_new
        
        # 构建输出
        output_data = {
            "items": [asdict(item) for item in all_items],
            "summary": {
                "total_feeds_polled": len(urls_to_poll),
                "total_items": len(all_items),
                "new_items": total_new,
                "errors_count": len(errors),
                "processing_time_ms": 0  # 将在execute中更新
            }
        }
        
        if errors:
            output_data["summary"]["errors"] = errors
        
        # 发送完成事件
        if ctx.event_bus and total_new > 0:
            await ctx.event_bus.emit("rss:poll_completed", {
                "plugin_id": self.id,
                "items_found": len(all_items),
                "new_items": total_new,
                "feeds_polled": len(urls_to_poll)
            })
        
        return NodeOutput(
            success=len(errors) < len(urls_to_poll),  # 部分成功也算成功
            data=output_data,
            message=f"Polled {len(all_items)} items ({total_new} new) from {len(urls_to_poll)} feeds"
        )
    
    async def _fetch_and_parse_feed(
        self,
        feed_url: str,
        config: Dict[str, Any],
        max_items: int,
        since_timestamp: Optional[str],
        ctx: 'PluginContext'
    ) -> Tuple[List[FeedItem], int]:
        """
        获取并解析单个feed
        
        返回: (items列表, 新项目数)
        """
        # 模拟RSS解析（实际项目中使用feedparser库）
        mock_items = self._generate_mock_feed_items(feed_url, max_items)
        
        # 应用过滤器
        filtered_items = self._apply_filters(mock_items, config)
        
        # 去重
        new_items = []
        for item in filtered_items:
            if item.content_hash not in self._seen_hashes:
                new_items.append(item)
                self._seen_hashes.add(item.content_hash)
        
        # 发送新项目事件
        if ctx.event_bus and config.get("notify_on_new_items", True):
            for item in new_items:
                await ctx.event_bus.emit("rss:new_item_found", {
                    "plugin_id": self.id,
                    "title": item.title,
                    "url": item.url,
                    "feed_url": item.feed_url,
                    "published_at": item.published_at.isoformat() if item.published_at else None
                })
        
        return filtered_items, len(new_items)
    
    def _generate_mock_feed_items(self, feed_url: str, count: int) -> List[FeedItem]:
        """生成模拟RSS数据（用于演示）"""
        import random
        
        domains = {
            "bbc.com": "BBC News",
            "nytimes.com": "New York Times",
            "techcrunch.com": "TechCrunch",
            "github.com": "GitHub Blog"
        }
        
        domain = urlparse(feed_url).netloc.replace("www.", "")
        source_name = domains.get(domain, "Unknown Source")
        
        titles = [
            lambda idx, sn=source_name: f"{sn}: Tech and AI Breakthrough #{idx}",
            lambda idx, sn=source_name: f"Technology Update: AI Machine Learning Advances #{idx}",
            lambda idx, sn=source_name: f"AI Market Analysis: Q{idx} Report Released",
            lambda idx, sn=source_name: f"Tech Tutorial: Getting Started with AI Plugin Development",
            lambda idx, sn=source_name: f"Security Alert: New Tech Vulnerability in AI Systems #{idx}"
        ]
        
        items = []
        now = datetime.utcnow()
        
        for i in range(min(count, len(titles))):
            pub_date = now - timedelta(hours=random.randint(0, 72))

            item = FeedItem(
                title=titles[i % len(titles)](i+1),
                url=f"{feed_url}/item/{i+1}",
                summary=f"This is a sample RSS item from {source_name}. Content preview here...",
                published_at=pub_date,
                author=f"{source_name} Editor",
                feed_url=feed_url,
                categories=["news", "technology"] if random.random() > 0.5 else ["general"]
            )
            items.append(item)
        
        return items
    
    def _apply_filters(self, items: List[FeedItem], config: Dict[str, Any]) -> List[FeedItem]:
        """应用内容过滤"""
        if not config.get("enable_content_filter", True):
            return items
        
        filter_config = config.get("filter_keywords", {})
        include_keywords = filter_config.get("include", [])
        exclude_keywords = filter_config.get("exclude", [])
        
        filtered = []
        
        for item in items:
            text = f"{item.title} {item.summary}".lower()
            
            # 排除过滤
            should_exclude = False
            for keyword in exclude_keywords:
                if keyword.lower() in text:
                    should_exclude = True
                    break
            
            if should_exclude:
                continue
            
            # 包含过滤（如果配置了include，则只保留匹配的）
            if include_keywords:
                matches_any = any(kw.lower() in text for kw in include_keywords)
                if not matches_any:
                    continue
            
            filtered.append(item)
        
        return filtered
    
    async def _list_feeds(self, config: Dict[str, Any]) -> 'NodeOutput':
        """列出所有feed状态"""
        feed_urls = config.get("feed_urls", [])
        
        feeds_info = []
        for url in feed_urls:
            stats = self._feed_stats.get(url)
            feeds_info.append({
                "url": url,
                "status": "active" if stats and stats.consecutive_errors < 3 else "error" if stats else "never_polled",
                "total_items": stats.total_items if stats else 0,
                "new_items_last_poll": stats.new_items if stats else 0,
                "last_poll": stats.last_poll_time.isoformat() if stats and stats.last_poll_time else None,
                "last_error": stats.last_error if stats else None
            })
        
        return NodeOutput(
            success=True,
            data={"feeds": feeds_info, "count": len(feeds_info)},
            message=f"Listed {len(feeds_info)} configured feeds"
        )
    
    async def _get_stats(self) -> 'NodeOutput':
        """获取详细统计"""
        return NodeOutput(
            success=True,
            data={
                "global_stats": self._stats.copy(),
                "feed_stats": {url: asdict(stats) for url, stats in self._feed_stats.items()},
                "cache_size": len(self._seen_hashes),
                "uptime_since": datetime.utcnow().isoformat()
            },
            message="Statistics retrieved"
        )
    
    async def _clear_cache(self) -> 'NodeOutput':
        """清除去重缓存"""
        cleared_count = len(self._seen_hashes)
        self._seen_hashes.clear()
        
        return NodeOutput(
            success=True,
            data={"cleared_items": cleared_count},
            message=f"Cleared {cleared_count} items from dedup cache"
        )
    
    def _update_feed_stats(
        self,
        feed_url: str,
        total_items: int,
        new_items: int,
        error: Optional[str]
    ):
        """更新feed统计信息"""
        if feed_url not in self._feed_stats:
            self._feed_stats[feed_url] = FeedStats(url=feed_url)
        
        stats = self._feed_stats[feed_url]
        stats.total_items += total_items
        stats.new_items += new_items
        stats.last_poll_time = datetime.utcnow()
        
        if error:
            stats.last_error = error
            stats.consecutive_errors += 1
        else:
            stats.last_error = None
            stats.consecutive_errors = 0


# ===== 辅助类 =====

class MockEventBus:
    """模拟事件总线"""
    
    def __init__(self):
        self.emitted_events = []
    
    async def emit(self, event_type: str, data: dict):
        """发出事件"""
        self.emitted_events.append({
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat()
        })
        print(f"[EventBus] Emitted: {event_type}")


@dataclass
class NodeOutput:
    """标准输出格式"""
    success: bool
    data: Dict[str, Any]
    message: str = ""
    execution_time_ms: int = 0


# ===== 本地测试入口 =====

if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("=" * 70)
        print("  RSS Monitor Plugin - Local Test Mode")
        print("=" * 70)
        
        plugin = RSSMonitorPlugin()
        
        # Test 1: Plugin info
        print("\n[Test 1] Plugin manifest:")
        manifest = plugin.get_manifest()
        print(f"  ID: {manifest.id}")
        print(f"  Name: {manifest.name}")
        print(f"  Capabilities: {manifest.capabilities}")
        
        # Test 2: Input validation
        print("\n[Test 2] Input validation:")
        valid, msg = await plugin.validate_inputs({"action": "poll_now"})
        print(f"  Valid input: {valid}, Message: {msg}")
        
        valid, msg = await plugin.validate_inputs({"action": "invalid_action"})
        print(f"  Invalid input: {valid}, Message: {msg}")
        
        # Test 3: Config validation
        print("\n[Test 3] Config validation:")
        config = {"feed_urls": ["https://example.com/rss.xml"]}
        valid, msg = await plugin.validate_config(config)
        print(f"  Valid config: {valid}, Message: {msg}")
        
        valid, msg = await plugin.validate_config({})
        print(f"  Invalid config: {valid}, Message: {msg}")
        
        # Test 4: Health check
        print("\n[Test 4] Health check:")
        health = await plugin.health_check()
        print(f"  Status: {health.status}")
        print(f"  Message: {health.message}")
        
        # Test 5: Execute poll_now
        print("\n[Test 5] Execute poll operation:")
        ctx = plugin.PluginContext()
        ctx.config = {
            "feed_urls": [
                "https://feeds.bbci.co.uk/news/technology/rss.xml",
                "https://techcrunch.com/feed/"
            ],
            "max_items_per_feed": 5,
            "enable_content_filter": True,
            "filter_keywords": {
                "include": ["technology", "AI"],
                "exclude": ["advertisement", "spam"]
            },
            "notify_on_new_items": True
        }
        
        result = await plugin.execute(ctx, {"action": "poll_now"})
        print(f"  Success: {result.success}")
        print(f"  Items found: {len(result.data.get('items', []))}")
        print(f"  New items: {result.data.get('summary', {}).get('new_items', 0)}")
        print(f"  Message: {result.message}")
        
        # Test 6: List feeds
        print("\n[Test 6] List feeds:")
        result = await plugin.execute(ctx, {"action": "list_feeds"})
        print(f"  Feeds listed: {result.data.get('count', 0)}")
        
        # Test 7: Get stats
        print("\n[Test 7] Get statistics:")
        result = await plugin.execute(ctx, {"action": "get_stats"})
        stats = result.data.get("global_stats", {})
        print(f"  Total polls: {stats.get('total_polls', 0)}")
        print(f"  Total items: {stats.get('total_items_found', 0)}")
        print(f"  Cache size: {result.data.get('cache_size', 0)}")
        
        # Test 8: Clear cache
        print("\n[Test 8] Clear dedup cache:")
        result = await plugin.execute(ctx, {"action": "clear_cache"})
        print(f"  Cleared: {result.data.get('cleared_items', 0)} items")
        
        print("\n" + "=" * 70)
        print("  All tests completed!")
        print("=" * 70)
        print("\nNote: This plugin uses mock data for demonstration.")
        print("      In production, install feedparser for real RSS parsing:")
        print("      pip install feedparser httpx")
    
    asyncio.run(test())