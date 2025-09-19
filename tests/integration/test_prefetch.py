# tests/integration/test_prefetch.py
import pytest
import asyncio
from app.services.prefetch_service import PrefetchService
from app.services.cache import InMemoryCache

@pytest.mark.asyncio
async def test_prefetch_service():
    # テスト用設定
    service = PrefetchService()
    service.symbols = ["AAPL", "MSFT"]  # テスト用に2銘柄のみ
    
    # プリフェッチ実行
    await service._prefetch_all()
    
    # キャッシュ確認
    cache = service.cache
    from datetime import date, timedelta
    today = date.today()
    from_date = today - timedelta(days=30)
    
    for symbol in service.symbols:
        cache_key = f"prefetch:{symbol}:{from_date}:{today}"
        assert await cache.get(cache_key) is not None