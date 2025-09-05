"""Integration tests for CSV export functionality."""

import pytest
import csv
import io
from httpx import AsyncClient
from datetime import date


class TestCSVExportAPI:
    """Test suite for CSV export functionality."""

    @pytest.mark.asyncio
    async def test_coverage_csv_export_basic(self, test_client: AsyncClient, sample_coverage):
        """Test basic coverage CSV export."""
        response = await test_client.get("/v1/coverage.csv")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert "attachment; filename=" in response.headers["content-disposition"]
        
        # Parse CSV content
        csv_content = response.text
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        
        # Should have data
        assert len(rows) > 0
        
        # Verify CSV headers
        expected_headers = ["symbol", "date", "status", "last_updated"]
        assert all(header in reader.fieldnames for header in expected_headers)
        
        # Verify data structure
        for row in rows:
            assert row["symbol"] in ["AAPL", "MSFT", "GOOGL"]
            assert row["status"] in ["complete", "partial", "missing"]
            assert row["date"]  # Should have date
            
    @pytest.mark.asyncio
    async def test_coverage_csv_export_with_filters(self, test_client: AsyncClient, sample_coverage):
        """Test coverage CSV export with filters."""
        # Test with symbol filter
        response = await test_client.get("/v1/coverage.csv?symbol=AAPL")
        
        assert response.status_code == 200
        csv_content = response.text
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        
        # All rows should be for AAPL
        for row in rows:
            assert row["symbol"] == "AAPL"
            
        # Test with date range filter
        response = await test_client.get("/v1/coverage.csv?date_from=2024-01-01&date_to=2024-01-31")
        
        assert response.status_code == 200
        csv_content = response.text
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        
        # Verify dates are within range
        for row in rows:
            row_date = date.fromisoformat(row["date"])
            assert date(2024, 1, 1) <= row_date <= date(2024, 1, 31)

    @pytest.mark.asyncio
    async def test_coverage_csv_export_sorting(self, test_client: AsyncClient, sample_coverage):
        """Test coverage CSV export with sorting."""
        # Test sorting by symbol
        response = await test_client.get("/v1/coverage.csv?sort_by=symbol&sort_order=asc")
        
        assert response.status_code == 200
        csv_content = response.text
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        
        # Verify sorting
        symbols = [row["symbol"] for row in rows]
        assert symbols == sorted(symbols)

    @pytest.mark.asyncio
    async def test_prices_csv_export_basic(self, test_client: AsyncClient, sample_prices):
        """Test basic prices CSV export."""
        response = await test_client.get("/v1/prices.csv?symbol=AAPL")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        
        # Parse CSV content
        csv_content = response.text
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        
        # Should have data
        assert len(rows) > 0
        
        # Verify CSV headers
        expected_headers = ["symbol", "date", "open", "high", "low", "close", "volume", "adjusted_close"]
        assert all(header in reader.fieldnames for header in expected_headers)
        
        # Verify data structure
        for row in rows:
            assert row["symbol"] == "AAPL"
            assert float(row["open"]) > 0
            assert float(row["high"]) > 0
            assert float(row["low"]) > 0
            assert float(row["close"]) > 0
            assert int(row["volume"]) >= 0

    @pytest.mark.asyncio
    async def test_prices_csv_export_with_date_range(self, test_client: AsyncClient, sample_prices):
        """Test prices CSV export with date range."""
        response = await test_client.get("/v1/prices.csv?symbol=AAPL&date_from=2024-01-01&date_to=2024-01-15")
        
        assert response.status_code == 200
        csv_content = response.text
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        
        # Verify dates are within range
        for row in rows:
            row_date = date.fromisoformat(row["date"])
            assert date(2024, 1, 1) <= row_date <= date(2024, 1, 15)

    @pytest.mark.asyncio
    async def test_metrics_csv_export_basic(self, test_client: AsyncClient, sample_prices):
        """Test basic metrics CSV export."""
        response = await test_client.get("/v1/metrics.csv?symbol=AAPL")
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        
        # Parse CSV content
        csv_content = response.text
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        
        # Should have data
        assert len(rows) > 0
        
        # Verify CSV headers
        expected_headers = ["symbol", "date", "avg_price", "price_volatility", "volume_sma", "price_change"]
        assert all(header in reader.fieldnames for header in expected_headers)
        
        # Verify data structure
        for row in rows:
            assert row["symbol"] == "AAPL"
            assert float(row["avg_price"]) > 0
            assert float(row["price_volatility"]) >= 0

    @pytest.mark.asyncio
    async def test_csv_export_large_dataset(self, test_client: AsyncClient, sample_coverage):
        """Test CSV export with large dataset."""
        # Request all data without filters
        response = await test_client.get("/v1/coverage.csv")
        
        assert response.status_code == 200
        
        # Should handle large responses efficiently
        csv_content = response.text
        assert len(csv_content) > 0
        
        # Parse to verify structure
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        
        # Should have reasonable amount of data
        assert len(rows) >= 10  # At least some test data

    @pytest.mark.asyncio
    async def test_csv_export_empty_result(self, test_client: AsyncClient):
        """Test CSV export with empty result set."""
        # Filter that should return no results
        response = await test_client.get("/v1/coverage.csv?symbol=NONEXISTENT")
        
        assert response.status_code == 200
        
        # Should still have headers
        csv_content = response.text
        lines = csv_content.strip().split('\n')
        
        # Should have header line but no data
        assert len(lines) >= 1  # At least header
        
        # Parse to verify headers exist
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        assert len(rows) == 0  # No data rows

    @pytest.mark.asyncio
    async def test_csv_export_encoding(self, test_client: AsyncClient, sample_coverage):
        """Test CSV export encoding and special characters."""
        response = await test_client.get("/v1/coverage.csv")
        
        assert response.status_code == 200
        assert "charset=utf-8" in response.headers["content-type"]
        
        # Content should be properly encoded
        csv_content = response.text
        assert isinstance(csv_content, str)
        
        # Should be parseable as CSV
        reader = csv.DictReader(io.StringIO(csv_content))
        rows = list(reader)
        assert len(rows) > 0

    @pytest.mark.asyncio
    async def test_csv_export_filename_headers(self, test_client: AsyncClient, sample_coverage):
        """Test CSV export filename headers."""
        # Coverage export
        response = await test_client.get("/v1/coverage.csv")
        assert response.status_code == 200
        
        disposition = response.headers["content-disposition"]
        assert "attachment; filename=" in disposition
        assert "coverage" in disposition.lower()
        assert ".csv" in disposition
        
        # Prices export
        response = await test_client.get("/v1/prices.csv?symbol=AAPL")
        assert response.status_code == 200
        
        disposition = response.headers["content-disposition"]
        assert "attachment; filename=" in disposition
        assert "prices" in disposition.lower()
        assert ".csv" in disposition

    @pytest.mark.asyncio
    async def test_csv_export_validation_errors(self, test_client: AsyncClient):
        """Test CSV export with validation errors."""
        # Invalid date format
        response = await test_client.get("/v1/coverage.csv?date_from=invalid-date")
        assert response.status_code == 422
        
        # Invalid sort order
        response = await test_client.get("/v1/coverage.csv?sort_order=invalid")
        assert response.status_code == 422
        
        # Missing symbol for prices
        response = await test_client.get("/v1/prices.csv")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_csv_export_performance(self, test_client: AsyncClient, sample_coverage):
        """Test CSV export performance."""
        from datetime import datetime
        
        start_time = datetime.utcnow()
        response = await test_client.get("/v1/coverage.csv")
        end_time = datetime.utcnow()
        
        assert response.status_code == 200
        
        # Should complete reasonably quickly
        duration = (end_time - start_time).total_seconds()
        assert duration < 5.0  # Less than 5 seconds

    @pytest.mark.asyncio
    async def test_csv_content_integrity(self, test_client: AsyncClient, sample_prices):
        """Test CSV content integrity and data accuracy."""
        # Get JSON data first
        json_response = await test_client.get("/v1/prices?symbol=AAPL&limit=10")
        assert json_response.status_code == 200
        json_data = json_response.json()["prices"]
        
        # Get CSV data
        csv_response = await test_client.get("/v1/prices.csv?symbol=AAPL&limit=10")
        assert csv_response.status_code == 200
        
        # Parse CSV
        csv_content = csv_response.text
        reader = csv.DictReader(io.StringIO(csv_content))
        csv_data = list(reader)
        
        # Should have same number of records
        assert len(csv_data) == len(json_data)
        
        # Verify data matches (sample check)
        if len(json_data) > 0 and len(csv_data) > 0:
            json_first = json_data[0]
            csv_first = csv_data[0]
            
            # Compare key fields
            assert json_first["symbol"] == csv_first["symbol"]
            assert json_first["date"] == csv_first["date"]
            assert abs(float(json_first["close"]) - float(csv_first["close"])) < 0.01
