import unittest
from unittest.mock import MagicMock, patch
from datetime import date
import pandas as pd
from app.services.fetcher import fetch_prices
from app.core.config import Settings
from app.services.data_cleaner import DataCleaner

class TestFetcherRefactored(unittest.TestCase):
    def setUp(self):
        self.settings = Settings()
        self.settings.FETCH_MAX_RETRIES = 1
        self.settings.FETCH_TIMEOUT_SECONDS = 1
        self.settings.YF_RATE_LIMIT_REQUESTS_PER_SECOND = 100
        self.settings.YF_RATE_LIMIT_BURST_SIZE = 100

    @patch("app.services.fetcher.yf.download")
    def test_fetch_prices_success(self, mock_download):
        # Setup mock DF
        df = pd.DataFrame({
            "Open": [100.0],
            "High": [110.0],
            "Low": [90.0],
            "Close": [105.0],
            "Volume": [1000],
            "Adj Close": [105.0]
        })
        mock_download.return_value = df
        
        # Execute
        result = fetch_prices(
            symbol="AAPL",
            start=date(2023, 1, 1),
            end=date(2023, 1, 2),
            settings=self.settings
        )
        
        # Verify
        self.assertIsNotNone(result)
        self.assertFalse(result.empty)
        self.assertIn("open", result.columns)
        self.assertNotIn("Adj Close", result.columns)
        self.assertNotIn("adj_close", result.columns)
        
    def test_data_cleaner(self):
        # Valid DF
        df = pd.DataFrame({
            "Open": [100.0],
            "High": [110.0],
            "Low": [90.0],
            "Close": [105.0],
            "Volume": [1000]
        })
        cleaned = DataCleaner.clean_price_data(df)
        self.assertIsNotNone(cleaned)
        self.assertIn("open", cleaned.columns)
        
        # Invalid DF (missing column)
        df_invalid = pd.DataFrame({
            "Open": [100.0],
            "High": [110.0],
            "Low": [90.0],
            # Missing Close
            "Volume": [1000]
        })
        cleaned_invalid = DataCleaner.clean_price_data(df_invalid)
        self.assertIsNone(cleaned_invalid)

if __name__ == "__main__":
    unittest.main()
