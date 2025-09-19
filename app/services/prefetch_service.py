# app/services/prefetch_service.py
import asyncio
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
import logging

from app.core.config import settings
from app.services.cache import get_cache
from app.services.fetcher import fetch_prices_batch
from app.db.engine import create_engine_and_sessionmaker
from app.db.queries import ensure_coverage_parallel

logger = logging.getLogger(__name__)

class PrefetchService:
    def __init__(self):
        self.symbols = self._parse_symbols()
        self.cache = get_cache()
        self.running = False
        self._task: Optional[asyncio.Task] = None
    
    def _parse_symbols(self) -> List[str]:
        """環境変数から銘柄リストを取得"""
        symbols_str = settings.PREFETCH_SYMBOLS
        if not symbols_str:
            return []
        return [s.strip() for s in symbols_str.split(",") if s.strip()]
    
    async def start(self):
        """プリフェッチサービス開始"""
        if self.running:
            return
        
        self.running = True
        logger.info(f"Starting prefetch for {len(self.symbols)} symbols")
        
        # 初回取得
        await self._prefetch_all()
        
        # 定期更新タスク開始
        self._task = asyncio.create_task(self._periodic_update())
    
    async def stop(self):
        """プリフェッチサービス停止"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
    
    async def _prefetch_all(self):
        """全銘柄をプリフェッチ"""
        if not self.symbols:
            return
        
        try:
            # 独立したDBセッションを作成
            _, SessionLocal = create_engine_and_sessionmaker(
                database_url=settings.DATABASE_URL,
                pool_size=2
            )
            
            async with SessionLocal() as session:
                # 最新30日分のデータを確保
                today = date.today()
                from_date = today - timedelta(days=30)
                
                # 並行取得
                await ensure_coverage_parallel(
                    session, self.symbols, from_date, today,
                    settings.YF_REFETCH_DAYS
                )
                
                # キャッシュに保存
                for symbol in self.symbols:
                    cache_key = f"prefetch:{symbol}:{from_date}:{today}"
                    await self.cache.set(cache_key, True)
                
            logger.info(f"Prefetched {len(self.symbols)} symbols")
            
        except Exception as e:
            logger.error(f"Prefetch failed: {e}")
    
    async def _periodic_update(self):
        """定期的な更新"""
        interval = settings.PREFETCH_INTERVAL_MINUTES * 60
        
        while self.running:
            try:
                await asyncio.sleep(interval)
                await self._prefetch_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic update failed: {e}")

# シングルトンインスタンス
_prefetch_service: Optional[PrefetchService] = None

def get_prefetch_service() -> PrefetchService:
    global _prefetch_service
    if _prefetch_service is None:
        _prefetch_service = PrefetchService()
    return _prefetch_service