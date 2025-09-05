"""Integration tests for coverage API endpoints."""

import pytest
from httpx import AsyncClient


class TestCoverageAPI:
    """Test suite for coverage API endpoints."""

    @pytest.mark.asyncio
    async def test_get_coverage_basic(self, test_client: AsyncClient, sample_prices):
        """Test basic coverage retrieval."""
        response = await test_client.get("/v1/coverage")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "items" in data
        assert "pagination" in data
        assert "meta" in data
        
        # Verify pagination structure
        pagination = data["pagination"]
        assert "page" in pagination
        assert "page_size" in pagination
        assert "total_items" in pagination
        assert "total_pages" in pagination
        
        # Verify meta structure
        meta = data["meta"]
        assert "query_time_ms" in meta
        assert "cached" in meta
        
        # Should have at least our test symbols
        assert len(data["items"]) >= 2  # AAPL, MSFT have data

    @pytest.mark.asyncio
    async def test_get_coverage_with_pagination(self, test_client: AsyncClient, sample_prices):
        """Test coverage with pagination parameters."""
        response = await test_client.get("/v1/coverage?page=1&page_size=2")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should respect page_size
        assert len(data["items"]) <= 2
        assert data["pagination"]["page"] == 1
        assert data["pagination"]["page_size"] == 2

    @pytest.mark.asyncio
    async def test_get_coverage_with_search(self, test_client: AsyncClient, sample_prices):
        """Test coverage with search query."""
        response = await test_client.get("/v1/coverage?q=AAPL")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should find AAPL
        items = data["items"]
        aapl_found = any(item["symbol"] == "AAPL" for item in items)
        assert aapl_found

    @pytest.mark.asyncio
    async def test_get_coverage_with_has_data_filter(self, test_client: AsyncClient, sample_prices):
        """Test coverage with has_data filter."""
        # Test has_data=true
        response = await test_client.get("/v1/coverage?has_data=true")
        assert response.status_code == 200
        data = response.json()
        
        # All items should have data
        for item in data["items"]:
            assert item["row_count"] > 0

        # Test has_data=false  
        response = await test_client.get("/v1/coverage?has_data=false")
        assert response.status_code == 200
        data = response.json()
        
        # All items should have no data
        for item in data["items"]:
            assert item["row_count"] == 0

    @pytest.mark.asyncio
    async def test_get_coverage_with_sorting(self, test_client: AsyncClient, sample_prices):
        """Test coverage with sorting options."""
        response = await test_client.get("/v1/coverage?sort_by=symbol&order=desc")
        
        assert response.status_code == 200
        data = response.json()
        
        items = data["items"]
        if len(items) >= 2:
            # Should be sorted by symbol descending
            assert items[0]["symbol"] >= items[1]["symbol"]

    @pytest.mark.asyncio
    async def test_get_coverage_invalid_parameters(self, test_client: AsyncClient):
        """Test coverage with invalid parameters."""
        # Invalid page
        response = await test_client.get("/v1/coverage?page=0")
        assert response.status_code == 422
        
        # Invalid page_size
        response = await test_client.get("/v1/coverage?page_size=0")
        assert response.status_code == 422
        
        # Invalid sort_by
        response = await test_client.get("/v1/coverage?sort_by=invalid_field")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_coverage_export_csv(self, test_client: AsyncClient, sample_prices):
        """Test CSV export functionality."""
        response = await test_client.get("/v1/coverage/export")
        
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        
        # Verify CSV content
        csv_content = response.text
        assert len(csv_content) > 0
        
        lines = csv_content.strip().split('\n')
        assert len(lines) >= 2  # Header + at least 1 data row
        
        # Check CSV header
        header = lines[0]
        expected_columns = [
            "symbol", "name", "exchange", "currency", "is_active",
            "data_start", "data_end", "data_days", "row_count", 
            "last_updated", "has_gaps"
        ]
        
        for column in expected_columns:
            assert column in header

    @pytest.mark.asyncio
    async def test_coverage_export_csv_with_filters(self, test_client: AsyncClient, sample_prices):
        """Test CSV export with filters."""
        response = await test_client.get("/v1/coverage/export?q=AAPL&has_data=true")
        
        assert response.status_code == 200
        assert "text/csv" in response.headers.get("content-type", "")
        
        csv_content = response.text
        lines = csv_content.strip().split('\n')
        
        # Should have header + filtered results
        assert len(lines) >= 1  # At least header
        
        # If data exists, verify AAPL is in results
        if len(lines) > 1:
            assert "AAPL" in csv_content

    @pytest.mark.asyncio
    async def test_coverage_performance(self, test_client: AsyncClient, sample_prices):
        """Test coverage API performance."""
        response = await test_client.get("/v1/coverage")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check query time is reasonable (less than 1 second)
        query_time_ms = data["meta"]["query_time_ms"]
        assert query_time_ms < 1000  # Less than 1 second
        
        # Response time should be reasonable
        assert response.elapsed.total_seconds() < 2.0

    @pytest.mark.asyncio
    async def test_coverage_data_integrity(self, test_client: AsyncClient, sample_prices):
        """Test data integrity in coverage responses."""
        response = await test_client.get("/v1/coverage")
        
        assert response.status_code == 200
        data = response.json()
        
        for item in data["items"]:
            # Basic field validation
            assert "symbol" in item
            assert "name" in item
            assert "row_count" in item
            assert "data_days" in item
            
            # Logical consistency
            if item["data_start"] and item["data_end"]:
                assert item["data_start"] <= item["data_end"]
            
            if item["row_count"] > 0:
                assert item["data_start"] is not None
                assert item["data_end"] is not None
                assert item["data_days"] > 0
            else:
                assert item["data_days"] == 0
