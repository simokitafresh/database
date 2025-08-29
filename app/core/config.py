from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    APP_ENV: str = "development"
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/app"
    API_MAX_SYMBOLS: int = 5
    API_MAX_ROWS: int = 10000
    YF_REFETCH_DAYS: int = 30
    YF_REQ_CONCURRENCY: int = 4
    FETCH_TIMEOUT_SECONDS: int = 8
    REQUEST_TIMEOUT_SECONDS: int = 15
    CORS_ALLOW_ORIGINS: str = ""
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


# Expose a module-level singleton for convenient import across the app.
# Usage: ``from app.core.config import settings``
settings = Settings()


__all__ = ["Settings", "settings"]
