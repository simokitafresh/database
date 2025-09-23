import asyncio
import sys
import asyncio

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
        
        # プリフェッチサービス開始（ENABLE_CACHEがTrueで、Supabase環境でない場合のみ）
        # SupabaseのNullPool環境では並行処理が許可されていないため無効化
        is_supabase = "supabase.com" in settings.DATABASE_URL
        if settings.ENABLE_CACHE and not is_supabase:
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
        elif is_supabase:
            logger.info("Prefetch service disabled for Supabase environment (NullPool)")
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
