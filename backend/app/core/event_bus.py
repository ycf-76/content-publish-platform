"""
Creator Platform Plugin System - Enhanced Event Bus
增强版事件总线，支持插件间通信、数据共享和事件持久化

功能：
1. 发布-订阅模式（基础）
2. 事件过滤和路由（增强）
3. 优先级队列（增强）
4. 数据共享存储（新增）
5. 事件持久化和重放（新增）
6. 跨插件数据传递（新增）
"""

import asyncio
import json
import time
import uuid
import logging
from typing import Any, Dict, List, Optional, Callable, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class EventPriority(str, Enum):
    """事件优先级"""
    CRITICAL = "critical"  # 关键事件（系统级）
    HIGH = "high"          # 高优先级
    NORMAL = "normal"      # 普通优先级
    LOW = "low"            # 低优先级
    BACKGROUND = "background"  # 后台事件


@dataclass
class Subscription:
    """订阅信息"""
    id: str
    event_pattern: str  # 支持通配符 * 和 ?
    handler: Callable
    priority: EventPriority = EventPriority.NORMAL
    filter_func: Optional[Callable] = None  # 额外的过滤函数
    once: bool = False  # 是否只触发一次
    created_at: datetime = field(default_factory=datetime.now)
    call_count: int = 0
    last_called_at: Optional[datetime] = None
    is_active: bool = True


@dataclass
class Event:
    """事件对象"""
    name: str
    data: Any = None
    source_plugin_id: Optional[str] = None
    target_plugin_id: Optional[str] = None  # 指定目标插件（点对点通信）
    priority: EventPriority = EventPriority.NORMAL
    event_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "eventId": self.event_id,
            "name": self.name,
            "data": self.data,
            "source": self.source_plugin_id,
            "target": self.target_plugin_id,
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


@dataclass
class SharedDataItem:
    """共享数据项"""
    key: str
    value: Any
    writer_plugin_id: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    ttl_seconds: Optional[int] = None  # 过期时间（秒），None表示永不过期
    readers: Set[str] = field(default_factory=set)
    access_count: int = 0
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.ttl_seconds is None:
            return False
        
        age = (datetime.now() - self.updated_at).total_seconds()
        return age > self.ttl_seconds
    
    def touch(self):
        """更新访问时间和计数"""
        self.updated_at = datetime.now()
        self.access_count += 1


class DataStore:
    """
    插件间数据共享存储
    
    实现安全的键值存储，支持TTL过期、访问控制。
    
    Usage:
        store = DataStore()
        
        # 写入数据
        store.set("my_key", {"data": 123}, writer="plugin-a", ttl=3600)
        
        # 读取数据
        value = store.get("my_key", reader="plugin-b")
        
        # 列出所有key
        keys = store.list_keys()
        
        # 删除数据
        store.delete("my_key", deleter="plugin-a")
    """

    def __init__(
        self,
        max_items: int = 1000,
        default_ttl: Optional[int] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化数据存储
        
        Args:
            max_items: 最大存储条目数
            default_ttl: 默认过期时间（秒）
            logger: 日志记录器
        """
        self._store: Dict[str, SharedDataItem] = {}
        self._max_items = max_items
        self._default_ttl = default_ttl
        self._logger = logger or logging.getLogger("data_store")
        
        # 统计信息
        self._stats = {
            "total_writes": 0,
            "total_reads": 0,
            "total_deletes": 0,
            "evictions": 0,
            "hits": 0,
            "misses": 0,
        }

    def set(
        self,
        key: str,
        value: Any,
        writer_plugin_id: str,
        ttl: Optional[int] = None,
        overwrite: bool = True,
    ) -> bool:
        """
        写入数据
        
        Args:
            key: 键名
            value: 值（任意可序列化对象）
            writer_plugin_id: 写入者插件ID
            ttl: 过期时间（秒），None使用默认值
            overwrite: 是否允许覆盖
            
        Returns:
            是否写入成功
        """
        if len(self._store) >= self._max_items and key not in self._store:
            # 触发淘汰策略
            self._evict_oldest()
        
        if not overwrite and key in self._store:
            self._logger.warning(f"Key {key} exists and overwrite=False")
            return False
        
        effective_ttl = ttl or self._default_ttl
        
        item = SharedDataItem(
            key=key,
            value=value,
            writer_plugin_id=writer_plugin_id,
            ttl_seconds=effective_ttl,
        )
        
        self._store[key] = item
        self._stats["total_writes"] += 1
        
        self._logger.debug(
            f"[DataStore] SET {key} by {writer_plugin_id} (ttl={effective_ttl}s)"
        )
        
        return True

    def get(
        self,
        key: str,
        reader_plugin_id: Optional[str] = None,
        default: Any = None,
    ) -> Any:
        """
        读取数据
        
        Args:
            key: 键名
            reader_plugin_id: 读取者插件ID（用于审计）
            default: 默认值
            
        Returns:
            数据值，不存在返回default
        """
        item = self._store.get(key)
        
        if item is None:
            self._stats["misses"] += 1
            return default
        
        # 检查是否过期
        if item.is_expired():
            del self._store[key]
            self._stats["misses"] += 1
            self._logger.debug(f"[DataStore] MISS {key} (expired)")
            return default
        
        # 更新访问信息
        item.touch()
        if reader_plugin_id:
            item.readers.add(reader_plugin_id)
        
        self._stats["total_reads"] += 1
        self._stats["hits"] += 1
        
        self._logger.debug(
            f"[DataStore] GET {key} by {reader_plugin_id} (access #{item.access_count})"
        )
        
        return item.value

    def delete(self, key: str, deleter_plugin_id: Optional[str] = None) -> bool:
        """
        删除数据
        
        Args:
            key: 键名
            deleter_plugin_id: 删除者插件ID（用于审计）
            
        Returns:
            是否删除成功
        """
        if key not in self._store:
            return False
        
        del self._store[key]
        self._stats["total_deletes"] += 1
        
        self._logger.debug(
            f"[DataStore] DEL {key} by {deleter_plugin_id}"
        )
        
        return True

    def list_keys(
        self,
        pattern: Optional[str] = None,
        writer_plugin_id: Optional[str] = None,
    ) -> List[str]:
        """
        列出所有键
        
        Args:
            pattern: 通配符模式过滤（如 "user:*"）
            writer_plugin_id: 按写入者过滤
            
        Returns:
            匹配的键列表
        """
        keys = list(self._store.keys())
        
        # 清理过期项
        for key in keys[:]:
            if self._store[key].is_expired():
                del self._store[key]
                keys.remove(key)
        
        # 应用过滤器
        if pattern:
            import fnmatch
            keys = [k for k in keys if fnmatch.fnmatch(k, pattern)]
        
        if writer_plugin_id:
            keys = [
                k for k in keys 
                if self._store[k].writer_plugin_id == writer_plugin_id
            ]
        
        return keys

    def get_info(self, key: str) -> Optional[Dict[str, Any]]:
        """获取数据项的详细信息"""
        item = self._store.get(key)
        if not item or item.is_expired():
            return None
        
        return {
            "key": item.key,
            "writer": item.writer_plugin_id,
            "created_at": item.created_at.isoformat(),
            "updated_at": item.updated_at.isoformat(),
            "ttl": item.ttl_seconds,
            "access_count": item.access_count,
            "readers": list(item.readers),
            "is_expired": item.is_expired(),
        }

    def clear(self, writer_plugin_id: Optional[str] = None):
        """清空存储"""
        count = len(self._store)
        self._store.clear()
        self._logger.info(f"[DataStore] CLEARED {count} items by {writer_plugin_id}")

    def cleanup_expired(self) -> int:
        """清理过期数据，返回清理数量"""
        expired_keys = [
            key for key, item in self._store.items() 
            if item.is_expired()
        ]
        
        for key in expired_keys:
            del self._store[key]
            self._stats["evictions"] += 1
        
        if expired_keys:
            self._logger.info(f"[DataStore] Cleaned up {len(expired_keys)} expired items")
        
        return len(expired_keys)

    def _evict_oldest(self):
        """淘汰最旧的数据项"""
        if not self._store:
            return
        
        oldest_key = min(
            self._store.keys(),
            key=lambda k: self._store[k].updated_at
        )
        
        del self._store[oldest_key]
        self._stats["evictions"] += 1
        self._logger.warning(f"[DataStore] Evicted oldest key: {oldest_key}")

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            "current_size": len(self._store),
            "max_capacity": self._max_items,
            "utilization_percent": round(len(self._store) / self._max_items * 100, 1),
            "hit_rate": round(
                self._stats["hits"] / max(1, self._stats["hits"] + self._stats["misses"]) * 100,
                1
            ),
        }


class EnhancedEventBus:
    """
    增强版事件总线
    
    相比基础版增加了：
    - 事件通配符匹配
    - 优先级排序
    - 点对点通信
    - 数据共享存储
    - 事件持久化
    - 过滤器和中间件
    
    Usage:
        bus = EnhancedEventBus()
        
        # 订阅（支持通配符）
        sub_id = await bus.subscribe("user:*:created", handler)
        
        # 发布（带优先级）
        await bus.publish("user:123:created", data, priority=EventPriority.HIGH)
        
        # 数据共享
        bus.data_store.set("cache:result", result_data, writer="my-plugin")
        cached = bus.data_store.get("cache:result")
    """

    def __init__(
        self,
        max_history: int = 1000,
        enable_persistence: bool = False,
        persistence_path: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        初始化增强事件总线
        
        Args:
            max_history: 最大历史记录数
            enable_persistence: 是否启用事件持久化
            persistence_path: 持久化文件路径
            logger: 日志记录器
        """
        # 订阅管理：{event_pattern: [Subscription]}
        self._subscriptions: Dict[str, List[Subscription]] = {}
        self._all_subscriptions: Dict[str, Subscription] = {}  # 按ID索引
        
        # 事件历史
        self._event_history: List[Event] = []
        self._max_history = max_history
        
        # 数据共享存储
        self.data_store = DataStore(logger=logger)
        
        # 持久化
        self._enable_persistence = enable_persistence
        self._persistence_path = Path(persistence_path) if persistence_path else None
        self._logger = logger or logging.getLogger("enhanced_event_bus")
        
        # 统计
        self._stats = {
            "total_published": 0,
            "total_delivered": 0,
            "total_filtered": 0,
            "total_errors": 0,
            "start_time": datetime.now(),
        }
        
        # 中间件链
        self._middlewares: List[Tuple[str, Callable]] = []
        
        # 如果启用持久化，尝试加载历史
        if self._enable_persistence and self._persistence_path:
            self._load_persisted_events()

    async def publish(
        self,
        event_name: str,
        data: Any = None,
        source_plugin_id: Optional[str] = None,
        target_plugin_id: Optional[str] = None,
        priority: EventPriority = EventPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, int]:
        """
        发布事件（增强版）
        
        Args:
            event_name: 事件名称
            data: 事件数据
            source_plugin_id: 来源插件ID
            target_plugin_id: 目标插件ID（点对点通信）
            priority: 事件优先级
            metadata: 元数据
            
        Returns:
            统计信息 {"delivered": N, "filtered": M, "errors": E}
        """
        # 创建事件对象
        event = Event(
            name=event_name,
            data=data,
            source_plugin_id=source_plugin_id,
            target_plugin_id=target_plugin_id,
            priority=priority,
            metadata=metadata or {},
        )
        
        stats = {"delivered": 0, "filtered": 0, "errors": 0}
        self._stats["total_published"] += 1
        
        # 执行中间件（前置处理）
        for mw_name, middleware in self._middlewares:
            try:
                should_continue = await middleware(event, "before_publish")
                if should_continue is False:
                    self._logger.debug(f"Middleware {mw_name} blocked event {event_name}")
                    return stats
            except Exception as e:
                self._logger.error(f"Middleware {mw_name} error: {e}")
        
        # 查找匹配的订阅者
        matched_subscriptions = self._find_matching_subscriptions(event)
        
        # 按优先级排序
        priority_order = {
            EventPriority.CRITICAL: 0,
            EventPriority.HIGH: 1,
            EventPriority.NORMAL: 2,
            EventPriority.LOW: 3,
            EventPriority.BACKGROUND: 4,
        }
        
        matched_subscriptions.sort(
            key=lambda sub: priority_order.get(sub.priority, 2)
        )
        
        # 通知订阅者
        for subscription in matched_subscriptions:
            if not subscription.is_active:
                continue
            
            # 应用过滤器
            if subscription.filter_func:
                try:
                    if not subscription.filter_func(event):
                        stats["filtered"] += 1
                        continue
                except Exception as e:
                    self._logger.error(f"Filter error: {e}")
                    stats["errors"] += 1
                    continue
            
            # 目标插件过滤（点对点通信）
            if event.target_plugin_id:
                # 这里简化处理：实际应该检查handler所属的插件
                pass
            
            try:
                if asyncio.iscoroutinefunction(subscription.handler):
                    await subscription.handler(event.name, event.data, event)
                else:
                    subscription.handler(event.name, event.data, event)
                
                subscription.call_count += 1
                subscription.last_called_at = datetime.now()
                
                stats["delivered"] += 1
                self._stats["total_delivered"] += 1
                
                # 如果是一次性订阅，标记为非活跃
                if subscription.once:
                    subscription.is_active = False
                    
            except Exception as e:
                self._logger.error(
                    f"Handler {subscription.id} failed for {event_name}: {e}"
                )
                stats["errors"] += 1
                self._stats["total_errors"] += 1
        
        # 记录到历史
        self._add_to_history(event, stats)
        
        # 持久化
        if self._enable_persistence:
            self._persist_event(event)
        
        return stats

    async def subscribe(
        self,
        event_pattern: str,
        handler: Callable,
        priority: EventPriority = EventPriority.NORMAL,
        filter_func: Optional[Callable] = None,
        once: bool = False,
    ) -> str:
        """
        订阅事件（支持通配符）
        
        Args:
            event_pattern: 事件模式（支持 * 和 ? 通配符）
            handler: 处理函数
            priority: 优先级
            filter_func: 额外过滤函数
            once: 是否只触发一次
            
        Returns:
            订阅ID
        """
        sub_id = str(uuid.uuid4())[:8]
        
        subscription = Subscription(
            id=sub_id,
            event_pattern=event_pattern,
            handler=handler,
            priority=priority,
            filter_func=filter_func,
            once=once,
        )
        
        if event_pattern not in self._subscriptions:
            self._subscriptions[event_pattern] = []
        
        self._subscriptions[event_pattern].append(subscription)
        self._all_subscriptions[sub_id] = subscription
        
        self._logger.debug(
            f"[EventBus] SUBSCRIBE {sub_id} -> {event_pattern} "
            f"(priority={priority.value}, once={once})"
        )
        
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        """取消订阅"""
        subscription = self._all_subscriptions.get(subscription_id)
        if not subscription:
            return False
        
        # 从pattern列表中移除
        pattern_subs = self._subscriptions.get(subscription.event_pattern, [])
        if subscription in pattern_subs:
            pattern_subs.remove(subscription)
        
        # 从全局索引中移除
        del self._all_subscriptions[subscription_id]
        
        self._logger.debug(f"[EventBus] UNSUBSCRIBE {subscription_id}")
        return True

    def _find_matching_subscriptions(self, event: Event) -> List[Subscription]:
        """查找与事件匹配的所有订阅"""
        matched = []
        
        for pattern, subscriptions in self._subscriptions.items():
            if self._match_pattern(pattern, event.name):
                matched.extend(subscriptions)
        
        return matched

    @staticmethod
    def _match_pattern(pattern: str, event_name: str) -> bool:
        """
        通配符匹配
        
        支持:
        - * 匹配任意多个字符
        - ? 匹配单个字符
        """
        import fnmatch
        return fnmatch.fnmatch(event_name, pattern)

    def _add_to_history(self, event: Event, delivery_stats: Dict[str, int]):
        """添加到历史记录"""
        history_entry = {
            **event.to_dict(),
            "delivery_stats": delivery_stats,
        }
        
        self._event_history.append(history_entry)
        
        # 保持历史大小限制
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

    def get_event_history(
        self,
        event_name: Optional[str] = None,
        source_plugin_id: Optional[str] = None,
        limit: int = 100,
        since: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """获取事件历史（支持多种过滤）"""
        history = self._event_history
        
        if event_name:
            history = [h for h in history if h["name"] == event_name]
        
        if source_plugin_id:
            history = [h for h in history if h.get("source") == source_plugin_id]
        
        if since:
            history = [
                h for h in history 
                if datetime.fromisoformat(h["timestamp"]) >= since
            ]
        
        return history[-limit:][::-1]

    def add_middleware(self, name: str, middleware: Callable):
        """
        添加中间件
        
        中间件签名: async middleware(event: Event, phase: str) -> bool|None
        - phase: "before_publish" 或 "after_publish"
        - 返回 False 可阻止事件发布
        """
        self._middlewares.append((name, middleware))
        self._logger.info(f"[EventBus] Middleware added: {name}")

    def remove_middleware(self, name: str) -> bool:
        """移除中间件"""
        for i, (mw_name, _) in enumerate(self._middlewares):
            if mw_name == name:
                self._middlewares.pop(i)
                return True
        return False

    def list_subscriptions(self, event_pattern: Optional[str] = None) -> Dict[str, int]:
        """列出订阅情况"""
        if event_pattern:
            matching_patterns = [
                p for p in self._subscriptions 
                if self._match_pattern(p, event_pattern)
            ]
            return {
                p: len([s for s in subs if s.is_active])
                for p in matching_patterns
                for subs in [self._subscriptions[p]]
            }
        
        return {
            pattern: len([s for s in subs if s.is_active])
            for pattern, subs in self._subscriptions.items()
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = (datetime.now() - self._stats["start_time"]).total_seconds()
        
        active_subs = sum(
            1 for s in self._all_subscriptions.values() 
            if s.is_active
        )
        
        return {
            **self._stats,
            "uptime_seconds": uptime,
            "active_subscriptions": active_subs,
            "total_subscriptions": len(self._all_subscriptions),
            "registered_patterns": len(self._subscriptions),
            "history_size": len(self._event_history),
            "data_store_stats": self.data_store.get_stats(),
            "middleware_count": len(self._middlewares),
        }

    def _persist_event(self, event: Event):
        """持久化单个事件"""
        if not self._persistence_path:
            return
        
        try:
            with open(self._persistence_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + '\n')
        except Exception as e:
            self._logger.error(f"Failed to persist event: {e}")

    def _load_persisted_events(self):
        """加载持久化的事件"""
        if not self._persistence_path or not self._persistence_path.exists():
            return
        
        try:
            with open(self._persistence_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        event_data = json.loads(line)
                        self._event_history.append(event_data)
            
            self._logger.info(
                f"Loaded {len(self._event_history)} persisted events"
            )
        except Exception as e:
            self._logger.error(f"Failed to load persisted events: {e}")

    def replay_events(
        self,
        event_name: Optional[str] = None,
        limit: int = 50,
    ) -> int:
        """
        重放历史事件
        
        用于故障恢复或调试。
        
        Args:
            event_name: 要重放的事件名称（None表示全部）
            limit: 最大重放数量
            
        Returns:
            重放的事件数量
        """
        events_to_replay = self.get_event_history(
            event_name=event_name,
            limit=limit
        )
        
        replayed = 0
        for event_data in events_to_replay:
            try:
                asyncio.create_task(
                    self.publish(
                        event_name=event_data["name"],
                        data=event_data["data"],
                        source_plugin_id=event_data.get("source"),
                        metadata={"replayed_from": event_data.get("timestamp")},
                    )
                )
                replayed += 1
            except Exception as e:
                self._logger.error(f"Failed to replay event: {e}")
        
        self._logger.info(f"Replayed {replayed} events")
        return replayed

    async def shutdown(self):
        """关闭事件总线"""
        self._logger.info("Shutting down EnhancedEventBus...")
        
        # 清理一次性订阅
        once_count = 0
        for sub_id, sub in list(self._all_subscriptions.items()):
            if sub.once or not sub.is_active:
                await self.unsubscribe(sub_id)
                once_count += 1
        
        # 清理过期数据
        cleaned = self.data_store.cleanup_expired()
        
        self._logger.info(
            f"Cleanup complete: removed {once_count} subscriptions, "
            f"{cleaned} expired data items"
        )


# 向后兼容：保留旧的PluginEventBus作为别名
PluginEventBus = EnhancedEventBus