from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    APP_NAME: str = "Stock Price Data API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres?sslmode=disable"
    
    # Database connection pool settings - optimized for Standard plan
    DB_POOL_SIZE: int = 5  # Increased from 2 to 5 for better concurrency
    DB_MAX_OVERFLOW: int = 5  # Increased from 3 to 5
    DB_POOL_PRE_PING: bool = True
    DB_POOL_RECYCLE: int = 900  # 1800から900に変更
    DB_ECHO: bool = False
    
    # API settings
    API_MAX_SYMBOLS: int = 10
    API_MAX_SYMBOLS_LOCAL: int = 100  # DB読み出し専用（新設）
    # Standard plan（1GB RAM）を考慮した上限値
    API_MAX_ROWS: int = 50000
    API_MAX_ROWS_LOCAL: int = 200000  # DB読み出し専用（新設）
    YF_REFETCH_DAYS: int = 7  # Reduced from 30 to minimize unnecessary re-fetching
    YF_REQ_CONCURRENCY: int = 6  # Reduced from 8 for stability (rate limit is the actual bottleneck)
    # Rate limiting settings for Yahoo Finance API
    YF_RATE_LIMIT_REQUESTS_PER_SECOND: float = 2.0  # Token bucket rate
    YF_RATE_LIMIT_BURST_SIZE: int = 10  # Token bucket capacity
    YF_RATE_LIMIT_BACKOFF_MULTIPLIER: float = 2.0  # Exponential backoff multiplier
    YF_RATE_LIMIT_BACKOFF_BASE_DELAY: float = 1.0  # Base delay for backoff
    YF_RATE_LIMIT_MAX_BACKOFF_DELAY: float = 60.0  # Maximum backoff delay
    FETCH_TIMEOUT_SECONDS: int = 30  # 8から30に変更
    FETCH_MAX_RETRIES: int = 3
    FETCH_BACKOFF_MAX_SECONDS: float = 8.0
    CORS_ALLOW_ORIGINS: str = ""
    LOG_LEVEL: str = "INFO"
    
    # Cron Job Settings
    CRON_SECRET_TOKEN: str = ""
    CRON_BATCH_SIZE: int = 50
    CRON_UPDATE_DAYS: int = 7
    CRON_FULL_HISTORY_TIMEOUT: int = 300  # Timeout for full history fetch (seconds), adjust after observing actual times

    # FRED API Settings
    FRED_API_KEY: Optional[str] = None
    
    # Auto-registration settings
    ENABLE_AUTO_REGISTRATION: bool = True
    AUTO_REGISTER_TIMEOUT: int = 15  # Total timeout for registration process
    YF_VALIDATE_TIMEOUT: int = 10    # Timeout for Yahoo Finance validation
    
    # Fetch Job Settings
    FETCH_JOB_MAX_SYMBOLS: int = 100
    FETCH_JOB_MAX_DAYS: int = 3650
    FETCH_JOB_TIMEOUT: int = 3600
    FETCH_WORKER_CONCURRENCY: int = 2
    FETCH_PROGRESS_UPDATE_INTERVAL: int = 5
    FETCH_JOB_CLEANUP_DAYS: int = 30
    FETCH_MAX_CONCURRENT_JOBS: int = 10

    # Cache settings - optimized for daily stock data
    CACHE_TTL_SECONDS: int = 14400  # 4 hours (daily data doesn't change frequently)
    ENABLE_CACHE: bool = True
    PREFETCH_SYMBOLS: str = "TQQQ,TECL,GLD,XLU,^VIX,QQQ,SPY,TMV,TMF,LQD,GDX,QLD,SPXL"
    PREFETCH_INTERVAL_MINUTES: int = 5

    # Redis settings (Standard planで利用可能)
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    REDIS_LOCK_TIMEOUT: int = 30
    REDIS_LOCK_BLOCKING_TIMEOUT: float = 10.0

    # Profiling settings
    ENABLE_PROFILING: bool = False

    # Price adjustment detection settings (TID-ADJ-001)
    ADJUSTMENT_CHECK_ENABLED: bool = True
    ADJUSTMENT_MIN_THRESHOLD_PCT: float = 0.001  # Minimum detection threshold (%)
    ADJUSTMENT_SAMPLE_POINTS: int = 10  # Number of sample points to check
    ADJUSTMENT_MIN_DATA_AGE_DAYS: int = 7  # Only check data older than this (reduced from 60 to catch recent splits)
    ADJUSTMENT_AUTO_FIX: bool = True  # Auto-fix detected issues (False = report only)
    ADJUSTMENT_CHECK_FULL_HISTORY: bool = True  # Check entire history, not just old data

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# Expose a module-level singleton for convenient import across the app.
# Usage: ``from app.core.config import settings``
settings = Settings()


def get_settings() -> Settings:
    """Get the application settings instance.
    
    Returns:
        Settings: The application settings singleton.
    """
    return settings


__all__ = ["Settings", "settings", "get_settings"]
