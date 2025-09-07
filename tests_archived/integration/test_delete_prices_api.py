"""Integration tests for DELETE /v1/prices/{symbol} endpoint."""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock

from app.main import app
from app.api.deps import get_session


class TestDeletePricesAPI:
    """Test suite for DELETE /v1/prices/{symbol} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_prices_success(self, test_client: AsyncClient):
        """Test successful price deletion with confirm=true."""
        # Mock the database session and query execution
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 100  # Simulate 100 rows deleted
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        # Apply dependency override
        app.dependency_overrides[get_session] = override_session
        try:
            response = await test_client.delete("/v1/prices/AAPL?confirm=true")

            assert response.status_code == 200
            data = response.json()
            assert "deleted_rows" in data
            assert "date_range" in data
            assert data["deleted_rows"] == 100
            assert data["symbol"] == "AAPL"
        finally:
            app.dependency_overrides.pop(get_session, None)

    @pytest.mark.asyncio
    async def test_delete_prices_with_date_range(self, test_client: AsyncClient):
        """Test price deletion with date range."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 50
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_session
        try:
            response = await test_client.delete(
                "/v1/prices/MSFT?confirm=true&date_from=2024-01-01&date_to=2024-01-31"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["deleted_rows"] == 50
            assert data["symbol"] == "MSFT"
            assert "date_range" in data
        finally:
            app.dependency_overrides.pop(get_session, None)

    @pytest.mark.asyncio
    async def test_delete_prices_without_confirm(self, test_client: AsyncClient):
        """Test price deletion without confirm parameter."""
        response = await test_client.delete("/v1/prices/AAPL")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "confirm" in data["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_prices_confirm_false(self, test_client: AsyncClient):
        """Test price deletion with confirm=false."""
        response = await test_client.delete("/v1/prices/AAPL?confirm=false")

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "confirm" in data["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_prices_invalid_date_range(self, test_client: AsyncClient):
        """Test price deletion with invalid date range."""
        response = await test_client.delete(
            "/v1/prices/AAPL?confirm=true&date_from=2024-01-31&date_to=2024-01-01"
        )

        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "date" in data["error"]["message"].lower()

    @pytest.mark.asyncio
    async def test_delete_prices_database_error(self, test_client: AsyncClient):
        """Test price deletion with database error."""
        # Mock the database session to raise an exception
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Database connection failed")

        async def override_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_session
        try:
            response = await test_client.delete("/v1/prices/AAPL?confirm=true")

            assert response.status_code == 500
            data = response.json()
            assert "error" in data
        finally:
            app.dependency_overrides.pop(get_session, None)

    @pytest.mark.asyncio
    async def test_delete_prices_nonexistent_symbol(self, test_client: AsyncClient):
        """Test price deletion for non-existent symbol."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.rowcount = 0  # No rows deleted
        mock_session.execute.return_value = mock_result

        async def override_session():
            yield mock_session

        app.dependency_overrides[get_session] = override_session
        try:
            response = await test_client.delete("/v1/prices/NONEXISTENT?confirm=true")

            assert response.status_code == 200
            data = response.json()
            assert data["deleted_rows"] == 0
            assert data["symbol"] == "NONEXISTENT"
        finally:
            app.dependency_overrides.pop(get_session, None)