"""Redis 缓存层。

提供统一的缓存接口，支持：
- 工作流状态缓存
- SSE 事件缓冲
- API 限流
- 用户会话缓存
- 搜索结果缓存
"""

from app.cache.redis import get_redis, redis_client, RedisClient

__all__ = ["get_redis", "redis_client", "RedisClient"]