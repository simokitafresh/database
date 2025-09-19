# app/api/v1/debug.py
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from app.core.config import settings
from app.api.deps import get_settings

router = APIRouter()

@router.get("/debug/cache-stats")
async def get_cache_stats(settings=Depends(get_settings)):
    """キャッシュ統計情報（開発環境のみ）"""
    if settings.APP_ENV not in ["development", "staging"]:
        raise HTTPException(status_code=404)
    
    from app.services.cache import get_cache
    cache = get_cache()
    
    with cache._lock:
        total_items = len(cache._cache)
        items_info = []
        for key, (value, timestamp) in list(cache._cache.items())[:10]:
            items_info.append({
                "key": key,
                "age_seconds": (datetime.now(timezone.utc) - timestamp).total_seconds(),
                "size_bytes": len(str(value))
            })
    
    return {
        "total_items": total_items,
        "max_size": cache._max_size,
        "ttl_seconds": cache._ttl,
        "sample_items": items_info
    }