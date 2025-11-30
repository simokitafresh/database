"""Unit tests for maintenance schemas (TID-ADJ-010)."""

import pytest

from app.schemas.maintenance import (
    AdjustmentCheckRequest,
    AdjustmentCheckResponse,
    AdjustmentEventResponse,
    AdjustmentFixRequest,
    AdjustmentFixResponse,
    AdjustmentReportResponse,
    FixResultItem,
    ScanResultResponse,
)


class TestAdjustmentCheckRequest:
    """Tests for AdjustmentCheckRequest schema."""
    
    def test_default_values(self):
        """Tests default values are set correctly."""
        request = AdjustmentCheckRequest()
        assert request.symbols is None
        assert request.auto_fix is False
        assert request.threshold_pct == 0.001
        assert request.sample_points == 10
    
    def test_with_symbols(self):
        """Tests with specified symbols."""
        request = AdjustmentCheckRequest(
            symbols=["AAPL", "MSFT"],
            auto_fix=True,
            threshold_pct=1.0,
            sample_points=5,
        )
        assert request.symbols == ["AAPL", "MSFT"]
        assert request.auto_fix is True
        assert request.threshold_pct == 1.0
        assert request.sample_points == 5
    
    def test_threshold_validation(self):
        """Tests threshold_pct validation."""
        # Negative threshold should fail
        with pytest.raises(ValueError):
            AdjustmentCheckRequest(threshold_pct=-1.0)
    
    def test_sample_points_validation(self):
        """Tests sample_points validation."""
        # Below minimum
        with pytest.raises(ValueError):
            AdjustmentCheckRequest(sample_points=1)
        # Above maximum
        with pytest.raises(ValueError):
            AdjustmentCheckRequest(sample_points=100)


class TestAdjustmentEventResponse:
    """Tests for AdjustmentEventResponse schema."""
    
    def test_event_schema(self):
        """Tests event schema with all fields."""
        event = AdjustmentEventResponse(
            symbol="AAPL",
            event_type="stock_split",
            severity="critical",
            pct_difference=50.0,
            check_date="2024-01-15",
            db_price=100.0,
            yf_adjusted_price=50.0,
            details={"ratio": 2.0},
            recommendation="Immediate refresh required",
        )
        assert event.symbol == "AAPL"
        assert event.event_type == "stock_split"
        assert event.severity == "critical"
        assert event.pct_difference == 50.0
        assert event.check_date == "2024-01-15"
        assert event.db_price == 100.0
        assert event.yf_adjusted_price == 50.0
        assert event.details == {"ratio": 2.0}
        assert event.recommendation == "Immediate refresh required"
    
    def test_defaults(self):
        """Tests default values."""
        event = AdjustmentEventResponse(
            symbol="AAPL",
            event_type="dividend",
            severity="normal",
            pct_difference=1.0,
            check_date="2024-01-15",
            db_price=100.0,
            yf_adjusted_price=99.0,
        )
        assert event.details == {}
        assert event.recommendation == ""


class TestScanResultResponse:
    """Tests for ScanResultResponse schema."""
    
    def test_scan_result_defaults(self):
        """Tests default values."""
        result = ScanResultResponse(symbol="AAPL", needs_refresh=False)
        assert result.symbol == "AAPL"
        assert result.needs_refresh is False
        assert result.events == []
        assert result.max_pct_diff == 0.0
        assert result.error is None
    
    def test_scan_result_with_events(self):
        """Tests with events."""
        event = AdjustmentEventResponse(
            symbol="AAPL",
            event_type="stock_split",
            severity="critical",
            pct_difference=50.0,
            check_date="2024-01-15",
            db_price=100.0,
            yf_adjusted_price=50.0,
        )
        result = ScanResultResponse(
            symbol="AAPL",
            needs_refresh=True,
            events=[event],
            max_pct_diff=50.0,
        )
        assert result.needs_refresh is True
        assert len(result.events) == 1
        assert result.max_pct_diff == 50.0


class TestAdjustmentCheckResponse:
    """Tests for AdjustmentCheckResponse schema."""
    
    def test_check_response(self):
        """Tests check response schema."""
        response = AdjustmentCheckResponse(
            scan_timestamp="2024-01-15T10:00:00",
            total_symbols=10,
            scanned=10,
            needs_refresh=[],
            no_change=["MSFT"],
            errors=[],
            fixed=[],
            summary={"by_type": {}, "by_severity": {}},
        )
        assert response.scan_timestamp == "2024-01-15T10:00:00"
        assert response.total_symbols == 10
        assert response.scanned == 10
        assert response.needs_refresh == []
        assert response.no_change == ["MSFT"]
        assert response.errors == []


class TestAdjustmentFixRequest:
    """Tests for AdjustmentFixRequest schema."""
    
    def test_requires_confirm(self):
        """Tests confirm defaults to False."""
        request = AdjustmentFixRequest()
        assert request.confirm is False
        assert request.symbols is None
    
    def test_with_confirm(self):
        """Tests with confirm=True."""
        request = AdjustmentFixRequest(
            symbols=["AAPL"],
            confirm=True,
        )
        assert request.confirm is True
        assert request.symbols == ["AAPL"]


class TestFixResultItem:
    """Tests for FixResultItem schema."""
    
    def test_fix_result_item(self):
        """Tests fix result item schema."""
        item = FixResultItem(
            symbol="AAPL",
            deleted_rows=100,
            job_created=True,
            job_id="123",
            error=None,
            timestamp="2024-01-15T10:00:00",
        )
        assert item.symbol == "AAPL"
        assert item.deleted_rows == 100
        assert item.job_created is True
        assert item.job_id == "123"
        assert item.error is None
        assert item.timestamp == "2024-01-15T10:00:00"


class TestAdjustmentFixResponse:
    """Tests for AdjustmentFixResponse schema."""
    
    def test_fix_response(self):
        """Tests fix response schema."""
        response = AdjustmentFixResponse(
            total_requested=2,
            fixed=[],
            errors=[],
            summary={"requested": 2, "success": 2, "failed": 0},
        )
        assert response.total_requested == 2
        assert response.fixed == []
        assert response.errors == []
        assert response.summary["success"] == 2


class TestAdjustmentReportResponse:
    """Tests for AdjustmentReportResponse schema."""
    
    def test_report_response_empty(self):
        """Tests empty report response."""
        response = AdjustmentReportResponse()
        assert response.last_scan_timestamp is None
        assert response.total_symbols == 0
        assert response.needs_refresh_count == 0
        assert response.needs_refresh == []
        assert response.summary == {}
        assert response.available is True
    
    def test_report_response_with_data(self):
        """Tests report response with data."""
        response = AdjustmentReportResponse(
            last_scan_timestamp="2024-01-15T10:00:00",
            total_symbols=10,
            needs_refresh_count=2,
            needs_refresh=[
                ScanResultResponse(symbol="AAPL", needs_refresh=True),
            ],
            summary={"by_type": {"stock_split": 1}},
            available=True,
        )
        assert response.last_scan_timestamp == "2024-01-15T10:00:00"
        assert response.total_symbols == 10
        assert response.needs_refresh_count == 2
        assert len(response.needs_refresh) == 1
