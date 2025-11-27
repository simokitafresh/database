import unittest
from unittest.mock import MagicMock, patch, AsyncMock
from app.api.v1.symbols import list_symbols
from app.schemas.symbols import SymbolOut

class TestSymbolsEndpoint(unittest.IsolatedAsyncioTestCase):
    async def test_list_symbols(self):
        # Mock Session
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "exchange": "NASDAQ",
            "currency": "USD",
            "is_active": True,
            "first_date": None,
            "last_date": None,
            "created_at": None
        }
        mock_result.fetchall.return_value = [mock_row]
        mock_session.execute.return_value = mock_result

        # Test
        result = await list_symbols(active=True, session=mock_session)
        
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].symbol, "AAPL")
        self.assertIsInstance(result[0], SymbolOut)

if __name__ == "__main__":
    unittest.main()
