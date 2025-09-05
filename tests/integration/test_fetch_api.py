"""Integration tests for fetch job API endpoints."""

import pytest
import asyncio
from httpx import AsyncClient
from datetime import date, datetime


class TestFetchJobAPI:
    """Test suite for fetch job API endpoints."""

    @pytest.mark.asyncio
    async def test_create_fetch_job_basic(self, test_client: AsyncClient, sample_symbols):
        """Test basic job creation."""
        payload = {
            "symbols": ["AAPL"],
            "date_from": "2024-01-01",
            "date_to": "2024-01-31",
            "interval": "1d",
            "force": False,
            "priority": "normal"
        }
        
        response = await test_client.post("/v1/fetch", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "job_id" in data
        assert "status" in data
        assert "message" in data
        assert "symbols_count" in data
        assert "date_range" in data
        
        # Verify job details
        assert data["status"] == "pending"
        assert data["symbols_count"] == 1
        assert data["date_range"]["from"] == "2024-01-01"
        assert data["date_range"]["to"] == "2024-01-31"
        
        return data["job_id"]

    @pytest.mark.asyncio
    async def test_create_fetch_job_multiple_symbols(self, test_client: AsyncClient, sample_symbols):
        """Test job creation with multiple symbols."""
        payload = {
            "symbols": ["AAPL", "MSFT", "GOOGL"],
            "date_from": "2024-01-01", 
            "date_to": "2024-01-31"
        }
        
        response = await test_client.post("/v1/fetch", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["symbols_count"] == 3
        return data["job_id"]

    @pytest.mark.asyncio
    async def test_get_job_status(self, test_client: AsyncClient, sample_symbols):
        """Test job status retrieval."""
        # First create a job
        payload = {
            "symbols": ["AAPL"],
            "date_from": "2024-01-01",
            "date_to": "2024-01-31"
        }
        
        create_response = await test_client.post("/v1/fetch", json=payload)
        assert create_response.status_code == 200
        job_id = create_response.json()["job_id"]
        
        # Get job status
        status_response = await test_client.get(f"/v1/fetch/{job_id}")
        
        assert status_response.status_code == 200
        data = status_response.json()
        
        # Verify response structure
        assert "job_id" in data
        assert "status" in data
        assert "symbols" in data
        assert "date_from" in data
        assert "date_to" in data
        assert "interval" in data
        assert "force" in data
        assert "priority" in data
        assert "created_at" in data
        
        # Verify job details
        assert data["job_id"] == job_id
        assert data["status"] in ["pending", "processing", "completed", "failed", "cancelled"]
        assert data["symbols"] == ["AAPL"]

    @pytest.mark.asyncio
    async def test_get_job_status_not_found(self, test_client: AsyncClient):
        """Test job status for non-existent job."""
        response = await test_client.get("/v1/fetch/non-existent-job-id")
        
        assert response.status_code == 404
        data = response.json()
        assert "error" in data or "detail" in data

    @pytest.mark.asyncio
    async def test_list_jobs(self, test_client: AsyncClient, sample_symbols):
        """Test job listing."""
        # Create a few jobs
        payloads = [
            {"symbols": ["AAPL"], "date_from": "2024-01-01", "date_to": "2024-01-31"},
            {"symbols": ["MSFT"], "date_from": "2024-01-01", "date_to": "2024-01-31"}
        ]
        
        job_ids = []
        for payload in payloads:
            response = await test_client.post("/v1/fetch", json=payload)
            assert response.status_code == 200
            job_ids.append(response.json()["job_id"])
        
        # List jobs
        response = await test_client.get("/v1/fetch")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "jobs" in data
        assert "total" in data
        
        # Should have our created jobs
        assert len(data["jobs"]) >= 2
        assert data["total"] >= 2
        
        # Verify job structure
        for job in data["jobs"]:
            assert "job_id" in job
            assert "status" in job
            assert "symbols" in job
            assert "created_at" in job

    @pytest.mark.asyncio
    async def test_list_jobs_with_filters(self, test_client: AsyncClient, sample_symbols):
        """Test job listing with filters."""
        # Create a job
        payload = {"symbols": ["AAPL"], "date_from": "2024-01-01", "date_to": "2024-01-31"}
        response = await test_client.post("/v1/fetch", json=payload)
        assert response.status_code == 200
        
        # List with status filter
        response = await test_client.get("/v1/fetch?status=pending")
        assert response.status_code == 200
        
        data = response.json()
        # All jobs should be pending
        for job in data["jobs"]:
            assert job["status"] == "pending"

    @pytest.mark.asyncio
    async def test_cancel_job(self, test_client: AsyncClient, sample_symbols):
        """Test job cancellation."""
        # Create a job
        payload = {"symbols": ["AAPL"], "date_from": "2024-01-01", "date_to": "2024-01-31"}
        response = await test_client.post("/v1/fetch", json=payload)
        assert response.status_code == 200
        job_id = response.json()["job_id"]
        
        # Cancel the job
        cancel_response = await test_client.post(f"/v1/fetch/{job_id}/cancel")
        
        assert cancel_response.status_code == 200
        data = cancel_response.json()
        
        # Verify cancellation response
        assert "success" in data
        assert "message" in data
        assert "job_id" in data
        assert "cancelled_at" in data
        
        assert data["success"] is True
        assert data["job_id"] == job_id
        
        # Verify job status changed to cancelled
        status_response = await test_client.get(f"/v1/fetch/{job_id}")
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["status"] == "cancelled"

    @pytest.mark.asyncio
    async def test_cancel_non_existent_job(self, test_client: AsyncClient):
        """Test cancellation of non-existent job."""
        response = await test_client.post("/v1/fetch/non-existent-job/cancel")
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_job_validation_errors(self, test_client: AsyncClient):
        """Test job creation with validation errors."""
        # Empty symbols
        payload = {"symbols": [], "date_from": "2024-01-01", "date_to": "2024-01-31"}
        response = await test_client.post("/v1/fetch", json=payload)
        assert response.status_code == 422
        
        # Invalid date range
        payload = {"symbols": ["AAPL"], "date_from": "2024-01-31", "date_to": "2024-01-01"}
        response = await test_client.post("/v1/fetch", json=payload)
        assert response.status_code == 422
        
        # Future date
        future_date = (date.today().replace(year=date.today().year + 1)).isoformat()
        payload = {"symbols": ["AAPL"], "date_from": "2024-01-01", "date_to": future_date}
        response = await test_client.post("/v1/fetch", json=payload)
        assert response.status_code == 422
        
        # Too many symbols
        many_symbols = [f"SYM{i}" for i in range(101)]  # 101 symbols
        payload = {"symbols": many_symbols, "date_from": "2024-01-01", "date_to": "2024-01-31"}
        response = await test_client.post("/v1/fetch", json=payload)
        assert response.status_code == 422
        
        # Invalid interval
        payload = {"symbols": ["AAPL"], "date_from": "2024-01-01", "date_to": "2024-01-31", "interval": "invalid"}
        response = await test_client.post("/v1/fetch", json=payload)
        assert response.status_code == 422
        
        # Invalid priority
        payload = {"symbols": ["AAPL"], "date_from": "2024-01-01", "date_to": "2024-01-31", "priority": "invalid"}
        response = await test_client.post("/v1/fetch", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_job_creation_performance(self, test_client: AsyncClient, sample_symbols):
        """Test job creation performance."""
        payload = {"symbols": ["AAPL"], "date_from": "2024-01-01", "date_to": "2024-01-31"}
        
        start_time = datetime.utcnow()
        response = await test_client.post("/v1/fetch", json=payload)
        end_time = datetime.utcnow()
        
        assert response.status_code == 200
        
        # Job creation should be fast
        duration = (end_time - start_time).total_seconds()
        assert duration < 1.0  # Less than 1 second

    @pytest.mark.asyncio
    async def test_concurrent_job_creation(self, test_client: AsyncClient, sample_symbols):
        """Test concurrent job creation."""
        payloads = [
            {"symbols": ["AAPL"], "date_from": "2024-01-01", "date_to": "2024-01-31"},
            {"symbols": ["MSFT"], "date_from": "2024-01-01", "date_to": "2024-01-31"},
            {"symbols": ["GOOGL"], "date_from": "2024-01-01", "date_to": "2024-01-31"}
        ]
        
        # Create jobs concurrently
        tasks = []
        for payload in payloads:
            task = test_client.post("/v1/fetch", json=payload)
            tasks.append(task)
        
        responses = await asyncio.gather(*tasks)
        
        # All should succeed
        for response in responses:
            assert response.status_code == 200
            data = response.json()
            assert "job_id" in data
        
        # All job IDs should be unique
        job_ids = [response.json()["job_id"] for response in responses]
        assert len(job_ids) == len(set(job_ids))  # All unique
