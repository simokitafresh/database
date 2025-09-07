"""Test fixtures for integration tests."""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock

from app.main import app
from app.api.deps import get_session


@pytest_asyncio.fixture
async def test_client():
    """Create test HTTP client without database dependencies."""
    
    # Mock database session to avoid database setup issues
    async def mock_get_session():
        mock_session = AsyncMock()
        yield mock_session
    
    app.dependency_overrides[get_session] = mock_get_session
    
    async with AsyncClient(
        transport=ASGITransport(app=app), 
        base_url="http://test"
    ) as client:
        yield client
    
    # Clean up dependency overrides
    app.dependency_overrides.clear()
