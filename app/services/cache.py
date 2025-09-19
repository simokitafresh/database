# app/services/cache.py
from typing import Any, Optional, Dict, Tuple
from datetime import datetime, timedelta, timezone
import asyncio
from threading import RLock

class InMemoryCache:
    def __init__(self, ttl_seconds: int = 60, max_size: int = 1000):
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._ttl = ttl_seconds
        self._max_size = max_size
        self._lock = RLock()
    
    async def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                value, timestamp = self._cache[key]
                if datetime.now(timezone.utc) - timestamp < timedelta(seconds=self._ttl):
                    return value
                else:
                    del self._cache[key]
        return None
    
    async def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache.keys(), 
                               key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            self._cache[key] = (value, datetime.now(timezone.utc))
    
    async def clear(self) -> None:
        with self._lock:
            self._cache.clear()
    
    def get_sync(self, key: str) -> Optional[Any]:
        """同期版（デバッグ用）"""
        return asyncio.run(self.get(key))

# シングルトンインスタンス
_cache_instance: Optional[InMemoryCache] = None

def get_cache() -> InMemoryCache:
    global _cache_instance
    if _cache_instance is None:
        from app.core.config import settings
        _cache_instance = InMemoryCache(
            ttl_seconds=settings.CACHE_TTL_SECONDS,
            max_size=1000
        )
    return _cache_instance