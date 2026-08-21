"""Redis 客户端封装。

基于 redis[hiredis] 的异步客户端，提供：
- 连接池管理（自动复用连接）
- 优雅降级（Redis 不可用时自动 fallback 到内存缓存）
- 通用缓存操作（get / set / delete / expire）
- Hash / List / Set 操作
- 分布式锁
- 健康检查
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.config import get_settings

logger = logging.getLogger(__name__)

_REDIS_AVAILABLE = False
try:
    import redis.asyncio as aioredis
    _REDIS_AVAILABLE = True
except ImportError:
    aioredis = None  # type: ignore[assignment]


class InMemoryFallback:
    """Redis 不可用时的内存降级缓存。

    单进程内有效，不支持分布式，仅作为兜底方案。
    自动过期：每次 get 时检查 TTL，过期则删除。
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[Any, float]] = {}

    async def get(self, key: str) -> str | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expires_at = entry
        if expires_at > 0 and time.time() > expires_at:
            del self._store[key]
            return None
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value)

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        expires_at = (time.time() + ex) if ex else 0
        self._store[key] = (value, expires_at)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        v = await self.get(key)
        return v is not None

    async def expire(self, key: str, seconds: int) -> None:
        entry = self._store.get(key)
        if entry is not None:
            value, _ = entry
            self._store[key] = (value, time.time() + seconds)

    async def ttl(self, key: str) -> int:
        entry = self._store.get(key)
        if entry is None:
            return -2
        _, expires_at = entry
        if expires_at == 0:
            return -1
        remaining = int(expires_at - time.time())
        if remaining <= 0:
            del self._store[key]
            return -2
        return remaining

    async def hset(self, name: str, key: str, value: Any) -> None:
        full_key = f"{name}::{key}"
        await self.set(full_key, value)

    async def hget(self, name: str, key: str) -> str | None:
        full_key = f"{name}::{key}"
        return await self.get(full_key)

    async def hgetall(self, name: str) -> dict[str, str]:
        prefix = f"{name}::"
        result: dict[str, str] = {}
        now = time.time()
        expired_keys: list[str] = []
        for k, (v, expires_at) in self._store.items():
            if k.startswith(prefix):
                if expires_at > 0 and now > expires_at:
                    expired_keys.append(k)
                    continue
                field = k[len(prefix):]
                result[field] = v.decode("utf-8") if isinstance(v, bytes) else str(v)
        for k in expired_keys:
            del self._store[k]
        return result

    async def hdel(self, name: str, key: str) -> None:
        full_key = f"{name}::{key}"
        await self.delete(full_key)

    async def lpush(self, name: str, *values: Any) -> None:
        for v in values:
            list_key = f"__list__{name}"
            entry = self._store.get(list_key)
            if entry is None:
                self._store[list_key] = ([v], 0)
            else:
                lst, exp = entry
                lst.insert(0, v)
                self._store[list_key] = (lst, exp)

    async def lrange(self, name: str, start: int, end: int) -> list[str]:
        list_key = f"__list__{name}"
        entry = self._store.get(list_key)
        if entry is None:
            return []
        lst, _ = entry
        if end == -1:
            end = len(lst)
        sliced = lst[start:end]
        return [v.decode("utf-8") if isinstance(v, bytes) else str(v) for v in sliced]

    async def ltrim(self, name: str, start: int, end: int) -> None:
        list_key = f"__list__{name}"
        entry = self._store.get(list_key)
        if entry is not None:
            lst, exp = entry
            if end == -1:
                end = len(lst)
            self._store[list_key] = (lst[start:end], exp)

    async def llen(self, name: str) -> int:
        list_key = f"__list__{name}"
        entry = self._store.get(list_key)
        if entry is None:
            return 0
        lst, _ = entry
        return len(lst)

    async def sadd(self, name: str, *values: Any) -> None:
        set_key = f"__set__{name}"
        entry = self._store.get(set_key)
        if entry is None:
            self._store[set_key] = (set(values), 0)
        else:
            s, exp = entry
            s.update(values)
            self._store[set_key] = (s, exp)

    async def smembers(self, name: str) -> set[str]:
        set_key = f"__set__{name}"
        entry = self._store.get(set_key)
        if entry is None:
            return set()
        s, _ = entry
        return {v.decode("utf-8") if isinstance(v, bytes) else str(v) for v in s}

    async def srem(self, name: str, *values: Any) -> None:
        set_key = f"__set__{name}"
        entry = self._store.get(set_key)
        if entry is not None:
            s, exp = entry
            for v in values:
                s.discard(v)
            self._store[set_key] = (s, exp)

    async def incr(self, key: str) -> int:
        entry = self._store.get(key)
        if entry is None:
            self._store[key] = (1, 0)
            return 1
        val, exp = entry
        new_val = int(val) + 1
        self._store[key] = (new_val, exp)
        return new_val

    async def incrby(self, key: str, amount: int) -> int:
        entry = self._store.get(key)
        if entry is None:
            self._store[key] = (amount, 0)
            return amount
        val, exp = entry
        new_val = int(val) + amount
        self._store[key] = (new_val, exp)
        return new_val

    async def ping(self) -> bool:
        return True

    async def close(self) -> None:
        self._store.clear()


class RedisClient:
    """统一 Redis 客户端，封装常用操作。

    Redis 可用时使用真 Redis；不可用时自动降级到 InMemoryFallback。
    所有方法均返回与 redis.asyncio 一致的类型签名。
    """

    def __init__(self) -> None:
        self._client: aioredis.Redis | None = None
        self._fallback = InMemoryFallback()
        self._use_fallback = True
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and not self._use_fallback

    @property
    def using_fallback(self) -> bool:
        return self._use_fallback

    async def connect(self) -> None:
        """初始化 Redis 连接池。"""
        if not _REDIS_AVAILABLE:
            logger.warning("redis package not installed, using in-memory fallback")
            self._use_fallback = True
            return

        settings = get_settings()
        url = settings.redis_url

        if not url:
            logger.info("REDIS_URL not configured, using in-memory fallback")
            self._use_fallback = True
            return

        try:
            self._client = aioredis.from_url(
                url,
                password=settings.redis_password or None,
                db=settings.redis_db,
                decode_responses=True,
                max_connections=settings.redis_pool_size,
                socket_timeout=5,
                socket_connect_timeout=3,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            await self._client.ping()
            self._connected = True
            self._use_fallback = False
            logger.info(f"Redis connected: {url.split('@')[-1] if '@' in url else url}")
        except Exception as e:
            logger.warning(f"Redis connection failed ({e}), using in-memory fallback")
            self._use_fallback = True
            self._connected = False

    async def close(self) -> None:
        """关闭连接。"""
        if self._client:
            await self._client.close()
            self._client = None
        await self._fallback.close()
        self._connected = False

    def _backend(self) -> aioredis.Redis | InMemoryFallback:
        if self._use_fallback or self._client is None:
            return self._fallback
        return self._client

    # ===== 基础操作 =====

    async def get(self, key: str) -> str | None:
        return await self._backend().get(key)

    async def get_json(self, key: str) -> Any:
        """获取并反序列化 JSON。"""
        raw = await self.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def set(self, key: str, value: Any, ex: int | None = None) -> None:
        await self._backend().set(key, value, ex=ex)

    async def set_json(self, key: str, value: Any, ex: int | None = None) -> None:
        """序列化为 JSON 后存储。"""
        await self.set(key, json.dumps(value, ensure_ascii=False), ex=ex)

    async def delete(self, *keys: str) -> None:
        backend = self._backend()
        for key in keys:
            await backend.delete(key)

    async def exists(self, key: str) -> bool:
        return await self._backend().exists(key)

    async def expire(self, key: str, seconds: int) -> None:
        await self._backend().expire(key, seconds)

    async def ttl(self, key: str) -> int:
        return await self._backend().ttl(key)

    # ===== Hash 操作 =====

    async def hset(self, name: str, key: str, value: Any) -> None:
        await self._backend().hset(name, key, value)

    async def hget(self, name: str, key: str) -> str | None:
        return await self._backend().hget(name, key)

    async def hgetall(self, name: str) -> dict[str, str]:
        return await self._backend().hgetall(name)

    async def hdel(self, name: str, key: str) -> None:
        await self._backend().hdel(name, key)

    # ===== List 操作 =====

    async def lpush(self, name: str, *values: Any) -> None:
        await self._backend().lpush(name, *values)

    async def lrange(self, name: str, start: int, end: int) -> list[str]:
        return await self._backend().lrange(name, start, end)

    async def ltrim(self, name: str, start: int, end: int) -> None:
        await self._backend().ltrim(name, start, end)

    async def llen(self, name: str) -> int:
        return await self._backend().llen(name)

    # ===== Set 操作 =====

    async def sadd(self, name: str, *values: Any) -> None:
        await self._backend().sadd(name, *values)

    async def smembers(self, name: str) -> set[str]:
        return await self._backend().smembers(name)

    async def srem(self, name: str, *values: Any) -> None:
        await self._backend().srem(name, *values)

    # ===== 计数器 =====

    async def incr(self, key: str) -> int:
        return await self._backend().incr(key)

    async def incrby(self, key: str, amount: int) -> int:
        return await self._backend().incrby(key, amount)

    # ===== 分布式锁 =====

    async def acquire_lock(
        self,
        name: str,
        timeout: int = 30,
        retry_interval: float = 0.1,
        retry_times: int = 300,
    ) -> bool:
        """获取分布式锁。

        Args:
            name: 锁名称
            timeout: 锁超时秒数（防止死锁）
            retry_interval: 重试间隔秒
            retry_times: 最大重试次数

        Returns:
            是否成功获取锁
        """
        if self._use_fallback:
            return True

        identifier = str(time.time())
        for _ in range(retry_times):
            acquired = await self._client.set(name, identifier, nx=True, ex=timeout)
            if acquired:
                return True
            import asyncio
            await asyncio.sleep(retry_interval)
        return False

    async def release_lock(self, name: str) -> None:
        """释放分布式锁。"""
        if self._use_fallback:
            return
        await self._client.delete(name)

    # ===== 健康检查 =====

    async def ping(self) -> bool:
        try:
            return await self._backend().ping()
        except Exception:
            return False


redis_client = RedisClient()


async def get_redis() -> RedisClient:
    """FastAPI 依赖注入：获取 Redis 客户端。"""
    return redis_client