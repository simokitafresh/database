import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock
from fastapi import FastAPI

from app.core.config import settings
from app.main import app as fastapi_application


class DummyAsyncSession:
    """Simple async session stub for dependency overrides in tests."""

    def __init__(self) -> None:
        self.execute = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.connection = AsyncMock()

    def in_transaction(self) -> bool:
        return False


@pytest.fixture
def fastapi_app() -> FastAPI:
    """FastAPI application instance with cache disabled for tests."""
    original_enable_cache = settings.ENABLE_CACHE
    settings.ENABLE_CACHE = False
    try:
        yield fastapi_application
    finally:
        fastapi_application.dependency_overrides.clear()
        settings.ENABLE_CACHE = original_enable_cache


@pytest.fixture
async def async_client(fastapi_app: FastAPI) -> AsyncClient:
    """HTTP client for async API tests."""
    async with AsyncClient(app=fastapi_app, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def dummy_session() -> DummyAsyncSession:
    """Factory for a stub AsyncSession replacement."""
    return DummyAsyncSession()
