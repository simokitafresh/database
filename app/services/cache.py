# app/services/cache.py
from typing import Any, Optional, Dict, Tuple, List
from datetime import datetime, timedelta, timezone
import asyncio
import json
import logging
from threading import RLock

from app.services.redis_utils import get_redis_client

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis-based cache with fallback to in-memory cache."""

    def __init__(self, ttl_seconds: int = 60, max_size: int = 1000):
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._fallback_cache: Dict[str, Tuple[Any, datetime]] = {}
        self._lock = RLock()
        self._redis_available = False
        self._redis_warning_logged = False

    async def _ensure_redis(self) -> bool:
        """Check if Redis is available."""
        if not self._redis_available:
            try:
                client = await get_redis_client()
                if client:
                    await client.ping()
                    self._redis_available = True
                    logger.info("Redis cache initialized")
                else:
                    if not self._redis_warning_logged:
                        logger.warning("Redis unavailable, using in-memory fallback")
                        self._redis_warning_logged = True
            except Exception as e:
                if not self._redis_warning_logged:
                    logger.warning(f"Redis check failed: {e}, using in-memory fallback")
                    self._redis_warning_logged = True
        return self._redis_available

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        if await self._ensure_redis():
            try:
                client = await get_redis_client()
                if client:
                    value = await client.get(key)
                    if value:
                        # Deserialize JSON if it's a complex object
                        try:
                            return json.loads(value)
                        except (json.JSONDecodeError, TypeError):
                            return value
            except Exception as e:
                if not self._redis_warning_logged:
                    logger.warning(f"Redis get failed: {e}, falling back to memory")
                    self._redis_warning_logged = True
                self._redis_available = False

        # Fallback to in-memory cache
        with self._lock:
            if key in self._fallback_cache:
                value, timestamp = self._fallback_cache[key]
                if datetime.now(timezone.utc) - timestamp < timedelta(seconds=self._ttl):
                    return value
                else:
                    del self._fallback_cache[key]
        return None

    async def set(self, key: str, value: Any) -> None:
        """Set value in cache."""
        if await self._ensure_redis():
            try:
                client = await get_redis_client()
                if client:
                    # Serialize complex objects to JSON
                    if isinstance(value, (dict, list, tuple)):
                        serialized_value = json.dumps(value)
                    else:
                        serialized_value = str(value)

                    await client.setex(key, self._ttl, serialized_value)
                    return
            except Exception as e:
                if not self._redis_warning_logged:
                    logger.warning(f"Redis set failed: {e}, falling back to memory")
                    self._redis_warning_logged = True
                self._redis_available = False

        # Fallback to in-memory cache
        with self._lock:
            if len(self._fallback_cache) >= self._max_size:
                oldest_key = min(self._fallback_cache.keys(),
                               key=lambda k: self._fallback_cache[k][1])
                del self._fallback_cache[oldest_key]
            self._fallback_cache[key] = (value, datetime.now(timezone.utc))

    async def delete(self, key: str) -> None:
        """Delete value from cache."""
        if await self._ensure_redis():
            try:
                client = await get_redis_client()
                if client:
                    await client.delete(key)
                    return
            except Exception as e:
                if not self._redis_warning_logged:
                    logger.warning(f"Redis delete failed: {e}")
                    self._redis_warning_logged = True
                self._redis_available = False

        # Fallback to in-memory cache
        with self._lock:
            self._fallback_cache.pop(key, None)

    async def clear(self) -> None:
        """Clear all cache entries."""
        if await self._ensure_redis():
            try:
                client = await get_redis_client()
                if client:
                    await client.flushdb()
                    return
            except Exception as e:
                if not self._redis_warning_logged:
                    logger.warning(f"Redis clear failed: {e}")
                    self._redis_warning_logged = True
                self._redis_available = False

        # Fallback to in-memory cache
        with self._lock:
            self._fallback_cache.clear()

    async def get_multi(self, keys: List[str]) -> Dict[str, Any]:
        """Get multiple values from cache in batch."""
        result = {}

        if await self._ensure_redis():
            try:
                client = await get_redis_client()
                if client:
                    values = await client.mget(keys)
                    for key, value in zip(keys, values):
                        if value:
                            try:
                                result[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                result[key] = value
                    return result
            except Exception as e:
                if not self._redis_warning_logged:
                    logger.warning(f"Redis mget failed: {e}, falling back to memory")
                    self._redis_warning_logged = True
                self._redis_available = False

        # Fallback to individual gets
        for key in keys:
            value = await self.get(key)
            if value is not None:
                result[key] = value

        return result

    async def set_multi(self, key_value_pairs: Dict[str, Any]) -> None:
        """Set multiple values in cache in batch."""
        if await self._ensure_redis():
            try:
                client = await get_redis_client()
                if client:
                    # Prepare pipeline
                    pipeline = client.pipeline()
                    for key, value in key_value_pairs.items():
                        if isinstance(value, (dict, list, tuple)):
                            serialized_value = json.dumps(value)
                        else:
                            serialized_value = str(value)
                        pipeline.setex(key, self._ttl, serialized_value)

                    await pipeline.execute()
                    return
            except Exception as e:
                if not self._redis_warning_logged:
                    logger.warning(f"Redis pipeline set failed: {e}, falling back to memory")
                    self._redis_warning_logged = True
                self._redis_available = False

        # Fallback to individual sets
        for key, value in key_value_pairs.items():
            await self.set(key, value)

    def get_sync(self, key: str) -> Optional[Any]:
        """同期版（デバッグ用）"""
        return asyncio.run(self.get(key))


# シングルトンインスタンス
_cache_instance: Optional[RedisCache] = None


def get_cache() -> RedisCache:
    """Get cache instance with Redis support."""
    global _cache_instance
    if _cache_instance is None:
        from app.core.config import settings
        _cache_instance = RedisCache(
            ttl_seconds=getattr(settings, 'CACHE_TTL_SECONDS', 60),
            max_size=1000
        )
    return _cache_instance