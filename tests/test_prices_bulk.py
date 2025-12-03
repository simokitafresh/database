import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from fastapi import HTTPException
from app.api.v1.prices import get_prices
from app.core.config import settings

class TestBulkPricesAPI(unittest.IsolatedAsyncioTestCase):
    
    @patch("app.api.v1.prices.PriceService")
    async def test_auto_fetch_true_respects_10_symbol_limit(self, MockPriceService):
        # settings.API_MAX_SYMBOLS is 10 by default
        symbols = ",".join([f"SYM{i}" for i in range(11)])
        
        mock_session = AsyncMock()
        
        with self.assertRaises(HTTPException) as cm:
            await get_prices(
                symbols=symbols,
                date_from="2023-01-01",
                date_to="2023-01-31",
                auto_fetch=True,
                session=mock_session
            )
        self.assertEqual(cm.exception.status_code, 422)
        self.assertIn("too many symbols requested", cm.exception.detail)

    @patch("app.api.v1.prices.PriceService")
    async def test_auto_fetch_false_allows_100_symbols(self, MockPriceService):
        # settings.API_MAX_SYMBOLS_LOCAL is 100 by default
        symbols = ",".join([f"SYM{i}" for i in range(100)])
        
        mock_service = MockPriceService.return_value
        mock_service.get_prices = AsyncMock(return_value=[])
        mock_session = AsyncMock()
        
        # Should not raise exception
        await get_prices(
            symbols=symbols,
            date_from="2023-01-01",
            date_to="2023-01-31",
            auto_fetch=False,
            session=mock_session
        )
        
    @patch("app.api.v1.prices.PriceService")
    async def test_auto_fetch_false_rejects_over_100_symbols(self, MockPriceService):
        symbols = ",".join([f"SYM{i}" for i in range(101)])
        
        mock_session = AsyncMock()
        
        with self.assertRaises(HTTPException) as cm:
            await get_prices(
                symbols=symbols,
                date_from="2023-01-01",
                date_to="2023-01-31",
                auto_fetch=False,
                session=mock_session
            )
        self.assertEqual(cm.exception.status_code, 422)
        self.assertIn("too many symbols requested", cm.exception.detail)
        self.assertIn("max: 100", cm.exception.detail)

    @patch("app.api.v1.prices.PriceService")
    async def test_auto_fetch_false_allows_large_response(self, MockPriceService):
        # settings.API_MAX_ROWS_LOCAL is 200000
        mock_service = MockPriceService.return_value
        # Mock return value with 50001 rows (over default 50000 but under 200000)
        mock_service.get_prices = AsyncMock(return_value=[{}] * 50001)
        
        mock_session = AsyncMock()
        
        # Should not raise exception
        await get_prices(
            symbols="AAPL",
            date_from="2023-01-01",
            date_to="2023-01-31",
            auto_fetch=False,
            session=mock_session
        )

    @patch("app.api.v1.prices.PriceService")
    async def test_auto_fetch_true_rejects_large_response(self, MockPriceService):
        # settings.API_MAX_ROWS is 50000
        mock_service = MockPriceService.return_value
        # Mock return value with 50001 rows
        mock_service.get_prices = AsyncMock(return_value=[{}] * 50001)
        
        mock_session = AsyncMock()
        
        with self.assertRaises(HTTPException) as cm:
            await get_prices(
                symbols="AAPL",
                date_from="2023-01-01",
                date_to="2023-01-31",
                auto_fetch=True,
                session=mock_session
            )
        self.assertEqual(cm.exception.status_code, 413)
        self.assertIn("response too large", cm.exception.detail)

    @patch("app.api.v1.prices.PriceService")
    async def test_auto_fetch_false_rejects_over_200000_rows(self, MockPriceService):
        # settings.API_MAX_ROWS_LOCAL is 200000
        mock_service = MockPriceService.return_value
        # Mock return value with 200001 rows
        mock_service.get_prices = AsyncMock(return_value=[{}] * 200001)
        
        mock_session = AsyncMock()
        
        with self.assertRaises(HTTPException) as cm:
            await get_prices(
                symbols="AAPL",
                date_from="2023-01-01",
                date_to="2023-01-31",
                auto_fetch=False,
                session=mock_session
            )
        self.assertEqual(cm.exception.status_code, 413)
        self.assertIn("response too large", cm.exception.detail)
        self.assertIn("max: 200000", cm.exception.detail)

if __name__ == "__main__":
    unittest.main()
