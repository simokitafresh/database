"""Basic integration tests for API endpoints."""

import pytest
from httpx import AsyncClient


class TestBasicAPI:
    """Test basic API functionality."""

    @pytest.mark.asyncio
    async def test_openapi_schema(self, test_client: AsyncClient):
        """Test OpenAPI schema is accessible."""
        response = await test_client.get("/openapi.json")
        
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

    @pytest.mark.asyncio
    async def test_coverage_endpoint_exists(self, test_client: AsyncClient):
        """Test coverage endpoint is accessible."""
        response = await test_client.get("/v1/coverage")
        
        # Should not return 404 (endpoint exists)
        assert response.status_code != 404
        # May return 200 (success) or 500 (internal error) depending on mock setup

    @pytest.mark.asyncio
    async def test_prices_endpoint_validation(self, test_client: AsyncClient):
        """Test prices endpoint validation."""
        # Without symbol parameter should return 422
        response = await test_client.get("/v1/prices")
        assert response.status_code == 422
        
        # With symbol should not be 404
        response = await test_client.get("/v1/prices?symbol=AAPL")
        assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_fetch_job_endpoint_validation(self, test_client: AsyncClient):
        """Test fetch job endpoint validation."""
        # Without payload should return 422
        response = await test_client.post("/v1/fetch")
        assert response.status_code == 422
        
        # With invalid payload should return 422
        invalid_payload = {"invalid": "data"}
        response = await test_client.post("/v1/fetch", json=invalid_payload)
        assert response.status_code == 422
