import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import date
from app.api.v1.prices import get_prices

class TestPricesEndpoint(unittest.IsolatedAsyncioTestCase):
    @patch("app.api.v1.prices.PriceService")
    async def test_get_prices(self, MockPriceService):
        # Setup
        mock_service = MockPriceService.return_value
        mock_service.get_prices = AsyncMock(return_value=[
            {"symbol": "AAPL", "date": date(2023, 1, 1), "close": 150.0}
        ])
        
        mock_session = AsyncMock()
        
        # Execute
        result = await get_prices(
            symbols="AAPL",
            date_from="2023-01-01",
            date_to="2023-01-31",
            auto_fetch=True,
            session=mock_session
        )
        
        # Verify
        MockPriceService.assert_called_once_with(mock_session)
        mock_service.get_prices.assert_called_once()
        call_args = mock_service.get_prices.call_args
        self.assertEqual(call_args.kwargs["symbols_list"], ["AAPL"])
        self.assertEqual(call_args.kwargs["date_from"], date(2023, 1, 1))
        self.assertEqual(call_args.kwargs["date_to"], date(2023, 1, 31))
        self.assertEqual(call_args.kwargs["auto_fetch"], True)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["symbol"], "AAPL")

if __name__ == "__main__":
    unittest.main()
