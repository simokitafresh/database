"""Tests for cron adjustment check integration (TID-ADJ-016~018)."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from app.main import app


# Correct mock path - the import is at function level, so we mock the original module
DETECTOR_MOCK_PATH = "app.services.adjustment_detector.PrecisionAdjustmentDetector"


@pytest.fixture
def mock_cron_token():
    """Mock cron token verification."""
    with patch("app.api.v1.cron.settings") as mock_settings:
        mock_settings.CRON_SECRET_TOKEN = "test-token"
        mock_settings.CRON_BATCH_SIZE = 10
        mock_settings.CRON_UPDATE_DAYS = 30
        mock_settings.YF_REFETCH_DAYS = 7
        mock_settings.ADJUSTMENT_CHECK_ENABLED = True
        mock_settings.ADJUSTMENT_AUTO_FIX = True
        yield mock_settings


class TestAdjustmentCheckEndpoint:
    """Tests for POST /v1/adjustment-check."""
    
    @pytest.mark.asyncio
    async def test_adjustment_check_disabled(self):
        """Returns skipped when adjustment check is disabled."""
        with patch("app.api.v1.cron.settings") as mock_settings:
            mock_settings.CRON_SECRET_TOKEN = "test"
            mock_settings.ADJUSTMENT_CHECK_ENABLED = False
            
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/adjustment-check",
                    headers={"X-Cron-Secret": "test"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "skipped"
                assert "disabled" in data["message"]
    
    @pytest.mark.asyncio
    async def test_adjustment_check_success(self, mock_cron_token):
        """Returns scan results when check succeeds."""
        sample_result = {
            "scan_timestamp": "2024-01-15T10:00:00",
            "total_symbols": 10,
            "scanned": 10,
            "needs_refresh": [
                {"symbol": "AAPL", "needs_refresh": True, "events": [], "max_pct_diff": 50.0}
            ],
            "no_change": ["MSFT", "GOOG"],
            "errors": [],
            "fixed": [],
            "summary": {"by_type": {"stock_split": 1}, "by_severity": {"critical": 1}},
        }
        
        with patch(DETECTOR_MOCK_PATH) as MockDetector:
            mock_instance = MagicMock()
            mock_instance.scan_all_symbols = AsyncMock(return_value=sample_result)
            MockDetector.return_value = mock_instance
            
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/adjustment-check",
                    headers={"X-Cron-Secret": "test-token"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "success"
                assert data["scanned"] == 10
                assert data["needs_refresh_count"] == 1
                assert "AAPL" in data["affected_symbols"]
    
    @pytest.mark.asyncio
    async def test_adjustment_check_with_auto_fix(self, mock_cron_token):
        """Includes fix results when auto_fix is true."""
        sample_result = {
            "scan_timestamp": "2024-01-15T10:00:00",
            "total_symbols": 5,
            "scanned": 5,
            "needs_refresh": [{"symbol": "AAPL", "needs_refresh": True, "events": []}],
            "no_change": [],
            "errors": [],
            "fixed": [{"symbol": "AAPL", "deleted_rows": 100, "job_id": "123"}],
            "summary": {"by_type": {}, "by_severity": {}},
        }
        
        with patch(DETECTOR_MOCK_PATH) as MockDetector:
            mock_instance = MagicMock()
            mock_instance.scan_all_symbols = AsyncMock(return_value=sample_result)
            MockDetector.return_value = mock_instance
            
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/adjustment-check?auto_fix=true",
                    headers={"X-Cron-Secret": "test-token"}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert "fixed_count" in data
                assert data["fixed_count"] == 1
                assert "AAPL" in data["fixed_symbols"]
    
    @pytest.mark.asyncio
    async def test_adjustment_check_auth_required(self):
        """Returns 401 when no auth token provided."""
        with patch("app.api.v1.cron.settings") as mock_settings:
            mock_settings.CRON_SECRET_TOKEN = "required-token"
            
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post("/v1/adjustment-check")
                assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_adjustment_check_invalid_token(self):
        """Returns 403 when invalid token provided."""
        with patch("app.api.v1.cron.settings") as mock_settings:
            mock_settings.CRON_SECRET_TOKEN = "correct-token"
            
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/adjustment-check",
                    headers={"X-Cron-Secret": "wrong-token"}
                )
                assert response.status_code == 403


class TestDailyUpdateWithAdjustmentCheck:
    """Tests for adjustment check integration in daily-update."""
    
    @pytest.mark.asyncio
    async def test_daily_update_schema_includes_adjustment_fields(self):
        """Verifies schema includes new adjustment check fields."""
        from app.schemas.cron import CronDailyUpdateRequest, CronDailyUpdateResponse
        
        # Request has new fields
        request = CronDailyUpdateRequest(
            dry_run=True,
            check_adjustments=True,
            auto_fix_adjustments=True,
        )
        assert request.check_adjustments is True
        assert request.auto_fix_adjustments is True
        
        # Response has new field
        response = CronDailyUpdateResponse(
            status="success",
            message="Test",
            total_symbols=10,
            batch_count=1,
            date_range={"from": "2024-01-01", "to": "2024-01-31"},
            timestamp="2024-01-15T10:00:00",
            adjustment_check={"scanned": 10, "needs_refresh_count": 1},
        )
        assert response.adjustment_check is not None
        assert response.adjustment_check["scanned"] == 10


class TestCronAdjustmentCheckLogging:
    """Tests for logging in adjustment check (TID-ADJ-018)."""
    
    @pytest.mark.asyncio
    async def test_logs_adjustment_check_start(self, mock_cron_token):
        """Verifies logging at start of adjustment check."""
        with patch("app.api.v1.cron.logger") as mock_logger:
            with patch(DETECTOR_MOCK_PATH) as MockDetector:
                mock_instance = MagicMock()
                mock_instance.scan_all_symbols = AsyncMock(return_value={
                    "scan_timestamp": "2024-01-15T10:00:00",
                    "total_symbols": 0,
                    "scanned": 0,
                    "needs_refresh": [],
                    "no_change": [],
                    "errors": [],
                    "summary": {"by_type": {}, "by_severity": {}},
                })
                MockDetector.return_value = mock_instance
                
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    await client.post(
                        "/v1/adjustment-check",
                        headers={"X-Cron-Secret": "test-token"}
                    )
                    
                    # Verify logging was called
                    mock_logger.info.assert_called()
    
    @pytest.mark.asyncio
    async def test_logs_adjustment_check_error(self, mock_cron_token):
        """Verifies logging when adjustment check fails."""
        with patch("app.api.v1.cron.logger") as mock_logger:
            with patch(DETECTOR_MOCK_PATH) as MockDetector:
                mock_instance = MagicMock()
                mock_instance.scan_all_symbols = AsyncMock(
                    side_effect=Exception("Test error")
                )
                MockDetector.return_value = mock_instance
                
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/v1/adjustment-check",
                        headers={"X-Cron-Secret": "test-token"}
                    )
                    
                    assert response.status_code == 500
                    mock_logger.exception.assert_called()
