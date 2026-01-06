import asyncio
import sys

# Windows環境でpsycopgを使用する場合の設定
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.errors import init_error_handlers
from app.api.v1.health import router as health_router
from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.cors import create_cors_middleware
from app.core.middleware import RequestIDMiddleware
from app.core.logging import logger


@asynccontextmanager
async def lifespan(_: FastAPI):
    """アプリケーションライフサイクル管理"""
    prefetch_service = None
    try:
        # 起動時の処理
        logger.info("Starting application...")
        
        # DB接続のウォームアップ（起動時に接続を確立）
        try:
            from app.api.deps import _sessionmaker_for
            from sqlalchemy import text
            
            SessionLocal = _sessionmaker_for(settings.DATABASE_URL)
            
            # 最大3回リトライしてDB接続を確立
            for attempt in range(3):
                try:
                    async with SessionLocal() as session:
                        await session.execute(text("SELECT 1"))
                        logger.info(f"Database connection established (attempt {attempt + 1})")
                        break
                except Exception as db_err:
                    if attempt < 2:
                        logger.warning(f"DB warmup attempt {attempt + 1} failed: {db_err}, retrying...")
                        await asyncio.sleep(1)
                    else:
                        logger.error(f"DB warmup failed after 3 attempts: {db_err}")
                        # エラーが起きてもアプリは起動させる（ヘルスチェックで検出される）
        except Exception as e:
            logger.warning(f"DB warmup skipped: {e}")
        
        # プリフェッチサービス開始
        # Transaction Pooler（ポート6543）のみNullPool制限があるため軽量版を使用
        # Direct接続やSession Pooler（5432）ではフルプリフェッチ可能
        is_transaction_pooler = "pooler.supabase.com" in settings.DATABASE_URL and ":6543" in settings.DATABASE_URL
        
        if settings.ENABLE_CACHE and not is_transaction_pooler:
            try:
                from app.services.prefetch_service import get_prefetch_service
                prefetch_service = get_prefetch_service()
                await prefetch_service.start()
                logger.info(f"Prefetch service started for {len(prefetch_service.symbols)} symbols")
            except ImportError:
                logger.warning("Prefetch service not found, skipping...")
            except Exception as e:
                logger.error(f"Failed to start prefetch service: {e}")
                # エラーが起きてもアプリは起動させる
        elif is_transaction_pooler and settings.ENABLE_CACHE:
            # Transaction Pooler環境: 起動時1回だけの軽量キャッシュウォーム
            try:
                from app.services.prefetch_service import startup_cache_warm
                symbols_str = settings.PREFETCH_SYMBOLS
                if symbols_str:
                    symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
                    cached = await startup_cache_warm(symbols)
                    logger.info(f"Transaction Pooler startup cache warm completed: {cached} symbols")
                else:
                    logger.info("Transaction Pooler environment: no PREFETCH_SYMBOLS configured")
            except Exception as e:
                logger.warning(f"Startup cache warm failed (non-critical): {e}")
        else:
            logger.info("Prefetch service disabled (ENABLE_CACHE=False)")
        
        yield
        
    finally:
        # シャットダウン時の処理
        logger.info("Shutting down application...")
        
        # プリフェッチサービス停止
        if prefetch_service and settings.ENABLE_CACHE:
            try:
                await prefetch_service.stop()
                logger.info("Prefetch service stopped")
            except Exception as e:
                logger.error(f"Error stopping prefetch service: {e}")


app = FastAPI(lifespan=lifespan)
init_error_handlers(app)

from app.core.logging import configure_logging

# Configure JSON logging to stdout so Render captures application logs
try:
    configure_logging(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
except Exception:
    # Fallback: at least set root level
    try:
        logging.getLogger().setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
    except Exception:
        pass

app.add_middleware(RequestIDMiddleware)
cors = create_cors_middleware(settings)
if cors:
    cls, kwargs = cors
    app.add_middleware(cls, **kwargs)

app.include_router(health_router)
app.include_router(v1_router)


@app.get("/")
async def root() -> dict:
    """Root endpoint useful for platform pings and quick checks."""
    return {"status": "ok", "service": "Stock OHLCV API"}
