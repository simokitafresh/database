from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    APP_NAME: str = "Stock Price Data API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/postgres?sslmode=disable"
    
    # Database connection pool settings
    DB_POOL_SIZE: int = 5  # Reduced for cloud deployment
    DB_MAX_OVERFLOW: int = 5  # Reduced for cloud deployment 
    DB_POOL_PRE_PING: bool = True
    DB_POOL_RECYCLE: int = 1800  # 30 minutes for cloud stability
    DB_ECHO: bool = False
    
    # API settings
    API_MAX_SYMBOLS: int = 5
    API_MAX_ROWS: int = 10000
    YF_REFETCH_DAYS: int = 7  # Reduced from 30 to minimize unnecessary re-fetching
    YF_REQ_CONCURRENCY: int = 4
    FETCH_TIMEOUT_SECONDS: int = 8
    FETCH_MAX_RETRIES: int = 3
    FETCH_BACKOFF_MAX_SECONDS: float = 8.0
    REQUEST_TIMEOUT_SECONDS: int = 15
    CORS_ALLOW_ORIGINS: str = ""
    LOG_LEVEL: str = "INFO"
    
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
