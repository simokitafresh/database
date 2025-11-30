import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date
from app.services.adjustment_detector import PrecisionAdjustmentDetector, ScanResult, AdjustmentSeverity
from app.services.adjustment_fixer import AdjustmentFixer

class TestAdjustmentDetectorRefactored(unittest.IsolatedAsyncioTestCase):
    async def test_detect_adjustments_no_data(self):
        detector = PrecisionAdjustmentDetector()
        mock_session = AsyncMock()
        
        # Mock get_sample_prices to return empty list
        with patch("app.services.adjustment_detector.PrecisionAdjustmentDetector.get_sample_prices", new_callable=AsyncMock) as mock_get_samples:
            mock_get_samples.return_value = []
            
            result = await detector.detect_adjustments(mock_session, "AAPL")
            
            self.assertIsInstance(result, ScanResult)
            self.assertIn("Insufficient historical data", result.error)

    @patch("app.services.adjustment_detector.get_symbols_for_scan")
    @patch("app.services.adjustment_detector.PrecisionAdjustmentDetector.detect_adjustments")
    async def test_scan_all_symbols(self, mock_detect, mock_get_symbols):
        detector = PrecisionAdjustmentDetector()
        mock_session = AsyncMock()
        
        mock_get_symbols.return_value = ["AAPL", "MSFT"]
        
        # Mock detection result
        mock_result = ScanResult(symbol="AAPL", needs_refresh=True)
        mock_detect.return_value = mock_result
        
        result = await detector.scan_all_symbols(mock_session)
        
        self.assertEqual(result["total_symbols"], 2)
        self.assertEqual(result["scanned"], 2)
        self.assertEqual(len(result["needs_refresh"]), 2) # Both return same mock result

    @patch("app.services.adjustment_detector.get_symbols_for_scan")
    @patch("app.services.adjustment_detector.PrecisionAdjustmentDetector.detect_adjustments")
    @patch("app.services.adjustment_detector.AdjustmentFixer")
    async def test_scan_all_symbols_with_autofix(self, MockFixer, mock_detect, mock_get_symbols):
        detector = PrecisionAdjustmentDetector()
        mock_session = AsyncMock()
        
        mock_get_symbols.return_value = ["AAPL"]
        mock_detect.return_value = ScanResult(symbol="AAPL", needs_refresh=True)
        
        mock_fixer_instance = MockFixer.return_value
        mock_fixer_instance.auto_fix_symbol = AsyncMock(return_value={"job_id": "123"})
        
        result = await detector.scan_all_symbols(mock_session, auto_fix=True)
        
        self.assertEqual(len(result["fixed"]), 1)
        self.assertEqual(result["fixed"][0]["job_id"], "123")
        mock_fixer_instance.auto_fix_symbol.assert_called_with("AAPL")

if __name__ == "__main__":
    unittest.main()
