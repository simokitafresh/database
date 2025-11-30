"""Tests for adjustment detector service."""

import pytest
from app.services.adjustment_detector import (
    AdjustmentType,
    AdjustmentSeverity,
    DetectionThresholds,
    AdjustmentEvent,
    ScanResult,
    PrecisionAdjustmentDetector,
)


class TestEnumsAndDataclasses:
    """Tests for TID-ADJ-002: Basic class and Enum definitions."""

    def test_adjustment_type_values(self):
        """Test AdjustmentType enum has all expected values."""
        assert AdjustmentType.STOCK_SPLIT.value == "stock_split"
        assert AdjustmentType.REVERSE_SPLIT.value == "reverse_split"
        assert AdjustmentType.DIVIDEND.value == "dividend"
        assert AdjustmentType.SPECIAL_DIVIDEND.value == "special_dividend"
        assert AdjustmentType.CAPITAL_GAIN.value == "capital_gain"
        assert AdjustmentType.SPINOFF.value == "spinoff"
        assert AdjustmentType.UNKNOWN.value == "unknown"
        
        # Verify total count
        assert len(AdjustmentType) == 7

    def test_adjustment_severity_values(self):
        """Test AdjustmentSeverity enum has all expected values."""
        assert AdjustmentSeverity.CRITICAL.value == "critical"
        assert AdjustmentSeverity.HIGH.value == "high"
        assert AdjustmentSeverity.NORMAL.value == "normal"
        assert AdjustmentSeverity.LOW.value == "low"
        
        # Verify total count
        assert len(AdjustmentSeverity) == 4

    def test_detection_thresholds_defaults(self):
        """Test DetectionThresholds default values."""
        thresholds = DetectionThresholds()
        
        assert thresholds.float_noise_pct == 0.0001
        assert thresholds.min_detection_pct == 0.001
        assert thresholds.split_threshold_pct == 10.0
        assert thresholds.special_div_threshold_pct == 2.0
        assert thresholds.spinoff_threshold_pct == 15.0
        assert thresholds.sample_points == 10
        assert thresholds.min_data_age_days == 7  # Reduced from 60 to catch recent splits
        assert thresholds.check_full_history is True  # New setting

    def test_detection_thresholds_custom(self):
        """Test DetectionThresholds with custom values."""
        thresholds = DetectionThresholds(
            float_noise_pct=0.001,
            min_detection_pct=0.01,
            split_threshold_pct=20.0,
            special_div_threshold_pct=5.0,
            spinoff_threshold_pct=25.0,
            sample_points=15,
            min_data_age_days=90,
            check_full_history=False,
        )
        
        assert thresholds.float_noise_pct == 0.001
        assert thresholds.min_detection_pct == 0.01
        assert thresholds.split_threshold_pct == 20.0
        assert thresholds.special_div_threshold_pct == 5.0
        assert thresholds.spinoff_threshold_pct == 25.0
        assert thresholds.sample_points == 15
        assert thresholds.min_data_age_days == 90
        assert thresholds.check_full_history is False

    def test_adjustment_event_creation(self):
        """Test AdjustmentEvent dataclass creation."""
        event = AdjustmentEvent(
            symbol="AAPL",
            event_type=AdjustmentType.DIVIDEND,
            severity=AdjustmentSeverity.NORMAL,
            pct_difference=0.5,
            check_date="2024-01-15",
            db_price=185.64,
            yf_adjusted_price=183.90,
            details={"dividend_count": 3},
            recommendation="Refresh historical data",
        )
        
        assert event.symbol == "AAPL"
        assert event.event_type == AdjustmentType.DIVIDEND
        assert event.severity == AdjustmentSeverity.NORMAL
        assert event.pct_difference == 0.5
        assert event.check_date == "2024-01-15"
        assert event.db_price == 185.64
        assert event.yf_adjusted_price == 183.90
        assert event.details == {"dividend_count": 3}
        assert event.recommendation == "Refresh historical data"

    def test_adjustment_event_to_dict(self):
        """Test AdjustmentEvent.to_dict() method."""
        event = AdjustmentEvent(
            symbol="AAPL",
            event_type=AdjustmentType.STOCK_SPLIT,
            severity=AdjustmentSeverity.CRITICAL,
            pct_difference=75.0,
            check_date="2024-06-10",
            db_price=180.0,
            yf_adjusted_price=45.0,
            details={"splits": [{"date": "2024-06-10", "ratio": 4.0}]},
            recommendation="Immediate refresh required",
        )
        
        result = event.to_dict()
        
        assert result["symbol"] == "AAPL"
        assert result["event_type"] == "stock_split"
        assert result["severity"] == "critical"
        assert result["pct_difference"] == 75.0
        assert result["check_date"] == "2024-06-10"
        assert result["db_price"] == 180.0
        assert result["yf_adjusted_price"] == 45.0
        assert result["details"]["splits"][0]["ratio"] == 4.0
        assert result["recommendation"] == "Immediate refresh required"

    def test_adjustment_event_default_values(self):
        """Test AdjustmentEvent with default values."""
        event = AdjustmentEvent(
            symbol="MSFT",
            event_type=AdjustmentType.UNKNOWN,
            severity=AdjustmentSeverity.LOW,
            pct_difference=0.01,
            check_date="2024-01-01",
            db_price=100.0,
            yf_adjusted_price=99.99,
        )
        
        assert event.details == {}
        assert event.recommendation == ""

    def test_scan_result_creation(self):
        """Test ScanResult dataclass creation."""
        result = ScanResult(
            symbol="AAPL",
            needs_refresh=True,
            max_pct_diff=1.5,
        )
        
        assert result.symbol == "AAPL"
        assert result.needs_refresh is True
        assert result.events == []
        assert result.max_pct_diff == 1.5
        assert result.error is None

    def test_scan_result_with_events(self):
        """Test ScanResult with events."""
        event = AdjustmentEvent(
            symbol="AAPL",
            event_type=AdjustmentType.DIVIDEND,
            severity=AdjustmentSeverity.NORMAL,
            pct_difference=0.5,
            check_date="2024-01-15",
            db_price=185.64,
            yf_adjusted_price=183.90,
        )
        
        result = ScanResult(
            symbol="AAPL",
            needs_refresh=True,
            events=[event],
            max_pct_diff=0.5,
        )
        
        assert len(result.events) == 1
        assert result.events[0].symbol == "AAPL"

    def test_scan_result_with_error(self):
        """Test ScanResult with error."""
        result = ScanResult(
            symbol="INVALID",
            error="Symbol not found",
        )
        
        assert result.symbol == "INVALID"
        assert result.needs_refresh is False
        assert result.events == []
        assert result.error == "Symbol not found"

    def test_scan_result_to_dict(self):
        """Test ScanResult.to_dict() method."""
        event = AdjustmentEvent(
            symbol="AAPL",
            event_type=AdjustmentType.DIVIDEND,
            severity=AdjustmentSeverity.NORMAL,
            pct_difference=0.5,
            check_date="2024-01-15",
            db_price=185.64,
            yf_adjusted_price=183.90,
        )
        
        result = ScanResult(
            symbol="AAPL",
            needs_refresh=True,
            events=[event],
            max_pct_diff=0.5,
        )
        
        dict_result = result.to_dict()
        
        assert dict_result["symbol"] == "AAPL"
        assert dict_result["needs_refresh"] is True
        assert len(dict_result["events"]) == 1
        assert dict_result["events"][0]["event_type"] == "dividend"
        assert dict_result["max_pct_diff"] == 0.5
        assert dict_result["error"] is None


class TestCompareWithPrecision:
    """Tests for TID-ADJ-003: High precision price comparison."""

    def test_compare_identical_prices(self):
        """Test comparing identical prices returns 0% difference."""
        detector = PrecisionAdjustmentDetector()
        pct_diff, is_significant = detector._compare_with_precision(100.0, 100.0)
        
        assert pct_diff == 0.0
        assert is_significant is False

    def test_compare_significant_difference(self):
        """Test comparing prices with 1% difference is detected."""
        detector = PrecisionAdjustmentDetector()
        pct_diff, is_significant = detector._compare_with_precision(100.0, 99.0)
        
        assert pct_diff == pytest.approx(1.0)
        assert is_significant is True

    def test_compare_noise_level(self):
        """Test tiny differences (floating-point noise) are ignored."""
        detector = PrecisionAdjustmentDetector()
        # 0.000001% difference - below noise threshold
        pct_diff, is_significant = detector._compare_with_precision(100.0, 99.999999)
        
        assert is_significant is False

    def test_compare_threshold_boundary(self):
        """Test differences at exactly min_detection_pct threshold."""
        detector = PrecisionAdjustmentDetector()
        # min_detection_pct is 0.001%, so 0.001% difference should be significant
        # 100 * 0.00001 = 0.001
        db_price = 100.0
        yf_price = db_price * (1 - 0.00001)  # 0.001% less
        pct_diff, is_significant = detector._compare_with_precision(db_price, yf_price)
        
        assert pct_diff >= 0.001
        assert is_significant is True

    def test_compare_zero_db_price(self):
        """Test handling of zero database price."""
        detector = PrecisionAdjustmentDetector()
        pct_diff, is_significant = detector._compare_with_precision(0, 100.0)
        
        assert pct_diff == 0.0
        assert is_significant is False

    def test_compare_zero_yf_price(self):
        """Test handling of zero yfinance price."""
        detector = PrecisionAdjustmentDetector()
        pct_diff, is_significant = detector._compare_with_precision(100.0, 0)
        
        assert pct_diff == 0.0
        assert is_significant is False

    def test_compare_both_zero(self):
        """Test handling of both prices being zero."""
        detector = PrecisionAdjustmentDetector()
        pct_diff, is_significant = detector._compare_with_precision(0, 0)
        
        assert pct_diff == 0.0
        assert is_significant is False

    def test_compare_large_difference(self):
        """Test detecting large price differences (split scenario)."""
        detector = PrecisionAdjustmentDetector()
        # Stock split: DB has old price 200, YF has adjusted price 50 (4:1 split)
        pct_diff, is_significant = detector._compare_with_precision(200.0, 50.0)
        
        assert pct_diff == pytest.approx(75.0)
        assert is_significant is True

    def test_compare_custom_thresholds(self):
        """Test with custom detection thresholds."""
        custom_thresholds = DetectionThresholds(
            float_noise_pct=0.01,
            min_detection_pct=0.1,
        )
        detector = PrecisionAdjustmentDetector(thresholds=custom_thresholds)
        
        # 0.05% difference - below custom threshold
        pct_diff, is_significant = detector._compare_with_precision(100.0, 99.95)
        
        assert pct_diff == pytest.approx(0.05)
        assert is_significant is False

    def test_compare_decimal_precision(self):
        """Test precision with many decimal places."""
        detector = PrecisionAdjustmentDetector()
        # Real-world prices with many decimals
        pct_diff, is_significant = detector._compare_with_precision(
            185.64123456, 183.90987654
        )
        
        # Should detect approximately 0.93% difference
        assert pct_diff == pytest.approx(0.932, rel=0.01)
        assert is_significant is True


class TestClassifyEvent:
    """Tests for TID-ADJ-004: Event classification method."""
    
    def _create_mock_splits(self, data: list[tuple[str, float]]):
        """Create a mock pandas Series for splits data."""
        import pandas as pd
        if not data:
            return pd.Series(dtype=float)
        dates = [pd.Timestamp(d) for d, _ in data]
        values = [v for _, v in data]
        return pd.Series(values, index=dates)
    
    def _create_mock_dividends(self, data: list[tuple[str, float]]):
        """Create a mock pandas Series for dividends data."""
        import pandas as pd
        if not data:
            return pd.Series(dtype=float)
        dates = [pd.Timestamp(d) for d, _ in data]
        values = [v for _, v in data]
        return pd.Series(values, index=dates)

    def test_classify_stock_split(self):
        """Test classification of stock split event."""
        detector = PrecisionAdjustmentDetector()
        
        # Mock ticker data with a 4:1 split
        ticker_data = {
            "splits": self._create_mock_splits([("2024-06-10", 4.0)]),
            "dividends": self._create_mock_dividends([]),
            "capital_gains": None,
        }
        
        event_type, severity, details = detector._classify_event(
            pct_diff=75.0,
            ticker_data=ticker_data,
            check_date="2024-01-01",
        )
        
        assert event_type == AdjustmentType.STOCK_SPLIT
        assert severity == AdjustmentSeverity.CRITICAL
        assert "splits" in details
        assert details["cumulative_factor"] == 4.0

    def test_classify_reverse_split(self):
        """Test classification of reverse split event."""
        detector = PrecisionAdjustmentDetector()
        
        # Mock ticker data with a 1:10 reverse split
        ticker_data = {
            "splits": self._create_mock_splits([("2024-06-10", 0.1)]),
            "dividends": self._create_mock_dividends([]),
            "capital_gains": None,
        }
        
        event_type, severity, details = detector._classify_event(
            pct_diff=90.0,
            ticker_data=ticker_data,
            check_date="2024-01-01",
        )
        
        assert event_type == AdjustmentType.REVERSE_SPLIT
        assert severity == AdjustmentSeverity.HIGH
        assert details["cumulative_factor"] == 0.1

    def test_classify_dividend(self):
        """Test classification of regular dividend event."""
        detector = PrecisionAdjustmentDetector()
        
        # Mock ticker data with quarterly dividends
        ticker_data = {
            "splits": self._create_mock_splits([]),
            "dividends": self._create_mock_dividends([
                ("2024-03-15", 0.25),
                ("2024-06-15", 0.25),
                ("2024-09-15", 0.25),
            ]),
            "capital_gains": None,
        }
        
        event_type, severity, details = detector._classify_event(
            pct_diff=0.5,
            ticker_data=ticker_data,
            check_date="2024-01-01",
        )
        
        assert event_type == AdjustmentType.DIVIDEND
        assert severity == AdjustmentSeverity.NORMAL
        assert details["dividend_count"] == 3
        assert details["total_dividends"] == pytest.approx(0.75)

    def test_classify_special_dividend(self):
        """Test classification of special dividend event."""
        detector = PrecisionAdjustmentDetector()
        
        # Mock ticker data with one large special dividend
        ticker_data = {
            "splits": self._create_mock_splits([]),
            "dividends": self._create_mock_dividends([
                ("2024-03-15", 0.25),
                ("2024-06-15", 5.00),  # Special dividend
                ("2024-09-15", 0.25),
            ]),
            "capital_gains": None,
        }
        
        event_type, severity, details = detector._classify_event(
            pct_diff=3.0,  # Above special_div_threshold_pct (2.0%)
            ticker_data=ticker_data,
            check_date="2024-01-01",
        )
        
        assert event_type == AdjustmentType.SPECIAL_DIVIDEND
        assert severity == AdjustmentSeverity.HIGH
        assert details["special_dividend"] == 5.00

    def test_classify_spinoff(self):
        """Test classification of spinoff event."""
        detector = PrecisionAdjustmentDetector()
        
        # Mock ticker data with no splits or dividends (but large price difference)
        ticker_data = {
            "splits": self._create_mock_splits([]),
            "dividends": self._create_mock_dividends([]),
            "capital_gains": None,
        }
        
        event_type, severity, details = detector._classify_event(
            pct_diff=20.0,  # Above spinoff_threshold_pct (15.0%)
            ticker_data=ticker_data,
            check_date="2024-01-01",
        )
        
        assert event_type == AdjustmentType.SPINOFF
        assert severity == AdjustmentSeverity.CRITICAL
        assert "note" in details

    def test_classify_capital_gain(self):
        """Test classification of ETF capital gain distribution."""
        import pandas as pd
        detector = PrecisionAdjustmentDetector()
        
        # Mock capital gains data
        cap_gains = pd.Series(
            [0.50, 0.75],
            index=[pd.Timestamp("2024-06-15"), pd.Timestamp("2024-12-15")]
        )
        
        ticker_data = {
            "splits": self._create_mock_splits([]),
            "dividends": self._create_mock_dividends([]),
            "capital_gains": cap_gains,
        }
        
        event_type, severity, details = detector._classify_event(
            pct_diff=0.8,
            ticker_data=ticker_data,
            check_date="2024-01-01",
        )
        
        assert event_type == AdjustmentType.CAPITAL_GAIN
        assert severity == AdjustmentSeverity.NORMAL
        assert details["capital_gains"] == pytest.approx(1.25)

    def test_classify_unknown(self):
        """Test classification of unknown event."""
        detector = PrecisionAdjustmentDetector()
        
        # Mock ticker data with no history
        ticker_data = {
            "splits": self._create_mock_splits([]),
            "dividends": self._create_mock_dividends([]),
            "capital_gains": None,
        }
        
        event_type, severity, details = detector._classify_event(
            pct_diff=5.0,  # Below spinoff threshold
            ticker_data=ticker_data,
            check_date="2024-01-01",
        )
        
        assert event_type == AdjustmentType.UNKNOWN
        assert severity == AdjustmentSeverity.LOW
        assert "note" in details

    def test_classify_split_before_check_date_ignored(self):
        """Test that splits before check_date are ignored."""
        detector = PrecisionAdjustmentDetector()
        
        # Split happened before check_date
        ticker_data = {
            "splits": self._create_mock_splits([("2023-06-10", 4.0)]),
            "dividends": self._create_mock_dividends([]),
            "capital_gains": None,
        }
        
        event_type, severity, details = detector._classify_event(
            pct_diff=75.0,
            ticker_data=ticker_data,
            check_date="2024-01-01",  # After the split
        )
        
        # Should be spinoff since no relevant splits found
        assert event_type == AdjustmentType.SPINOFF
        assert severity == AdjustmentSeverity.CRITICAL


class TestGetSamplePrices:
    """Tests for TID-ADJ-005: Sample price retrieval method."""
    
    @pytest.fixture
    def detector(self):
        """Create a detector with default thresholds."""
        return PrecisionAdjustmentDetector()
    
    @pytest.fixture
    def detector_custom_thresholds(self):
        """Create a detector with custom thresholds for testing."""
        return PrecisionAdjustmentDetector(
            thresholds=DetectionThresholds(
                sample_points=5,
                min_data_age_days=30,
            )
        )
    
    @pytest.mark.asyncio
    async def test_sample_prices_normal(self, detector):
        """Test normal case with sufficient data (mocked DB)."""
        from datetime import date, timedelta
        from unittest.mock import AsyncMock, MagicMock
        
        # Create mock data - 100 days of prices, but only 40 older than min_data_age (60)
        today = date.today()
        mock_rows = [
            (today - timedelta(days=i), 100.0 + i * 0.1)
            for i in range(100, 60, -1)  # 61-100 days ago (40 data points)
        ]
        mock_rows.reverse()  # Order by date ascending
        
        # Mock session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result
        
        samples = await detector.get_sample_prices(mock_session, "AAPL")
        
        # Should have sampled points
        assert len(samples) > 0
        assert len(samples) <= detector.thresholds.sample_points + 2  # +2 for first/last
        
        # All samples should be (date, float) tuples
        for sample_date, sample_price in samples:
            assert isinstance(sample_date, date)
            assert isinstance(sample_price, float)
    
    @pytest.mark.asyncio
    async def test_sample_prices_insufficient_data(self, detector):
        """Test returns empty list when insufficient data."""
        from datetime import date
        from unittest.mock import AsyncMock, MagicMock
        
        # Only 1 data point
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(date.today(), 100.0)]
        mock_session.execute.return_value = mock_result
        
        samples = await detector.get_sample_prices(mock_session, "AAPL")
        
        assert samples == []
    
    @pytest.mark.asyncio
    async def test_sample_prices_empty_data(self, detector):
        """Test returns empty list when no data available."""
        from unittest.mock import AsyncMock, MagicMock
        
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result
        
        samples = await detector.get_sample_prices(mock_session, "AAPL")
        
        assert samples == []
    
    @pytest.mark.asyncio
    async def test_sample_prices_includes_oldest_newest(self, detector_custom_thresholds):
        """Test that samples include oldest and newest points."""
        from datetime import date, timedelta
        from unittest.mock import AsyncMock, MagicMock
        
        today = date.today()
        # 50 data points, all older than 30 days
        mock_rows = [
            (today - timedelta(days=i), 100.0 + i)
            for i in range(80, 30, -1)  # 31-80 days ago
        ]
        mock_rows.reverse()  # Order by date ascending
        
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result
        
        samples = await detector_custom_thresholds.get_sample_prices(mock_session, "AAPL")
        
        # First sample should be oldest
        assert samples[0][0] == mock_rows[0][0]
        # Last sample should be newest (before cutoff)
        assert samples[-1][0] == mock_rows[-1][0]
    
    @pytest.mark.asyncio
    async def test_sample_prices_respects_sample_points_limit(self, detector_custom_thresholds):
        """Test that samples respect the sample_points limit with reasonable overhead."""
        from datetime import date, timedelta
        from unittest.mock import AsyncMock, MagicMock
        
        today = date.today()
        # Create 100 data points older than 30 days
        mock_rows = [
            (today - timedelta(days=i), 100.0 + i)
            for i in range(130, 30, -1)  # 31-130 days ago
        ]
        mock_rows.reverse()
        
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result
        
        samples = await detector_custom_thresholds.get_sample_prices(mock_session, "AAPL")
        
        # Should not exceed sample_points + 4 (for guaranteed first/last + recent period extras)
        # The enhanced sampling adds a few extra points from recent period for better split detection
        assert len(samples) <= detector_custom_thresholds.thresholds.sample_points + 4
    
    @pytest.mark.asyncio
    async def test_sample_prices_two_data_points(self, detector):
        """Test minimum case with exactly 2 data points."""
        from datetime import date, timedelta
        from unittest.mock import AsyncMock, MagicMock
        
        today = date.today()
        mock_rows = [
            (today - timedelta(days=100), 100.0),
            (today - timedelta(days=90), 110.0),
        ]
        
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result
        
        samples = await detector.get_sample_prices(mock_session, "AAPL")
        
        assert len(samples) == 2
        assert samples[0] == mock_rows[0]
        assert samples[1] == mock_rows[1]


class TestDetectAdjustments:
    """Tests for TID-ADJ-006: Single symbol adjustment detection."""
    
    @pytest.fixture
    def detector(self):
        """Create a detector with default thresholds."""
        return PrecisionAdjustmentDetector()
    
    @pytest.mark.asyncio
    async def test_detect_no_adjustment_needed(self, detector):
        """Test detection when no adjustment is needed."""
        from datetime import date, timedelta
        from unittest.mock import AsyncMock, MagicMock, patch
        import pandas as pd
        
        today = date.today()
        mock_rows = [
            (today - timedelta(days=100), 100.0),
            (today - timedelta(days=90), 100.0),
        ]
        
        # Mock session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result
        
        # Mock yfinance - same prices (no adjustment needed)
        mock_ticker = MagicMock()
        mock_hist = pd.DataFrame({
            'Close': [100.0, 100.0],
        }, index=[pd.Timestamp(mock_rows[0][0]), pd.Timestamp(mock_rows[1][0])])
        mock_ticker.history.return_value = mock_hist
        mock_ticker.splits = pd.Series(dtype=float)
        mock_ticker.dividends = pd.Series(dtype=float)
        
        with patch('yfinance.Ticker', return_value=mock_ticker):
            result = await detector.detect_adjustments(mock_session, "AAPL")
        
        assert result.symbol == "AAPL"
        assert result.needs_refresh is False
        assert len(result.events) == 0
        assert result.error is None
    
    @pytest.mark.asyncio
    async def test_detect_split_detected(self, detector):
        """Test detection of stock split."""
        from datetime import date, timedelta
        from unittest.mock import AsyncMock, MagicMock, patch
        import pandas as pd
        
        today = date.today()
        mock_rows = [
            (today - timedelta(days=100), 400.0),  # Old unsplit price
            (today - timedelta(days=90), 400.0),
        ]
        
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result
        
        # Mock yfinance - split adjusted prices (4:1 split)
        mock_ticker = MagicMock()
        mock_hist = pd.DataFrame({
            'Close': [100.0, 100.0],  # Post-split adjusted
        }, index=[pd.Timestamp(mock_rows[0][0]), pd.Timestamp(mock_rows[1][0])])
        mock_ticker.history.return_value = mock_hist
        
        # Mock a 4:1 split that happened after check_date
        split_date = today - timedelta(days=80)
        mock_ticker.splits = pd.Series([4.0], index=[pd.Timestamp(split_date)])
        mock_ticker.dividends = pd.Series(dtype=float)
        
        with patch('yfinance.Ticker', return_value=mock_ticker):
            result = await detector.detect_adjustments(mock_session, "AAPL")
        
        assert result.symbol == "AAPL"
        assert result.needs_refresh is True
        assert len(result.events) > 0
        assert result.events[0].event_type == AdjustmentType.STOCK_SPLIT
        assert result.events[0].severity == AdjustmentSeverity.CRITICAL
    
    @pytest.mark.asyncio
    async def test_detect_dividend_detected(self, detector):
        """Test detection of dividend accumulation."""
        from datetime import date, timedelta
        from unittest.mock import AsyncMock, MagicMock, patch
        import pandas as pd
        
        today = date.today()
        mock_rows = [
            (today - timedelta(days=100), 100.0),
            (today - timedelta(days=90), 100.0),
        ]
        
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result
        
        # Mock yfinance - dividend adjusted (0.5% lower)
        mock_ticker = MagicMock()
        mock_hist = pd.DataFrame({
            'Close': [99.5, 99.5],
        }, index=[pd.Timestamp(mock_rows[0][0]), pd.Timestamp(mock_rows[1][0])])
        mock_ticker.history.return_value = mock_hist
        mock_ticker.splits = pd.Series(dtype=float)
        
        # Dividends after check dates
        div_date = today - timedelta(days=85)
        mock_ticker.dividends = pd.Series([0.50], index=[pd.Timestamp(div_date)])
        
        with patch('yfinance.Ticker', return_value=mock_ticker):
            result = await detector.detect_adjustments(mock_session, "AAPL")
        
        assert result.needs_refresh is True
        assert len(result.events) > 0
        assert result.events[0].event_type == AdjustmentType.DIVIDEND
    
    @pytest.mark.asyncio
    async def test_detect_yfinance_error(self, detector):
        """Test handling of yfinance API errors."""
        from datetime import date, timedelta
        from unittest.mock import AsyncMock, MagicMock, patch
        
        today = date.today()
        mock_rows = [
            (today - timedelta(days=100), 100.0),
            (today - timedelta(days=90), 100.0),
        ]
        
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result
        
        # Mock yfinance to raise exception
        mock_ticker = MagicMock()
        mock_ticker.history.side_effect = Exception("API rate limit exceeded")
        
        with patch('yfinance.Ticker', return_value=mock_ticker):
            result = await detector.detect_adjustments(mock_session, "AAPL")
        
        assert result.symbol == "AAPL"
        assert result.needs_refresh is False
        assert result.error is not None
        assert "yfinance" in result.error.lower()
    
    @pytest.mark.asyncio
    async def test_detect_insufficient_data(self, detector):
        """Test handling when DB has insufficient data."""
        from unittest.mock import AsyncMock, MagicMock
        
        # Only 1 data point
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result
        
        result = await detector.detect_adjustments(mock_session, "AAPL")
        
        assert result.symbol == "AAPL"
        assert result.needs_refresh is False
        assert result.error is not None
        assert "Insufficient" in result.error
    
    @pytest.mark.asyncio
    async def test_detect_empty_yfinance_data(self, detector):
        """Test handling when yfinance returns no data."""
        from datetime import date, timedelta
        from unittest.mock import AsyncMock, MagicMock, patch
        import pandas as pd
        
        today = date.today()
        mock_rows = [
            (today - timedelta(days=100), 100.0),
            (today - timedelta(days=90), 100.0),
        ]
        
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result
        
        # Mock yfinance to return empty DataFrame
        mock_ticker = MagicMock()
        mock_ticker.history.return_value = pd.DataFrame()
        
        with patch('yfinance.Ticker', return_value=mock_ticker):
            result = await detector.detect_adjustments(mock_session, "AAPL")
        
        assert result.needs_refresh is False
        assert result.error is not None
        assert "No yfinance data" in result.error


class TestScanAllSymbols:
    """Tests for TID-ADJ-007: Full symbol scan method."""
    
    @pytest.fixture
    def detector(self):
        """Create a detector with default thresholds."""
        return PrecisionAdjustmentDetector()
    
    @pytest.mark.asyncio
    async def test_scan_multiple_symbols(self, detector):
        """Test scanning multiple symbols."""
        from unittest.mock import AsyncMock, MagicMock, patch
        
        # Create mock scan result
        mock_scan_result = ScanResult(
            symbol="AAPL",
            needs_refresh=False,
        )
        
        with patch.object(detector, 'detect_adjustments', return_value=mock_scan_result):
            mock_session = AsyncMock()
            
            result = await detector.scan_all_symbols(
                mock_session, 
                symbols=["AAPL", "MSFT", "GOOG"]
            )
        
        assert result["total_symbols"] == 3
        assert result["scanned"] == 3
        assert len(result["no_change"]) == 3
        assert len(result["errors"]) == 0
    
    @pytest.mark.asyncio
    async def test_scan_summary_statistics(self, detector):
        """Test that summary statistics are calculated correctly."""
        from unittest.mock import AsyncMock, patch
        
        # Create mock results with different event types
        def mock_detect(session, symbol):
            if symbol == "AAPL":
                return ScanResult(
                    symbol="AAPL",
                    needs_refresh=True,
                    events=[
                        AdjustmentEvent(
                            symbol="AAPL",
                            event_type=AdjustmentType.DIVIDEND,
                            severity=AdjustmentSeverity.NORMAL,
                            pct_difference=0.5,
                            check_date="2024-01-01",
                            db_price=100.0,
                            yf_adjusted_price=99.5,
                        )
                    ],
                )
            elif symbol == "NVDA":
                return ScanResult(
                    symbol="NVDA",
                    needs_refresh=True,
                    events=[
                        AdjustmentEvent(
                            symbol="NVDA",
                            event_type=AdjustmentType.STOCK_SPLIT,
                            severity=AdjustmentSeverity.CRITICAL,
                            pct_difference=75.0,
                            check_date="2024-06-01",
                            db_price=400.0,
                            yf_adjusted_price=100.0,
                        )
                    ],
                )
            return ScanResult(symbol=symbol, needs_refresh=False)
        
        with patch.object(detector, 'detect_adjustments', side_effect=mock_detect):
            mock_session = AsyncMock()
            
            result = await detector.scan_all_symbols(
                mock_session,
                symbols=["AAPL", "MSFT", "NVDA"]
            )
        
        assert result["summary"]["by_type"]["dividend"] == 1
        assert result["summary"]["by_type"]["stock_split"] == 1
        assert result["summary"]["by_severity"]["normal"] == 1
        assert result["summary"]["by_severity"]["critical"] == 1
    
    @pytest.mark.asyncio
    async def test_scan_categorization(self, detector):
        """Test proper categorization of scan results."""
        from unittest.mock import AsyncMock, patch
        
        def mock_detect(session, symbol):
            if symbol == "AAPL":
                return ScanResult(symbol="AAPL", needs_refresh=True, events=[
                    AdjustmentEvent(
                        symbol="AAPL", event_type=AdjustmentType.DIVIDEND,
                        severity=AdjustmentSeverity.NORMAL, pct_difference=0.5,
                        check_date="2024-01-01", db_price=100.0, yf_adjusted_price=99.5,
                    )
                ])
            elif symbol == "ERROR":
                return ScanResult(symbol="ERROR", error="Test error")
            return ScanResult(symbol=symbol, needs_refresh=False)
        
        with patch.object(detector, 'detect_adjustments', side_effect=mock_detect):
            mock_session = AsyncMock()
            
            result = await detector.scan_all_symbols(
                mock_session,
                symbols=["AAPL", "MSFT", "ERROR"]
            )
        
        assert len(result["needs_refresh"]) == 1
        assert len(result["no_change"]) == 1
        assert len(result["errors"]) == 1
        assert result["errors"][0]["symbol"] == "ERROR"
    
    @pytest.mark.asyncio
    async def test_scan_empty_symbols_list(self, detector):
        """Test scanning empty symbols list."""
        from unittest.mock import AsyncMock
        
        mock_session = AsyncMock()
        
        result = await detector.scan_all_symbols(mock_session, symbols=[])
        
        assert result["total_symbols"] == 0
        assert result["scanned"] == 0
        assert len(result["needs_refresh"]) == 0
    
    @pytest.mark.asyncio
    async def test_scan_fetches_active_symbols_when_none_provided(self, detector):
        """Test that active symbols are fetched when none provided."""
        from unittest.mock import AsyncMock, MagicMock, patch
        
        # Mock the symbols query
        mock_symbol_result = MagicMock()
        mock_symbol_result.fetchall.return_value = [("AAPL",), ("MSFT",)]
        
        mock_session = AsyncMock()
        mock_session.execute.return_value = mock_symbol_result
        
        mock_scan_result = ScanResult(symbol="test", needs_refresh=False)
        
        with patch.object(detector, 'detect_adjustments', return_value=mock_scan_result):
            result = await detector.scan_all_symbols(mock_session, symbols=None)
        
        # Should have queried for active symbols
        assert result["total_symbols"] == 2


class TestAutoFix:
    """Tests for TID-ADJ-008: Auto-fix method."""
    
    @pytest.fixture
    def detector(self):
        """Create a detector with default thresholds."""
        return PrecisionAdjustmentDetector()
    
    @pytest.mark.asyncio
    async def test_auto_fix_deletes_prices(self, detector):
        """Test that auto_fix deletes existing prices."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from datetime import date
        
        mock_session = AsyncMock()
        
        # Mock date range query result
        mock_range_result = MagicMock()
        mock_range_row = MagicMock()
        mock_range_row.first_date = date(2020, 1, 1)
        mock_range_row.last_date = date(2024, 12, 1)
        mock_range_result.fetchone.return_value = mock_range_row
        
        # Mock delete result
        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 100
        
        # First call returns range, second returns delete result
        mock_session.execute.side_effect = [mock_range_result, mock_delete_result]
        
        # Mock FetchJob
        mock_job = MagicMock()
        mock_job.job_id = "test-job-id"
        
        with patch('app.db.models.FetchJob', return_value=mock_job):
            result = await detector.auto_fix_symbol(mock_session, "AAPL")
        
        assert result["symbol"] == "AAPL"
        assert result["deleted_rows"] == 100
        assert result["date_range"] is not None
    
    @pytest.mark.asyncio
    async def test_auto_fix_creates_job(self, detector):
        """Test that auto_fix creates a fetch job with proper date range."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from datetime import date
        
        mock_session = AsyncMock()
        
        # Mock date range query
        mock_range_result = MagicMock()
        mock_range_row = MagicMock()
        mock_range_row.first_date = date(2020, 1, 1)
        mock_range_row.last_date = date(2024, 12, 1)
        mock_range_result.fetchone.return_value = mock_range_row
        
        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 50
        
        mock_session.execute.side_effect = [mock_range_result, mock_delete_result]
        
        mock_job = MagicMock()
        mock_job.job_id = "new-job-123"
        
        with patch('app.db.models.FetchJob', return_value=mock_job):
            result = await detector.auto_fix_symbol(mock_session, "AAPL")
        
        assert result["job_created"] is True
        assert result["job_id"] is not None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_auto_fix_returns_stats(self, detector):
        """Test that auto_fix returns proper statistics including date_range."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from datetime import date
        
        mock_session = AsyncMock()
        
        mock_range_result = MagicMock()
        mock_range_row = MagicMock()
        mock_range_row.first_date = date(2015, 1, 1)
        mock_range_row.last_date = date(2024, 11, 1)
        mock_range_result.fetchone.return_value = mock_range_row
        
        mock_delete_result = MagicMock()
        mock_delete_result.rowcount = 75
        
        mock_session.execute.side_effect = [mock_range_result, mock_delete_result]
        
        mock_job = MagicMock()
        mock_job.job_id = "stats-job-456"
        
        with patch('app.db.models.FetchJob', return_value=mock_job):
            result = await detector.auto_fix_symbol(mock_session, "MSFT")
        
        assert "symbol" in result
        assert "deleted_rows" in result
        assert "job_created" in result
        assert "job_id" in result
        assert "date_range" in result
        assert "timestamp" in result
        assert "error" in result
        
        assert result["symbol"] == "MSFT"
        assert result["deleted_rows"] == 75
        assert result["error"] is None
        assert result["date_range"]["from"] == "2015-01-01"
    
    @pytest.mark.asyncio
    async def test_auto_fix_handles_errors(self, detector):
        """Test error handling in auto_fix."""
        from unittest.mock import AsyncMock
        
        mock_session = AsyncMock()
        mock_session.execute.side_effect = Exception("Database error")
        
        result = await detector.auto_fix_symbol(mock_session, "ERROR")
        
        assert result["error"] is not None
        assert "Database error" in result["error"]
        mock_session.rollback.assert_called_once()
