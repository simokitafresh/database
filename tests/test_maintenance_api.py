"""Integration tests for maintenance API endpoints (TID-ADJ-015)."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
def mock_settings_enabled():
    """Settings with adjustment check enabled."""
    with patch("app.api.v1.maintenance.settings") as mock:
        mock.ADJUSTMENT_CHECK_ENABLED = True
        mock.ADJUSTMENT_AUTO_FIX = True
        mock.ADJUSTMENT_MIN_THRESHOLD_PCT = 0.5
        mock.ADJUSTMENT_SAMPLE_POINTS = 5
        yield mock


@pytest.fixture
def mock_settings_disabled():
    """Settings with adjustment check disabled."""
    with patch("app.api.v1.maintenance.settings") as mock:
        mock.ADJUSTMENT_CHECK_ENABLED = False
        mock.ADJUSTMENT_AUTO_FIX = False
        yield mock


@pytest.fixture
def mock_settings_no_auto_fix():
    """Settings with auto-fix disabled."""
    with patch("app.api.v1.maintenance.settings") as mock:
        mock.ADJUSTMENT_CHECK_ENABLED = True
        mock.ADJUSTMENT_AUTO_FIX = False
        yield mock


@pytest.fixture
def sample_scan_result_dict():
    """Sample scan result dict from service."""
    return {
        "scan_timestamp": "2024-01-15T10:00:00",
        "total_symbols": 1,
        "scanned": 1,
        "needs_refresh": [
            {
                "symbol": "AAPL",
                "needs_refresh": True,
                "events": [
                    {
                        "symbol": "AAPL",
                        "event_type": "stock_split",
                        "severity": "critical",
                        "pct_difference": 50.0,
                        "check_date": "2024-01-15",
                        "db_price": 100.0,
                        "yf_adjusted_price": 50.0,
                        "details": {"ratio": 2.0},
                        "recommendation": "Immediate data refresh required",
                    }
                ],
                "max_pct_diff": 50.0,
                "error": None,
            }
        ],
        "no_change": [],
        "errors": [],
        "fixed": [],
        "summary": {
            "by_type": {"stock_split": 1},
            "by_severity": {"critical": 1},
        },
    }


@pytest.fixture
def sample_scan_result_clean():
    """Sample scan result with no adjustments."""
    return {
        "scan_timestamp": "2024-01-15T10:00:00",
        "total_symbols": 1,
        "scanned": 1,
        "needs_refresh": [],
        "no_change": ["MSFT"],
        "errors": [],
        "fixed": [],
        "summary": {"by_type": {}, "by_severity": {}},
    }


class TestCheckAdjustmentsEndpoint:
    """Tests for POST /v1/maintenance/check-adjustments."""
    
    @pytest.mark.asyncio
    async def test_check_adjustments_disabled(self, mock_settings_disabled):
        """Returns 503 when adjustment check is disabled."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/maintenance/check-adjustments",
                json={}
            )
            assert response.status_code == 503
    
    @pytest.mark.asyncio
    async def test_check_adjustments_success(
        self, mock_settings_enabled, sample_scan_result_dict
    ):
        """Returns scan results when check succeeds."""
        with patch(
            "app.api.v1.maintenance.PrecisionAdjustmentDetector"
        ) as MockDetector:
            mock_instance = MagicMock()
            mock_instance.scan_all_symbols = AsyncMock(
                return_value=sample_scan_result_dict
            )
            MockDetector.return_value = mock_instance
            
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/maintenance/check-adjustments",
                    json={"symbols": ["AAPL"]}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["total_symbols"] == 1
                assert data["scanned"] == 1
                assert len(data["needs_refresh"]) == 1
                assert data["needs_refresh"][0]["symbol"] == "AAPL"
    
    @pytest.mark.asyncio
    async def test_check_adjustments_no_issues(
        self, mock_settings_enabled, sample_scan_result_clean
    ):
        """Returns empty needs_refresh list when no adjustments found."""
        with patch(
            "app.api.v1.maintenance.PrecisionAdjustmentDetector"
        ) as MockDetector:
            mock_instance = MagicMock()
            mock_instance.scan_all_symbols = AsyncMock(
                return_value=sample_scan_result_clean
            )
            MockDetector.return_value = mock_instance
            
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/maintenance/check-adjustments",
                    json={"symbols": ["MSFT"]}
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["scanned"] == 1
                assert len(data["needs_refresh"]) == 0
                assert "MSFT" in data["no_change"]
    
    @pytest.mark.asyncio
    async def test_check_adjustments_scan_error(self, mock_settings_enabled):
        """Returns 500 when scan fails."""
        with patch(
            "app.api.v1.maintenance.PrecisionAdjustmentDetector"
        ) as MockDetector:
            mock_instance = MagicMock()
            mock_instance.scan_all_symbols = AsyncMock(
                side_effect=Exception("DB error")
            )
            MockDetector.return_value = mock_instance
            
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/maintenance/check-adjustments",
                    json={}
                )
                
                assert response.status_code == 500


class TestAdjustmentReportEndpoint:
    """Tests for GET /v1/maintenance/adjustment-report."""
    
    @pytest.mark.asyncio
    async def test_report_disabled(self, mock_settings_disabled):
        """Returns 503 when adjustment check is disabled."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/v1/maintenance/adjustment-report")
            assert response.status_code == 503
    
    @pytest.mark.asyncio
    async def test_report_empty(self, mock_settings_enabled):
        """Returns empty report when no scans have been done."""
        with patch(
            "app.api.v1.maintenance._last_scan_result", None
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/v1/maintenance/adjustment-report")
                
                assert response.status_code == 200
                data = response.json()
                assert data["total_symbols"] == 0
                assert data["needs_refresh"] == []
                assert data["available"] is False
    
    @pytest.mark.asyncio
    async def test_report_with_cached_results(
        self, mock_settings_enabled, sample_scan_result_dict
    ):
        """Returns cached scan results in report."""
        with patch(
            "app.api.v1.maintenance._last_scan_result",
            sample_scan_result_dict
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get("/v1/maintenance/adjustment-report")
                
                assert response.status_code == 200
                data = response.json()
                assert data["needs_refresh_count"] == 1
                assert len(data["needs_refresh"]) == 1
                assert data["needs_refresh"][0]["symbol"] == "AAPL"
                assert data["available"] is True
    
    @pytest.mark.asyncio
    async def test_report_filter_by_symbol(self, mock_settings_enabled):
        """Filters report by symbol."""
        cached_results = {
            "scan_timestamp": "2024-01-15T10:00:00",
            "total_symbols": 2,
            "scanned": 2,
            "needs_refresh": [
                {
                    "symbol": "AAPL",
                    "needs_refresh": True,
                    "events": [
                        {
                            "symbol": "AAPL",
                            "event_type": "stock_split",
                            "severity": "critical",
                            "pct_difference": 50.0,
                            "check_date": "2024-01-15",
                            "db_price": 100.0,
                            "yf_adjusted_price": 50.0,
                        }
                    ],
                    "max_pct_diff": 50.0,
                },
                {
                    "symbol": "MSFT",
                    "needs_refresh": True,
                    "events": [
                        {
                            "symbol": "MSFT",
                            "event_type": "dividend",
                            "severity": "normal",
                            "pct_difference": 1.0,
                            "check_date": "2024-01-10",
                            "db_price": 200.0,
                            "yf_adjusted_price": 198.0,
                        }
                    ],
                    "max_pct_diff": 1.0,
                },
            ],
            "no_change": [],
            "errors": [],
            "summary": {"by_type": {}, "by_severity": {}},
        }
        
        with patch(
            "app.api.v1.maintenance._last_scan_result",
            cached_results
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.get(
                    "/v1/maintenance/adjustment-report?symbols=AAPL"
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["needs_refresh_count"] == 1
                assert data["needs_refresh"][0]["symbol"] == "AAPL"


class TestFixAdjustmentsEndpoint:
    """Tests for POST /v1/maintenance/fix-adjustments."""
    
    @pytest.mark.asyncio
    async def test_fix_disabled(self, mock_settings_disabled):
        """Returns 503 when adjustment check is disabled."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/maintenance/fix-adjustments",
                json={"confirm": True}
            )
            assert response.status_code == 503
    
    @pytest.mark.asyncio
    async def test_fix_auto_fix_disabled(self, mock_settings_no_auto_fix):
        """Returns 403 when auto-fix is disabled."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/maintenance/fix-adjustments",
                json={"confirm": True}
            )
            assert response.status_code == 403
    
    @pytest.mark.asyncio
    async def test_fix_requires_confirmation(self, mock_settings_enabled):
        """Returns 400 when confirmation is not provided."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/maintenance/fix-adjustments",
                json={"confirm": False}
            )
            assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_fix_no_symbols(self, mock_settings_enabled):
        """Returns 400 when no symbols to fix."""
        with patch("app.api.v1.maintenance._last_scan_result", None):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/maintenance/fix-adjustments",
                    json={"confirm": True}
                )
                assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_fix_success(self, mock_settings_enabled, sample_scan_result_dict):
        """Successfully fixes symbols."""
        with patch(
            "app.api.v1.maintenance._last_scan_result",
            sample_scan_result_dict
        ):
            with patch(
                "app.api.v1.maintenance.PrecisionAdjustmentDetector"
            ) as MockDetector:
                mock_instance = MagicMock()
                mock_instance.auto_fix_symbol = AsyncMock(return_value={
                    "symbol": "AAPL",
                    "deleted_rows": 100,
                    "job_created": True,
                    "job_id": "123",
                    "error": None,
                    "timestamp": "2024-01-15T10:00:00",
                })
                MockDetector.return_value = mock_instance
                
                async with AsyncClient(
                    transport=ASGITransport(app=app),
                    base_url="http://test"
                ) as client:
                    response = await client.post(
                        "/v1/maintenance/fix-adjustments",
                        json={"confirm": True}
                    )
                    
                    assert response.status_code == 200
                    data = response.json()
                    assert data["total_requested"] == 1
                    assert len(data["fixed"]) == 1
                    assert data["fixed"][0]["symbol"] == "AAPL"
                    assert data["fixed"][0]["job_created"] is True
    
    @pytest.mark.asyncio
    async def test_fix_specific_symbols(self, mock_settings_enabled):
        """Fixes only specified symbols."""
        with patch(
            "app.api.v1.maintenance.PrecisionAdjustmentDetector"
        ) as MockDetector:
            mock_instance = MagicMock()
            mock_instance.auto_fix_symbol = AsyncMock(return_value={
                "symbol": "MSFT",
                "deleted_rows": 50,
                "job_created": True,
                "job_id": "456",
                "error": None,
                "timestamp": "2024-01-15T10:00:00",
            })
            MockDetector.return_value = mock_instance
            
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test"
            ) as client:
                response = await client.post(
                    "/v1/maintenance/fix-adjustments",
                    json={
                        "symbols": ["MSFT"],
                        "confirm": True
                    }
                )
                
                assert response.status_code == 200
                data = response.json()
                assert data["total_requested"] == 1
                assert data["fixed"][0]["symbol"] == "MSFT"


class TestMaintenanceRouterRegistration:
    """Tests for router registration."""
    
    @pytest.mark.asyncio
    async def test_maintenance_endpoints_registered(self, mock_settings_disabled):
        """Verifies maintenance endpoints are accessible."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            # Just check that routes exist (will get 503 if disabled)
            # but not 404 which would mean routes aren't registered
            response = await client.post("/v1/maintenance/check-adjustments", json={})
            assert response.status_code != 404
            
            response = await client.get("/v1/maintenance/adjustment-report")
            assert response.status_code != 404
            
            response = await client.post(
                "/v1/maintenance/fix-adjustments", 
                json={"confirm": True}
            )
            assert response.status_code != 404
