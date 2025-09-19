# tests/unit/test_cache.py
import pytest
import asyncio
from datetime import datetime, timedelta
from app.services.cache import InMemoryCache

@pytest.mark.asyncio
async def test_cache_basic():
    cache = InMemoryCache(ttl_seconds=1)
    
    # Set and get
    await cache.set("key1", "value1")
    assert await cache.get("key1") == "value1"
    
    # TTL expiration
    await asyncio.sleep(1.1)
    assert await cache.get("key1") is None

@pytest.mark.asyncio
async def test_cache_max_size():
    cache = InMemoryCache(ttl_seconds=60, max_size=2)
    
    await cache.set("key1", "value1")
    await cache.set("key2", "value2")
    await cache.set("key3", "value3")  # key1 should be evicted
    
    assert await cache.get("key1") is None
    assert await cache.get("key2") == "value2"
    assert await cache.get("key3") == "value3"